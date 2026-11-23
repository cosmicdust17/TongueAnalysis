import pytest
from research.retrieval.extract_batch import exact_quote, prepare_candidate
from research.retrieval.graph import validate_candidate
from research.retrieval.io_utils import digest, write_json
from research.retrieval.quality import quality


def chunk(page=60):
    return {'chunk_id': 'unit-source', 'text': '红舌。外感病中，红舌多见于热证。', 'source_title': '单元测试',
            'location': {'chapter': '舌诊', 'pdf_page': page}, 'is_demo': False}


def test_ocr_requires_approval_of_exact_source(tmp_path, monkeypatch):
    c = chunk(57)
    assert quality(c)['retrieval_eligible'] is False
    assert quality(chunk(60))['retrieval_eligible'] is True
    record = {'status': 'approved', 'source_hash': digest(c), 'reviewer': 'tester', 'reviewed_at': '2026-11-19'}
    path = tmp_path/'review.json'
    write_json(path, {c['chunk_id']: record})
    monkeypatch.setenv('RETRIEVAL_OCR_REVIEW_FILE', str(path))
    assert quality(c)['retrieval_eligible'] is True
    c['text'] += 'changed'
    assert quality(c)['retrieval_eligible'] is False


def test_qualifiers_conditions_and_term_normalization():
    c = chunk()
    triple = {'subject': '红舌', 'predicate': '多见于', 'object': '热证', 'condition': '外感病中',
              'quote': '外感病中，红舌多见于热证。'}
    v = prepare_candidate(triple, c, {'红舌': '舌红'}, 'test-model', 'test-revision')
    assert v['subject'] == '舌红' and v['subject_raw'] == '红舌'
    assert v['qualifiers'] == ['多见'] and v['predicate'] == '多见于'
    assert v['condition'] == '外感病中' and v['status'] == 'pending'
    assert validate_candidate(v, {c['chunk_id']: c}) == v['candidate_id']
    changed = dict(v, condition='')
    assert validate_candidate(changed, {c['chunk_id']: c}) != v['candidate_id']
    with pytest.raises(ValueError, match='condition'):
        prepare_candidate(dict(triple, condition='未出现条件'), c, {}, 'test', 'test')


def test_literal_applicability_clause_is_not_invented():
    c = chunk()
    c['text'] = '外感病见之，多属表证。'
    value = prepare_candidate({'subject':'淡红舌','predicate':'多属','object':'表证','quote':c['text'],'condition':''},
                              c, {}, 'test', 'test')
    assert value['condition'] == '外感病见之'
    assert value['condition'] in value['quote']
    assert value['condition_origin'] == 'literal_source_clause'
    assert value['review_warnings']


def test_quote_restores_only_whitespace():
    assert exact_quote('舌红，苔黄。', '前文舌红，\n苔黄。后文') == '舌红，\n苔黄。'
    with pytest.raises(ValueError):
        exact_quote('舌红，苔白。', '舌红，苔黄。')
    with pytest.raises(ValueError):
        exact_quote('', '舌红。')
