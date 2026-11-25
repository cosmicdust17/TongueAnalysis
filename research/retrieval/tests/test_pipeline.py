"""Synthetic contract checks; these scores are not textbook/model quality measurements."""
import json
import numpy as np
import pytest
from fastapi.testclient import TestClient
from research.retrieval.core import LocalIndex, build_vectors, query_text, retrieve
from research.retrieval.evaluation import evaluate, metrics, validate_labels
from research.retrieval.graph import local_url, review, validate_candidate
from research.retrieval.io_utils import digest, rows, write_rows
from research.retrieval.service import create_app
from research.retrieval.demo import SyntheticModels


@pytest.fixture
def corpus(tmp_path):
    chunks = [dict(chunk_id=f'demo-{i}', text=t, source_title='合成测试资料（非教材）', edition=None,
                   location={'chapter': '测试', 'pdf_page': None, 'printed_page': None, 'paragraph': None}, is_demo=True)
              for i, t in enumerate(['测试寒象：畏寒，舌淡。', '测试热象：口渴，舌红。', '测试无关段落。'])]
    path = tmp_path / 'chunks.jsonl'
    write_rows(path, chunks)
    return path, chunks


def test_metrics():
    assert metrics(['a', 'b', 'c'], ['b', 'd'], 3) == {'recall': .5, 'rr': .5}
    assert metrics([], ['a'], 3) == {'recall': 0, 'rr': 0}


def test_graph_only_does_not_load_vector_models(monkeypatch):
    def unexpected_models():
        pytest.fail('Graph mode must not load vector models')

    class Store:
        def graph(self, chunk_id, limit):
            assert (chunk_id, limit) == ('source', 3)
            return [{'relation': {'chunk_id': chunk_id}}]

    monkeypatch.setattr('research.retrieval.service.Models', unexpected_models)
    with TestClient(create_app(store=Store(), graph_only=True)) as client:
        assert client.get('/health').json()['mode'] == 'graph-only'
        assert client.get('/v1/graph', params={'chunk_id': 'source', 'limit': 3}).json() == {
            'relations': [{'relation': {'chunk_id': 'source'}}],
        }
        assert client.post('/v1/retrieve', json={'symptoms': '畏寒'}).status_code == 503


def test_query_validation():
    assert query_text('畏寒', '舌淡') == '症状：畏寒；舌象：舌淡'
    with pytest.raises(ValueError):
        query_text(' ', '')


def test_index_contract_and_api(corpus, tmp_path, monkeypatch):
    path, chunks = corpus
    models = SyntheticModels()
    build_vectors(path, tmp_path / 'index', models)
    index = LocalIndex(tmp_path / 'index', models)
    client = TestClient(create_app(index, models))
    result = client.post('/v1/retrieve', json={'symptoms': '畏寒', 'tongue_features': '舌淡'}).json()
    assert result['evidence'][0]['chunk_id'] == 'demo-0'
    assert result['evidence'][0]['location']['printed_page'] is None
    assert result['evidence'][0]['is_demo'] is True
    assert client.post('/v1/retrieve', json={}).status_code == 422
    assert client.post('/v1/retrieve', json={'symptoms': '寒', 'top_k': 10, 'candidate_count': 2}).status_code == 422
    monkeypatch.delenv('RETRIEVAL_ADMIN_TOKEN', raising=False)
    assert client.get('/v1/admin/graph').status_code == 401
    assert client.get('/v1/graph').status_code == 503
    models.identity = 'different-embedding'
    with pytest.raises(ValueError, match='rebuild'):
        LocalIndex(tmp_path / 'index', models)


def test_review_guards(corpus, tmp_path):
    _, chunks = corpus
    candidate = dict(subject='测试寒象', predicate='表现', object='畏寒', quote='畏寒', chunk_id='demo-0')
    cid = validate_candidate(candidate, {v['chunk_id']: v for v in chunks})
    candidate.update(candidate_id=cid, status='pending', source_hash=digest(chunks[0]))
    path = tmp_path / 'review.jsonl'
    write_rows(path, [candidate])
    review(path, cid, 'approved', 'tester')
    assert rows(path)[0]['reviewed_at']
    review(path, cid, 'rejected', 'tester')
    assert rows(path)[0]['status'] == 'rejected'
    candidate['quote'] = '不存在的原文'
    with pytest.raises(ValueError):
        validate_candidate(candidate, {v['chunk_id']: v for v in chunks})
    with pytest.raises(ValueError):
        local_url('https://remote.example/v1')


def test_heldout_labels(corpus, tmp_path):
    path, chunks = corpus
    label = dict(query_id='synthetic-test', symptoms='畏寒', tongue_features='舌淡', relevant_chunk_ids=['demo-0'],
                 hard_negative_chunk_ids=['demo-1'], split='test', is_demo=True, human_verified=False, reviewer=None)
    with pytest.raises(ValueError, match='Human'):
        validate_labels([label], {v['chunk_id']: v for v in chunks})
    with pytest.raises(ValueError, match='Duplicate'):
        validate_labels([label, dict(label, query_id='other', split='train')], {v['chunk_id']: v for v in chunks}, False)
    labels = tmp_path / 'labels.jsonl'
    write_rows(labels, [label])
    models = SyntheticModels()
    build_vectors(path, tmp_path / 'index', models)
    report = evaluate(LocalIndex(tmp_path / 'index', models), models, labels, tmp_path / 'report.json', 2, 3, allow_demo=True)
    assert report['is_demo']
    assert set(report['modes']) == {'symptoms', 'symptoms+tongue'}


def test_changed_corpus_detected(corpus, tmp_path):
    path, chunks = corpus
    models = SyntheticModels()
    build_vectors(path, tmp_path / 'index', models)
    chunks[0]['text'] = 'changed'
    write_rows(tmp_path / 'index' / 'chunks.jsonl', chunks)
    with pytest.raises(ValueError, match='changed'):
        LocalIndex(tmp_path / 'index', models)


def test_text_layer_extraction_is_stable(tmp_path, capsys):
    import pymupdf
    from research.retrieval.extract import extract, page_lines
    from research.retrieval.io_utils import write_json
    pdf = tmp_path / 'synthetic.pdf'
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((70, 120), 'Synthetic textbook paragraph with enough text to avoid any OCR fallback.')
    doc.save(pdf)
    doc.close()
    plan = dict(bibliography_confirmed=True, source_title='Synthetic book', edition='Test edition',
                publisher='Test publisher', copyright_pdf_page=1,
                sections=[dict(chapter='Test chapter', pdf_start=1, pdf_end=1)])
    write_json(tmp_path/'plan.json', plan)
    extract(pdf, tmp_path/'plan.json', tmp_path/'out')
    first = rows(tmp_path/'out/chunks.jsonl')
    extract(pdf, tmp_path/'plan.json', tmp_path/'out')
    assert rows(tmp_path/'out/chunks.jsonl') == first
    assert first[0]['location']['printed_page'] is None
    assert first[0]['location']['paragraph'] is None
    assert first[0]['extraction_method'] == 'text_layer'
    blank = pymupdf.open()
    blank.new_page()
    assert page_lines(blank[0]) == ([], 'needs_ocr')


def test_graph_publication_filters_and_revokes(corpus, tmp_path):
    from research.retrieval.graph import import_reviewed
    path, chunks = corpus
    values = []
    for status, chunk in zip(['approved', 'pending', 'rejected'], chunks):
        value = dict(subject='测试实体', predicate='测试关系', object='另一实体', chunk_id=chunk['chunk_id'], quote=chunk['text'])
        value.update(candidate_id=validate_candidate(value, {c['chunk_id']: c for c in chunks}),
                     source_hash=digest(chunk), status=status, reviewer='tester', reviewed_at='2026-11-19T00:00:00Z')
        values.append(value)
    write_rows(tmp_path/'review.jsonl', values)
    calls = []
    class Result:
        def values(self): return []
        def consume(self): return None
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute_write(self, fn): return fn(self)
        def run(self, query, **params):
            calls.append((query, params))
            return Result()
    class Driver:
        def session(self, **kwargs): return Session()
    class Store:
        driver = Driver()
        database = 'test'
    assert import_reviewed(Store(), path, tmp_path/'review.jsonl')['approved'] == 1
    assert 'DELETE r' in calls[1][0]
    assert calls[1][1]['ids'] == [v['candidate_id'] for v in values]
    assert len(calls[2][1]['values']) == 1
    assert calls[2][1]['values'][0]['status'] == 'approved'


def test_training_rejects_unreviewed_data(corpus, tmp_path):
    from research.retrieval.training import train
    path, _ = corpus
    labels = tmp_path/'labels.jsonl'
    write_rows(labels, [dict(query_id='a', symptoms='寒', tongue_features='舌淡', split='train',
                            relevant_chunk_ids=['demo-0'], hard_negative_chunk_ids=['demo-1'], human_verified=False)])
    with pytest.raises(ValueError, match='Human'):
        train('embedding', path, labels, tmp_path/'model', 'not-loaded')
