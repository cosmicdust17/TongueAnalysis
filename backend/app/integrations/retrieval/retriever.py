"""Replaceable lexical entity linker and two-hop graph retrieval baseline."""
import re
from app.repositories.graph_repository import graph_repository
from app.core.config import settings

def retrieve_evidence(result, symptoms: str, limit=5):
    if not settings().knowledge_retrieval_enabled:
        return []
    data = graph_repository().all()
    sources = {s['id']: s for s in data['sources']}
    nodes = {n['id']: n for n in data['nodes'] if n['status'] == 'published' and n['source_id'] in sources}
    terms = [f.value.replace('（模拟）', '') for f in result.tongue_features]
    raw_query_terms = result.fusion_result.get('query_terms', [])
    if isinstance(raw_query_terms, list):
        terms += [t[:100] for t in raw_query_terms[:30] if isinstance(t, str) and t.strip()]
    query = symptoms + ' ' + ' '.join(terms)
    scores, paths = {}, {}
    for nid, n in nodes.items():
        matches = [name for name in [n['name'], *n.get('aliases', [])] if name and name in query]
        if matches:
            scores[nid] = sum(len(x) for x in set(matches))
            paths[nid] = []
    # Only published edges with explicit provenance and published endpoints enter evidence.
    relations = [r for r in data['relations'] if r['status'] == 'published' and r['source'] in nodes and r['target'] in nodes and r['source_id'] in sources]
    for _ in range(2):
        prior = dict(scores)
        for r in relations:
            for a, b in [(r['source'], r['target']), (r['target'], r['source'])]:
                candidate = prior.get(a, 0) * .5
                if candidate > scores.get(b, 0):
                    scores[b] = candidate
                    paths[b] = [*paths.get(a, []), dict(r, citation=sources[r['source_id']]['citation'], source_title=sources[r['source_id']]['title'], is_demo=bool(r.get('is_demo') or sources[r['source_id']].get('is_demo')))]
    # Transparent baseline re-ranking; scores are ranking weights, not probabilities.
    ranked = sorted(scores, key=lambda k: (-scores[k], k))[:limit]
    evidence = []
    for nid in ranked:
        n = nodes[nid]
        source = sources[n['source_id']]
        evidence.append({'entity_id': nid, 'title': n['name'], 'kind': n['kind'],
            'text': n['text'], 'source_id': source['id'], 'source_title': source['title'],
            'citation': source['citation'], 'score': scores[nid], 'path': paths.get(nid, []),
            'is_demo': bool(n.get('is_demo') or source.get('is_demo') or any(p.get('is_demo') for p in paths.get(nid, []))),
            'entity_updated_at': n.get('updated_at')})
    return evidence
