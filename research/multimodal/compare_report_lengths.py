"""Compare Qwen generation budgets on the same real report inputs."""
import json
import os
from pathlib import Path

from runtime import Engine

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'research/multimodal/results/fissure-regression'

if __name__ == '__main__':
    engine = Engine()
    results = []
    for case, profiles in [('22_S3663', ('full', 'compact')), ('27_S3038', ('compact', 'full'))]:
        record = json.loads((OUT / 'current' / (case + '.json')).read_text(encoding='utf-8'))
        image = ROOT / 'research/results/fissure_review/candidates' / case / 'original.jpg'
        detections = record['raw_result']['fusion_result']['detections']
        chunks = record['evidence']['items']
        for profile in profiles:
            os.environ['QWEN_MAX_NEW_TOKENS'] = '512' if profile == 'full' else '128'
            # Keep evidence verbatim and use exactly the same approved chunks in both runs.
            features = detections if profile == 'full' else [
                {'class_name': d['class_name']} for d in detections]
            result = engine.infer(str(image), record['symptoms'], features, chunks, 'both')
            result.update(case=case, profile=profile, provided_chunk_ids=[c['chunk_id'] for c in chunks])
            results.append(result)
            print(json.dumps({'case': case, 'profile': profile, 'status': result['status'],
                              'metrics': result['metrics']}, ensure_ascii=False), flush=True)
    (OUT / 'qwen-lengths.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
