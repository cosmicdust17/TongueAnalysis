import hashlib
import json

import httpx

from app.core.config import settings


def test_textbook_graph_publication_states_and_citation(client, tokens, tmp_path, monkeypatch):
    config = settings()
    monkeypatch.setattr(config, 'retrieval_graph_base_url', 'http://graph.test')
    review_file = tmp_path / 'verified.json'
    monkeypatch.setattr(config, 'retrieval_review_file', str(review_file))
    evidence = {'chunk_id': 'reference', 'text': '外感病见之，多属表证', 'source_title': '中医诊断学',
                'location': {'printed_page': 44, 'pdf_page': 60, 'paragraph': None}}
    digest = hashlib.sha256(json.dumps({k:evidence[k] for k in ('text','source_title','location')},
                                       ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    review_file.write_text(json.dumps({'reference': {'status':'location_verified', 'content_sha256':digest,
                                                     'quotes':[evidence['text']]}}), encoding='utf-8')
    relation = {'candidate_id':'real','kind':'可见于','object_qualifier':'部分','quote':evidence['text'],
                'condition':'外感病见之','approved':True}
    edge = {'source': {'name':'淡红舌'}, 'target': {'name':'表证'}, 'relation':relation, 'evidence':evidence}
    rows = [edge, {**edge, 'relation': {**relation, 'approved': False}}, {**edge, 'evidence': {**evidence, 'is_demo': True}}]
    status = 200
    factory = httpx.AsyncClient
    def transport(request):
        assert request.url.host == 'graph.test'
        return httpx.Response(status, json={'relations':rows})
    monkeypatch.setattr('app.api.knowledge.httpx.AsyncClient', lambda **kw: factory(transport=httpx.MockTransport(transport), **kw))
    url = '/api/v1/knowledge/textbook-graph'
    assert client.get(url, headers=tokens['user']).status_code == 403
    response = client.get(url, headers=tokens['knowledge_admin'])
    assert response.status_code == 200
    only, = response.json()['relations']
    assert only['relation']['statement'] == '淡红舌可见于部分表证'
    assert only['relation']['condition'] == '外感病见之'
    assert only['evidence']['verified_location'] == {'printed_page':44}
    rows.clear()
    assert client.get(url, headers=tokens['knowledge_admin']).json()['relations'] == []
    status = 503
    assert client.get(url, headers=tokens['knowledge_admin']).status_code == 503
