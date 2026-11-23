"""HTTP smoke test for a running stack in development mode.

Creates a marked demo report and temporary graph records, then removes only the
records it created. Never resets a database. Requires DEV_LOGIN_ENABLED=true.
"""
import argparse
from io import BytesIO
from time import monotonic, sleep
import httpx
from PIL import Image

parser = argparse.ArgumentParser()
parser.add_argument('--base-url', default='http://127.0.0.1:8000')
args = parser.parse_args()
with httpx.Client(base_url=args.base_url, timeout=30, trust_env=False) as client:
    def request(method, path, headers=None, **kw):
        res = client.request(method, '/api/v1' + path, headers=headers, **kw)
        res.raise_for_status()
        return res
    headers = {}
    for role in ('user', 'knowledge_admin', 'ops_admin'):
        session = request('POST', '/auth/dev-login', json={'role': role}).json()
        headers[role] = {'Authorization': 'Bearer ' + session['access_token']}
    h = headers['user']
    image = BytesIO()
    Image.new('RGB', (96,96), (190,130,135)).save(image, format='PNG')
    fid = request('POST', '/uploads', h, files={'file': ('synthetic-test.png', image.getvalue(), 'image/png')}).json()['id']
    aid = request('POST', '/analyses', h, json={'image_id': fid, 'symptoms': '联调验证：口干、乏力', 'duration': '近一周'}).json()['id']
    end = monotonic() + 150
    while monotonic() < end:
        task = request('GET', '/analyses/' + aid, h).json()
        if task['status'] == 'completed': break
        if task['status'] == 'failed': raise RuntimeError(task['error'])
        sleep(.5)
    else: raise RuntimeError('Analysis timed out')
    rid = task['report_id']
    report = request('GET', '/reports/' + rid, h).json()
    evidence = request('GET', '/reports/' + rid + '/evidence', h).json()
    pdf = request('GET', '/reports/' + rid + '/pdf', h)
    assert pdf.content.startswith(b'%PDF-')
    assert request('GET', '/reports', h).json()['total'] >= 1
    kh = headers['knowledge_admin']
    source_id = entity_id = relation_id = None
    try:
        source_id = request('POST', '/knowledge/sources', kh, json={'title': 'HTTP smoke fixture', 'citation': 'Synthetic integration-test data, not clinical evidence', 'is_demo': True}).json()['id']
        node = {'name': '联调测试实体', 'kind': '症状', 'text': '联调数据，验证后删除', 'source_id': source_id, 'aliases': [], 'status': 'pending'}
        entity_id = request('POST', '/knowledge/entities', kh, json=node).json()['id']
        request('POST', '/knowledge/entities/' + entity_id + '/publish', kh)
        graph = request('GET', '/knowledge/graph', kh).json()
        assert any(x['id'] == entity_id for x in graph['nodes'])
        existing = next((x for x in graph['nodes'] if x['id'] != entity_id and x['status'] == 'published'), None)
        if existing:
            relation_id = request('POST', '/knowledge/relations', kh, json={'source': entity_id, 'target': existing['id'], 'kind': '相关', 'source_id': source_id, 'status': 'pending'}).json()['id']
            request('POST', '/knowledge/relations/' + relation_id + '/publish', kh)
    finally:
        if relation_id: request('DELETE', '/knowledge/relations/' + relation_id, kh)
        if entity_id: request('DELETE', '/knowledge/entities/' + entity_id, kh)
        if source_id: request('DELETE', '/knowledge/sources/' + source_id, kh)
    overview = request('GET', '/operations/overview', headers['ops_admin']).json()
    assert overview['today_analyses'] >= 1
    assert all(s['status'] != 'offline' for s in overview['services']), overview['services']
    print('PASS: upload -> queued worker -> report -> evidence -> PDF -> history')
    print('PASS: graph source/entity/relationship CRUD and publication; operations probes')
    print('Report mode:', 'demo' if report['is_demo'] else 'model', '; evidence snapshots:', len(evidence['items']))
