import argparse
import importlib.util
import json
import os
import time
import traceback
from pathlib import Path
from contracts import retrieve
from runtime import Engine

ROOT = Path(__file__).resolve().parents[2]

def detector():
    os.environ.setdefault('YOLO_CONFIG_DIR', str(ROOT / 'research/multimodal/results/yolo-settings'))
    Path(os.environ['YOLO_CONFIG_DIR']).mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location('tongue_detector', ROOT / 'model-service/predictor.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = module.Predictor()
    model.load()
    return model

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--image')
    p.add_argument('--symptoms', default='')
    p.add_argument('--mode', choices=['image', 'symptoms', 'both'], default='both')
    p.add_argument('--adapter')
    p.add_argument('--retrieval-url', default=os.getenv('RETRIEVAL_BASE_URL', ''))
    p.add_argument('--output', default='research/multimodal/results/baseline.json')
    a = p.parse_args()
    result = {'status': 'failed', 'stage': 'load', 'parameters': vars(a)}
    started = time.perf_counter()
    try:
        engine = Engine(a.adapter)
        result['load_seconds'] = time.perf_counter()-started
        detected = detector().analyze(a.image, '') if a.mode != 'symptoms' else None
        detections = detected['fusion_result']['detections'] if detected else []
        features = [f for f in detected['tongue_features'] if f['confidence'] is not None] if detected else []
        status, chunks = retrieve(a.retrieval_url, a.symptoms if a.mode != 'image' else '', features)
        result['stage'] = 'inference'
        result.update(engine.infer(a.image, a.symptoms, detections, chunks, a.mode))
        ids = result.get('output', {}).get('cited_chunk_ids', [])
        result.update(evidence_status=status, evidence=[c for c in chunks if c['chunk_id'] in ids],
                      yolo_detections=detections,
                      detector_metadata=detected['fusion_result'] if detected else None)
    except Exception:
        result['traceback'] = traceback.format_exc()
        raise
    finally:
        result['total_seconds'] = time.perf_counter()-started
        Path(a.output).parent.mkdir(parents=True, exist_ok=True)
        Path(a.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
