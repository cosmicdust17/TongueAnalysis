"""Run a real-model POST against the standalone app, saving full results only locally."""
import argparse
from pathlib import Path
from fastapi.testclient import TestClient
from .core import LocalIndex, Models
from .io_utils import write_json
from .service import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--index', default='research/retrieval/data/index')
    parser.add_argument('--models', default='research/retrieval/models')
    parser.add_argument('--out', default='research/retrieval/data/verification')
    args = parser.parse_args()
    models = Models(str(Path(args.models)/'bge-small-zh-v1.5'), str(Path(args.models)/'bge-reranker-base'))
    models.load_reranker()
    index = LocalIndex(args.index, models)
    with TestClient(create_app(index, models)) as client:
        for name, body in [('symptoms', {'symptoms': '口渴，喜冷饮'}),
                           ('symptoms-tongue', {'symptoms': '口渴，喜冷饮', 'tongue_features': '舌红，苔黄而干'})]:
            response = client.post('/v1/retrieve', json=dict(body, top_k=5, candidate_count=40))
            response.raise_for_status()
            result = response.json()
            assert len(result['evidence']) == 5
            assert all(v['chunk_id'].startswith('ch_') and not v['is_demo'] for v in result['evidence'])
            write_json(Path(args.out)/f'{name}.json', {'request': body, 'response': result,
                'quality_evaluation': False, 'note': '真实模型和教材接口连通性检查；未经人工相关性标注，不能解读为质量评估。'})
            print(name, 'HTTP', response.status_code, 'evidence', len(result['evidence']),
                  'ms', result['elapsed_ms'], 'top', result['evidence'][0]['chunk_id'],
                  'location', result['evidence'][0]['location']['pdf_page'])


if __name__ == '__main__':
    main()
