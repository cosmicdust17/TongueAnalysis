import asyncio
import httpx
import json
import pytest
from app.integrations.retrieval.http import retrieve_http
from app.core.config import settings
from app.integrations.generation.generator import build_report
from app.integrations.inference.schemas import ModelResult

def test_retrieval_unavailable_and_mapping(monkeypatch):
    monkeypatch.setattr(settings(), 'retrieval_base_url', 'http://local')
    async def scenario():
        def handler(request):
            assert request.url.path == '/v1/retrieve'
            body = json.loads(request.content)
            assert body['tongue_features'] == '检出裂纹特征'
            return httpx.Response(200, json={'evidence': [{'chunk_id': 'book:1', 'text': '原文',
                'source_title': '教材', 'location': {'chapter': '舌诊', 'pdf_page': 1}, 'is_demo': True}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            status, chunks = await retrieve_http(client, '症状', [{'value': '检出裂纹特征', 'confidence': .7},
                {'value': '未检出其他特征', 'confidence': None}])
            assert status == 'available' and chunks[0]['text'] == '原文'
            assert chunks[0]['location']['pdf_page'] == 1 and chunks[0]['is_demo']
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as client:
            assert await retrieve_http(client, '', []) == ('unavailable', [])
    asyncio.run(scenario())

def test_report_preserves_detector_and_generation():
    r = ModelResult(model_version='qwen-test', tongue_features=[], fusion_result={
        'detections': [{'class_id': 2}], 'evidence_status': 'unavailable',
        'qwen': {'status': 'valid', 'output': {'symptoms_summary': '口干', 'analysis': '证据不足',
            'cited_chunk_ids': []}, 'metrics': {'seconds': 1}}})
    report = build_report(r, '原始症状', '', [])
    assert report['summary'] == '证据不足'
    assert report['evidence_status'] == 'unavailable'
    assert report['yolo_detections'] == [{'class_id': 2}]

def test_external_retrieval_does_not_require_embedded_graph():
    from app.core.config import Settings
    s = Settings(_env_file=None, jwt_secret='x'*40, graph_provider='neo4j',
        neo4j_password='', knowledge_retrieval_enabled=True, multimodal_enabled=True,
        model_provider='http')
    s.validate_runtime()

@pytest.mark.parametrize('unknown_id', [False, True])
def test_adapter_fills_evidence_from_retrieval_only(monkeypatch, tmp_path, unknown_id):
    from app.integrations.inference.http import HttpAdapter
    s = settings()
    monkeypatch.setattr(s, 'multimodal_enabled', True)
    monkeypatch.setattr(s, 'retrieval_base_url', 'http://retrieve')
    image = tmp_path/'image.jpg'
    image.write_bytes(b'image')
    seen = []
    def handler(request):
        seen.append(request.url.path)
        if request.url.path == '/v1/retrieve':
            return httpx.Response(200, json={'evidence': [{'chunk_id': 'book:1',
                'text': '后端原文', 'source_title': '真实教材', 'location': '第1页'}]})
        r = {'model_version': 'qwen-test', 'tongue_features': [], 'fusion_result': {}}
        if request.url.path == '/v1/infer':
            r['fusion_result']['qwen'] = {'status': 'valid', 'output': {
                'symptoms_summary': '口干', 'analysis': '分析',
                'cited_chunk_ids': ['invented' if unknown_id else 'book:1']}}
        return httpx.Response(200, json=r)
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    if unknown_id:
        with pytest.raises(ValueError):
            asyncio.run(HttpAdapter().analyze(str(image), '口干'))
    else:
        result = asyncio.run(HttpAdapter().analyze(str(image), '口干'))
        assert result.fusion_result['evidence'][0]['text'] == '后端原文'
        assert len(result.fusion_result['evidence'][0]['entity_id']) == 36
    assert seen == ['/v1/detect', '/v1/retrieve', '/v1/infer']
