"""Convert only train/val positives. Unannotated classes remain unknown."""
import argparse
import hashlib
import json
from pathlib import Path
import yaml

def convert(config_path, output):
    config = yaml.safe_load(Path(config_path).read_text(encoding='utf-8'))
    names = config['names']
    names = [names[i] for i in range(len(names))] if isinstance(names, dict) else names
    if names != ['hongshe', 'zishe', 'liewenshe', 'chihenshe', 'baitaishe', 'huangtaishe', 'heitaishe']:
        raise ValueError('Unexpected YAML class map')
    root = Path(config['path'])
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    seen = set()
    counts = {}
    for split in ('train', 'val'):
        rows = []
        for image in sorted((root / config[split]).rglob('*')):
            if image.suffix.lower() not in ('.jpg', '.png', '.jpeg', '.bmp', '.webp'):
                continue
            label = root / split / 'labels' / image.with_suffix('.txt').name
            if not label.is_file():
                raise ValueError(f'Missing label: {label}')
            positive = set()
            for line in label.read_text().splitlines():
                fields = line.split()
                if len(fields) != 5:
                    raise ValueError(f'Invalid detection: {label}')
                cid = int(fields[0])
                if cid not in range(len(names)) or any(not 0 <= float(v) <= 1 for v in fields[1:]):
                    raise ValueError(f'Invalid class or coordinates: {label}')
                positive.add(cid)
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            if split == 'val' and digest in seen:
                raise ValueError('Train/val image leakage')
            if split == 'train':
                seen.add(digest)
            target = {'annotated_attributes': [names[i] for i in sorted(positive)],
                      'unknown_attributes': [n for i, n in enumerate(names) if i not in positive]}
            rows.append({'case_id': image.stem, 'split': split, 'image': str(image.resolve()),
                         'image_sha256': digest, 'symptoms': None, 'reference': target,
                         'reference_kind': 'detection_annotations', 'is_simulated': False})
        (output / f'{split}.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows), encoding='utf-8')
        counts[split] = len(rows)
    (output / 'manifest.json').write_text(json.dumps({'counts': counts, 'names': names,
        'test_used': False, 'negative_labels_created': False}, indent=2), encoding='utf-8')
    return counts

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data', default='research/datasets/clean_v2/data.yaml')
    p.add_argument('--output', default='research/multimodal/data/recognition')
    a = p.parse_args()
    print(convert(a.data, a.output))
