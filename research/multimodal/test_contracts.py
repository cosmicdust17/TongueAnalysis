import json
import pytest
from contracts import parse_output, messages, retrieve
from prepare_data import convert

def test_citations_and_json():
    raw = json.dumps({'symptoms_summary': '', 'analysis': '无知识证据', 'cited_chunk_ids': []})
    assert parse_output(raw, [])['cited_chunk_ids'] == []
    with pytest.raises(ValueError):
        parse_output(raw.replace('[]', '["invented"]'), [])
    with pytest.raises(ValueError):
        parse_output(raw[:-1]+',"text":"invented"}', [])
    assert retrieve('', '', []) == ('disabled', [])
    assert retrieve('http://127.0.0.1:1', '', [], .1) == ('unavailable', [])

def test_modality_does_not_leak():
    image_only = messages('local.jpg', 'private symptoms', [{'class_id': 1}], [], 'image')
    assert 'private symptoms' not in str(image_only)
    symptoms_only = messages(None, '症状', [{'class_id': 1}], [], 'symptoms')
    assert 'local.jpg' not in str(symptoms_only) and 'class_id' not in str(symptoms_only)
    assert all(isinstance(m['content'], list) for m in image_only)
    report = messages(None, '症状', [{'class_id': 4}], [], 'report')
    assert all(c['type'] != 'image' for c in report[1]['content'])
    assert 'class_id' in str(report)

def test_no_negative_labels_and_split_preserved(tmp_path):
    import yaml
    names = ['hongshe', 'zishe', 'liewenshe', 'chihenshe', 'baitaishe', 'huangtaishe', 'heitaishe']
    for split in ('train', 'val'):
        (tmp_path/split/'images').mkdir(parents=True)
        (tmp_path/split/'labels').mkdir()
        (tmp_path/split/'images'/'x.jpg').write_bytes(split.encode())
        (tmp_path/split/'labels'/'x.txt').write_text('2 0.5 0.5 0.2 0.2\n')
    config = tmp_path/'data.yaml'
    config.write_text(yaml.safe_dump({'path': str(tmp_path), 'train': 'train/images', 'val': 'val/images', 'names': names}))
    assert convert(config, tmp_path/'out') == {'train': 1, 'val': 1}
    row = json.loads((tmp_path/'out/train.jsonl').read_text())
    assert row['reference']['annotated_attributes'] == ['liewenshe']
    assert 'hongshe' in row['reference']['unknown_attributes']
