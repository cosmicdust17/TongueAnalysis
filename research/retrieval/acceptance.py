"""Real database and HTTP acceptance. Full evidence remains in local files."""
import argparse
import json
import os
from pathlib import Path
from .io_utils import digest, read_json, rows, write_json, write_rows
from .runtime_config import BASE, configure


def ingest():
    from .neo import NeoStore
    from .quality import quality
    configure()
    store = NeoStore()
    try:
        result = {'uri': os.environ['NEO4J_URI'], 'return_1': store.run('RETURN 1 AS ok'),
                  'version': store.run('CALL dbms.components() YIELD name,versions,edition RETURN name,versions,edition'),
                  'before': store.run('MATCH (n) RETURN count(n) AS all_nodes')}
        original = rows(BASE/'data/index/chunks.jsonl')
        ids = sorted(c['chunk_id'] for c in original)
        result['original_ids_hash'] = digest(ids)
        pending = [dict(c, **quality(c)) for c in original if not quality(c)['retrieval_eligible']]
        write_rows(BASE/'data/ocr-pending.jsonl', pending)
        snapshots = []
        for iteration in (1, 2):
            manifest = store.ingest(BASE/'data/index')
            indexed_property = 'retrieval_'+manifest['index_id']
            found = store.run('MATCH (c:RetrievalChunk) WHERE c.chunk_id IN $ids '
                f'RETURN c.chunk_id AS id,c.retrieval_eligible AS eligible,size(c.{indexed_property}_raw) AS raw_dimension', ids=ids)
            assert sorted(v['id'] for v in found) == ids
            assert all(v['raw_dimension'] == manifest['dimension'] for v in found)
            snapshots.append({'iteration': iteration, 'count': len(found), 'ids_hash': digest(sorted(v['id'] for v in found)),
                              'eligible': sum(v['eligible'] is True for v in found), 'pending_ocr': len(pending)})
        assert snapshots[0]['count'] == snapshots[1]['count'] == 411
        assert snapshots[0]['ids_hash'] == snapshots[1]['ids_hash']
        result['imports'] = snapshots
        result['indexes'] = store.run('SHOW VECTOR INDEXES YIELD name,state,populationPercent,options '
                                      'WHERE name=$name RETURN name,state,populationPercent,options', name=indexed_property)
        assert result['indexes'][0]['state'] == 'ONLINE'
        result['source_count'] = store.run('MATCH (s:RetrievalSource) RETURN count(s) AS count')
        result['after'] = store.run('MATCH (n) RETURN count(n) AS all_nodes')
        write_json(BASE/'data/acceptance/ingest.json', result)
        print(json.dumps({'return_1': 1, 'imports': snapshots, 'index': result['indexes'][0]['state']}, ensure_ascii=False))
    finally:
        store.close()


def http(base_url):
    import httpx
    configure()
    request = {'symptoms': '口渴，喜冷饮', 'tongue_features': '舌红，苔黄而干', 'top_k': 5, 'candidate_count': 40}
    headers = {'X-Admin-Token': os.environ['RETRIEVAL_ADMIN_TOKEN']}
    with httpx.Client(base_url=base_url, timeout=120, trust_env=False) as client:
        health = client.get('/health')
        health.raise_for_status()
        response = client.post('/v1/retrieve', json=request)
        response.raise_for_status()
        result = response.json()
        assert result['backend'] == 'neo4j' and len(result['evidence']) == 5
        for chunk in result['evidence']:
            assert chunk['location']['pdf_page'] not in {57,64}
            source = client.get('/v1/admin/chunks/'+chunk['chunk_id'], headers=headers)
            source.raise_for_status()
            assert source.json()['text'] == chunk['text'] and source.json()['location'] == chunk['location']
        graph = client.get('/v1/admin/graph', headers=headers)
        graph.raise_for_status()
        candidates = client.get('/v1/admin/candidates', headers=headers)
        candidates.raise_for_status()
        test_graph = client.get('/v1/admin/graph', params={'include_test': 'true', 'chunk_id': 'retrieval-acceptance-test-v1'}, headers=headers)
        test_graph.raise_for_status()
        public_graph = client.get('/v1/graph')
        public_graph.raise_for_status()
        assert all(not e['evidence'].get('is_demo') for e in public_graph.json()['relations'])
        assert any(e['evidence'].get('is_demo') is True for e in test_graph.json()['edges'])
        assert all(r['relation']['approved'] is True for r in graph.json()['edges'])
        report = {'url': base_url+'/v1/retrieve', 'status_code': response.status_code, 'request': request, 'response': result,
                  'source_lookup': 'All 5 text/location pairs matched Neo4j admin chunk lookups',
                  'admin_graph': graph.json(), 'candidates': candidates.json(),
                  'admin_test_graph': test_graph.json(), 'public_graph': public_graph.json()}
        write_json(BASE/'data/acceptance/http.json', report)
        print(json.dumps({'http': response.status_code, 'backend': result['backend'], 'count': len(result['evidence']),
                          'top_chunk': result['evidence'][0]['chunk_id'], 'location': result['evidence'][0]['location'],
                          'published_relations': len(graph.json()['edges']), 'pending_candidates': len(candidates.json()['items'])}, ensure_ascii=False))


def test_graph():
    import numpy as np
    from .graph import import_reviewed, review, validate_candidate
    from .neo import NeoStore
    configure()
    out = BASE/'data/acceptance/test-fixture'
    out.mkdir(parents=True, exist_ok=True)
    chunk = {'chunk_id': 'retrieval-acceptance-test-v1', 'text': '独立发布测试：测试头实体通过测试关系连接测试尾实体。',
             'source_title': '独立验收测试数据（非教材）', 'pdf_sha256': 'retrieval-acceptance-test-v1',
             'edition': '合成测试', 'location': {'chapter': '合成测试', 'pdf_page': None, 'printed_page': None, 'paragraph': None},
             'is_demo': True}
    write_rows(out/'chunks.jsonl', [chunk])
    vector = np.load(BASE/'data/index/vectors.npy', allow_pickle=False)[:1]
    np.save(out/'vectors.npy', vector)
    from .io_utils import file_hash
    manifest = {'corpus_hash': digest([chunk]), 'embedding_identity': 'SYNTHETIC-ACCEPTANCE-ONLY',
                'embedding': 'SYNTHETIC-ACCEPTANCE-ONLY', 'dimension': 512, 'count': 1,
                'vectors_hash': file_hash(out/'vectors.npy')}
    manifest['index_id'] = digest(manifest)[:24]
    write_json(out/'manifest.json', manifest)
    candidate = dict(subject='测试头实体', predicate='测试关系', object='测试尾实体', quote=chunk['text'],
                     chunk_id=chunk['chunk_id'], source_hash=digest(chunk), status='pending', reviewer=None, reviewed_at=None,
                     is_demo=True)
    candidate['candidate_id'] = validate_candidate(candidate, {chunk['chunk_id']: chunk})
    write_rows(out/'candidates.jsonl', [candidate])
    store = NeoStore()
    try:
        store.ingest(out)
        pending = import_reviewed(store, out/'chunks.jsonl', out/'candidates.jsonl')
        assert store.graph(chunk['chunk_id'], include_test=True) == []
        review(out/'candidates.jsonl', candidate['candidate_id'], 'approved', '自动流程验收（仅合成测试，非医学审核）')
        published = import_reviewed(store, out/'chunks.jsonl', out/'candidates.jsonl')
        import_reviewed(store, out/'chunks.jsonl', out/'candidates.jsonl')
        found = store.graph(chunk['chunk_id'], include_test=True)
        assert len(found) == 1 and found[0]['evidence']['is_demo'] is True
        assert found[0]['relation']['quote'] in found[0]['evidence']['text']
        assert found[0]['relation']['chunk_id'] == found[0]['evidence']['chunk_id'] == chunk['chunk_id']
        assert store.graph(chunk['chunk_id']) == []
        review(out/'candidates.jsonl', candidate['candidate_id'], 'rejected', '自动撤销验收（仅合成测试）')
        import_reviewed(store, out/'chunks.jsonl', out/'candidates.jsonl')
        assert store.graph(chunk['chunk_id'], include_test=True) == []
        review(out/'candidates.jsonl', candidate['candidate_id'], 'approved', '自动流程验收（仅合成测试，非医学审核）')
        import_reviewed(store, out/'chunks.jsonl', out/'candidates.jsonl')
        write_json(BASE/'data/acceptance/publication.synthetic.json', {'is_demo': True, 'pending_import': pending,
                   'approved_import': published, 'queried_relation': found, 'repeated_import_count': len(found), 'revoke_verified': True,
                   'production_exclusion_verified': True})
        print('Synthetic publication: pending excluded, approved queryable, revoke verified, production excluded')
    finally:
        store.close()


def publish(review_file=None):
    from .graph import import_reviewed
    from .neo import NeoStore
    configure()
    store = NeoStore()
    try:
        result = import_reviewed(store, BASE/'data/textbook/chunks.jsonl', review_file or BASE/'data/qwen-batch/candidates.jsonl')
        write_json(BASE/'data/acceptance/real-publication.json', result)
        print(json.dumps(result))
    finally:
        store.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['ingest','http','test-graph','publish'])
    parser.add_argument('--base-url', default='http://127.0.0.1:8011')
    parser.add_argument('--review-file', type=Path)
    args = parser.parse_args()
    if args.action == 'ingest':
        ingest()
    elif args.action == 'test-graph':
        test_graph()
    elif args.action == 'publish':
        publish(args.review_file)
    else:
        http(args.base_url)
