"""Synthetic pipeline demonstration. Does not load BGE, read the textbook, or publish medical knowledge."""
from pathlib import Path
import numpy as np
from .core import LocalIndex, build_vectors, retrieve
from .evaluation import evaluate
from .io_utils import digest, write_json, write_rows


class SyntheticModels:
    embedding_name = reranker_name = identity = 'SYNTHETIC-CONTRACT-ONLY'

    def encode(self, texts, **kwargs):
        vectors = np.array([[t.count('寒')+1, t.count('热')+1, t.count('渴')+1] for t in texts], dtype=float)
        return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

    def rank(self, query, candidates, k):
        return sorted([dict(c, score=float(len(set(query) & set(c['text'])))) for c in candidates],
                      key=lambda c: -c['score'])[:k]


def main():
    out = Path('research/retrieval/samples')
    chunks = [dict(chunk_id=f'demo-{i}', text=t, source_title='合成测试资料（非教材）', edition=None,
                   location={'chapter': '测试', 'pdf_page': None, 'printed_page': None, 'paragraph': None}, is_demo=True)
              for i, t in enumerate(['测试寒象：畏寒，舌淡。', '测试热象：口渴，舌红。', '测试无关段落。'])]
    write_rows(out/'chunks.synthetic.jsonl', chunks)
    labels = [dict(query_id=f'demo-{i}', split=split, symptoms=symptom, tongue_features=tongue,
                   relevant_chunk_ids=[positive], hard_negative_chunk_ids=[negative], human_verified=False,
                   reviewer=None, is_demo=True) for i, (split, symptom, tongue, positive, negative) in enumerate([
                       ('train', '测试寒', '舌淡', 'demo-0', 'demo-1'),
                       ('validation', '测试口渴', '舌红', 'demo-1', 'demo-0'),
                       ('test', '测试畏寒', '舌淡', 'demo-0', 'demo-1'),
                       ('test', '测试热与渴', '舌红', 'demo-1', 'demo-0')])]
    write_rows(out/'labels.synthetic.jsonl', labels)
    model = SyntheticModels()
    build_vectors(out/'chunks.synthetic.jsonl', 'research/retrieval/data/demo-index', model)
    index = LocalIndex('research/retrieval/data/demo-index', model)
    write_json(out/'response.synthetic.json', dict(retrieve(index, model, '测试畏寒', '舌淡', 3, 2), is_demo=True))
    evaluate(index, model, out/'labels.synthetic.jsonl', out/'evaluation.synthetic.json', 2, 3, allow_demo=True)
    candidate = dict(subject='测试寒象', predicate='测试表现', object='畏寒', quote='畏寒', chunk_id='demo-0')
    from .graph import validate_candidate
    candidate.update(candidate_id=validate_candidate(candidate, {'demo-0': chunks[0]}),
                     status='pending', reviewer=None, reviewed_at=None, source_hash=digest(chunks[0]), is_demo=True)
    write_rows(out/'candidates.synthetic.jsonl', [candidate])
    print('Synthetic fixtures written: 3 chunks, 4 queries, 1 pending candidate. Not a BGE quality evaluation.')


if __name__ == '__main__':
    main()
