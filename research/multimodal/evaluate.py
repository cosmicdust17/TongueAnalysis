"""Same paired validation cohort, all three modalities, three experiment groups."""
import argparse
import hashlib
import json
from pathlib import Path
from runtime import Engine
from train import read_rows, validate_rows

def evaluate(a):
    rows = read_rows(a.cases)
    validate_rows(rows, 'joint', 'val')
    ids = [r['case_id'] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate paired case IDs')
    cohort = hashlib.sha256(Path(a.cases).read_bytes()).hexdigest()
    out = Path(a.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Append each result immediately so GPU/OOM interruptions retain completed cases.
    with out.open('w', encoding='utf-8') as f:
        for group, adapter in [('baseline', None), ('recognition', a.recognition_adapter), ('joint', a.joint_adapter)]:
            engine = Engine(adapter)
            for row in rows:
                for mode in ('image', 'symptoms', 'both'):
                    try:
                        r = engine.infer(row['image'], row['symptoms'], [], [], mode)
                        reference = row['reference']
                        text = r.get('output', {}).get('analysis', '')
                        # Character bigram F1 is descriptive overlap, never clinical correctness.
                        grams = lambda s: {s[i:i+2] for i in range(max(0, len(s)-1))}
                        pred, gold = grams(text), grams(reference['analysis'])
                        score = 2*len(pred & gold)/(len(pred)+len(gold)) if pred or gold else 1.0
                        r.update(character_bigram_f1=score, reference=reference)
                    except Exception as exc:
                        r = {'status': 'failed', 'error': str(exc)}
                    r.update(group=group, mode=mode, case_id=row['case_id'], cohort_sha256=cohort)
                    f.write(json.dumps(r, ensure_ascii=False)+'\n')
                    f.flush()
            del engine
            import gc, torch
            gc.collect()
            torch.cuda.empty_cache()

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--cases', required=True)
    p.add_argument('--recognition-adapter', required=True)
    p.add_argument('--joint-adapter', required=True)
    p.add_argument('--output', default='research/multimodal/results/paired-evaluation.jsonl')
    evaluate(p.parse_args())
