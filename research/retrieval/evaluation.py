import statistics
import time
from .core import model_identity, query_text
from .io_utils import digest, rows, write_json


def validate_labels(values, chunks, require_review=True):
    seen, queries, symptom_splits = set(), set(), {}
    for v in values:
        if v['query_id'] in seen:
            raise ValueError('Duplicate query ID')
        seen.add(v['query_id'])
        query = query_text(v['symptoms'], v.get('tongue_features'))
        if query in queries:
            raise ValueError('Duplicate queries across splits')
        queries.add(query)
        if v.get('split') not in {'train', 'validation', 'test'}:
            raise ValueError('Explicit train/validation/test split required')
        symptom_key = ''.join(v['symptoms'].split())
        if symptom_key in symptom_splits and symptom_splits[symptom_key] != v['split']:
            raise ValueError('Symptom-only query overlaps held-out split')
        symptom_splits[symptom_key] = v['split']
        if require_review and (v.get('human_verified') is not True or not isinstance(v.get('reviewer'), str) or not v['reviewer'].strip()):
            raise ValueError('Human-verified labels and reviewer required')
        positives, negatives = set(v['relevant_chunk_ids']), set(v['hard_negative_chunk_ids'])
        if not positives or positives & negatives or not (positives | negatives) <= chunks.keys():
            raise ValueError('Invalid positive/negative chunk IDs')


def metrics(ranked, relevant, k):
    ranked = ranked[:k]
    return {'recall': len(set(ranked) & set(relevant))/len(set(relevant)),
            'rr': next((1/i for i, cid in enumerate(ranked, 1) if cid in relevant), 0)}


def evaluate(index, models, labels, output, k=5, candidate_count=40, split='test', allow_demo=False):
    values = rows(labels)
    chunks = {c['chunk_id']: c for c in index.chunks} if hasattr(index, 'chunks') else None
    if chunks is None:
        raise ValueError('Evaluation uses frozen local index; run with --backend local')
    validate_labels(values, chunks, require_review=not allow_demo)
    if allow_demo and not all(v.get('is_demo') for v in values):
        raise ValueError('--allow-demo only accepts explicitly synthetic labels')
    selected = [v for v in values if v['split'] == split]
    if split == 'train' or not selected or not 1 <= k <= candidate_count:
        raise ValueError('Use nonempty held-out split and k <= candidate_count')
    # Warm both paths. Model startup is excluded; measured latency includes query encoding and reranking.
    for with_tongue in (False, True):
        q = query_text(selected[0]['symptoms'], selected[0].get('tongue_features') if with_tongue else None)
        models.rank(q, index.candidates(q, candidate_count), k)
    report = {'is_demo': allow_demo, 'split': split, 'labels_hash': digest(values),
              'index': index.manifest, 'embedding': models.embedding_name, 'reranker': models.reranker_name,
              'candidate_count': candidate_count, 'k': k, 'modes': {}}
    report['reranker_identity'] = 'SYNTHETIC-CONTRACT-ONLY' if allow_demo else model_identity(models.reranker_name)
    for mode in ('symptoms', 'symptoms+tongue'):
        results = []
        for v in selected:
            q = query_text(v['symptoms'], v.get('tongue_features') if mode.endswith('tongue') else None)
            start = time.perf_counter()
            candidates = index.candidates(q, candidate_count)
            ranked = models.rank(q, candidates, k)
            elapsed = (time.perf_counter()-start)*1000
            scores = metrics([c['chunk_id'] for c in ranked], v['relevant_chunk_ids'], k)
            baseline = metrics([c['chunk_id'] for c in candidates], v['relevant_chunk_ids'], k)
            results.append(dict(scores, vector_recall=baseline['recall'], vector_rr=baseline['rr'], query_id=v['query_id'],
                                elapsed_ms=elapsed, ranked_ids=[c['chunk_id'] for c in ranked]))
        report['modes'][mode] = {'recall_at_k': statistics.mean(r['recall'] for r in results),
            'mrr_at_k': statistics.mean(r['rr'] for r in results),
            'vector_recall_at_k': statistics.mean(r['vector_recall'] for r in results),
            'vector_mrr_at_k': statistics.mean(r['vector_rr'] for r in results),
            'mean_ms': statistics.mean(r['elapsed_ms'] for r in results), 'queries': results}
    write_json(output, report)
    return report
