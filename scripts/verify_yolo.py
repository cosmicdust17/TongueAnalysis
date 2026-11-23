"""Upload a real photo through the running backend and reopen its persisted report."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import monotonic, sleep

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.core.database import SessionLocal, engine
from app.models import Analysis, Report, StoredFile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', type=Path, required=True)
    args = parser.parse_args()
    photo = args.image.resolve()
    assert photo.is_file()
    weights = ROOT / 'research/results/formal/clean-v1-yolo11n-seed42/weights/best.pt'
    sha = hashlib.sha256(weights.read_bytes()).hexdigest()
    with httpx.Client(base_url='http://127.0.0.1:8000', timeout=120, trust_env=False) as client:
        health = client.get('/health')
        health.raise_for_status()
        assert health.json()['model_provider'] == 'http'
        session = client.post('/api/v1/auth/dev-login', json={'role': 'user'})
        session.raise_for_status()
        headers = {'Authorization': 'Bearer ' + session.json()['access_token']}

        def request(method, path, **kwargs):
            r = client.request(method, '/api/v1' + path, headers=headers, **kwargs)
            r.raise_for_status()
            return r

        fid = request('POST', '/uploads', files={'file': ('real-photo.jpg', photo.read_bytes(), 'image/jpeg')}).json()['id']
        aid = request('POST', '/analyses', json={'image_id': fid, 'symptoms': '实拍舌象图，YOLO内部联调记录', 'duration': '近一周'}).json()['id']
        end = monotonic() + 120
        while monotonic() < end:
            task = request('GET', '/analyses/' + aid).json()
            if task['status'] == 'completed':
                break
            assert task['status'] != 'failed', 'Real inference task failed'
            sleep(.5)
        else:
            raise RuntimeError('Real inference timed out')
        rid = task['report_id']
        report = request('GET', '/reports/' + rid).json()
        assert report['is_demo'] is False
        assert report['content']['model_version'].endswith(sha[:12])
        assert report['content']['evidence_status'] == 'disabled'
        assert any(item['id'] == rid for item in request('GET', '/reports').json()['items'])
        assert request('GET', '/reports/' + rid).json() == report
        assert request('GET', f'/reports/{rid}/pdf').content.startswith(b'%PDF-')
        assert request('GET', f'/uploads/{fid}/content').status_code == 200
        with SessionLocal() as db:
            row = db.get(Analysis, aid)
            assert db.get(Report, rid).content == report['content']
            assert Path(db.get(StoredFile, fid).path).is_file()
            result = row.result
            fusion = result['fusion_result']
            assert fusion['weights_sha256'] == sha and fusion['imgsz'] == 640 and fusion['conf'] == .218
            fissure = any(d['class_id'] == 2 for d in fusion['detections'])
            if not fissure:
                assert any(f['value'] == '未检出裂纹特征' for f in report['content']['tongue_features'])
            record = {'report_id': rid, 'analysis_id': aid, 'image_id': fid,
                      'model_version': result['model_version'], 'weights_sha256': sha,
                      'imgsz': 640, 'conf': .218, 'is_demo': report['is_demo'],
                      'detections': len(fusion['detections']), 'fissure_detected': fissure,
                      'checks': ['real photo upload', 'HTTP YOLO inference', 'MySQL persistence', 'history reopen', 'PDF']}
        (ROOT / 'storage/yolo-integration-check.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(record, ensure_ascii=True))
    engine.dispose()


if __name__ == '__main__':
    main()
