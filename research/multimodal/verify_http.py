"""Real local GPU model through the FastAPI upload route; no production database."""
import json
import os
import sys
from pathlib import Path
from fastapi.testclient import TestClient

root = Path(__file__).resolve().parents[2]
os.environ['MODEL_MODE'] = 'qwen'
os.environ.setdefault('MODEL_DEVICE', 'cpu')
os.environ.setdefault('YOLO_CONFIG_DIR', str(root/'research/multimodal/results/yolo-settings'))
Path(os.environ['YOLO_CONFIG_DIR']).mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(root/'model-service'))
from app import app

if __name__ == '__main__':
    sample = json.loads((root/'research/multimodal/data/recognition/val.jsonl').read_text(encoding='utf-8').splitlines()[0])
    key = os.getenv('MODEL_API_KEY', '')
    headers = {'Authorization': 'Bearer '+key} if key else {}
    with TestClient(app) as client:
        health = client.get('/health', headers=headers)
        assert health.status_code == 200 and health.json()['ready'], health.text
        results = {}
        for mode in ('image', 'symptoms', 'both'):
            with Path(sample['image']).open('rb') as image:
                response = client.post('/v1/infer', files={'image': ('image.jpg', image, 'image/jpeg')},
                    data={'symptoms': '近一周口干，睡眠欠佳' if mode != 'image' else '',
                          'mode': mode, 'evidence': '[]'}, headers=headers)
            assert response.status_code == 200, response.text
            result = response.json()
            assert result['fusion_result']['qwen']['status'] == 'valid'
            assert result['fusion_result']['qwen']['output']['cited_chunk_ids'] == []
            results[mode] = result
            print(json.dumps({'mode': mode, 'qwen': result['fusion_result']['qwen']}, ensure_ascii=False))
        (root/'research/multimodal/results/http-smoke.json').write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
