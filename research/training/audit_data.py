"""Read-only TXT dataset audit. Outputs never enter the source dataset."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import random
from PIL import Image, ImageDraw, ImageOps
from common import ROOT, DATA_ROOT, classes, digest, write_json

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.webp'}

def parse_label(text, nc=21):
    boxes, errors = [], []
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            fields = line.split()
            if len(fields) != 5:
                raise ValueError('expected five fields')
            cid = int(fields[0])
            x, y, w, h = map(float, fields[1:])
            if not 0 <= cid < nc:
                raise ValueError('class ID outside mapping')
            if not all(math.isfinite(v) for v in (x, y, w, h)):
                raise ValueError('nonfinite coordinate')
            if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1):
                raise ValueError('coordinate outside normalized range')
            if min(x-w/2, y-h/2) < -1e-6 or max(x+w/2, y+h/2) > 1+1e-6:
                raise ValueError('box crosses image boundary')
            box = [cid, x, y, w, h]
            if box in boxes:
                raise ValueError('duplicate annotation row')
            boxes.append(box)
        except ValueError as exc:
            errors.append(dict(line=line_no, reason=str(exc), text=line))
    return boxes, errors

def audit(source, output, patient_csv=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or source in output.parents:
        raise ValueError('Output must be outside source dataset')
    candidates = [p for p in source.rglob('*') if p.is_dir() and 'txt' in p.name.lower()
                  and all((p/s/'images').is_dir() and (p/s/'labels').is_dir() for s in ('train','val','test'))]
    if len(candidates) != 1:
        raise ValueError(f'Expected one TXT dataset root; found {len(candidates)}')
    data = candidates[0]
    class_files = sorted(source.rglob('classes.txt'))
    if not class_files:
        raise ValueError('No local classes.txt found')
    names = classes(class_files[0])
    mappings = {str(p):p.read_text(encoding='utf-8-sig').splitlines() for p in class_files}
    class_conflicts = [str(p) for p in class_files if mappings[str(p)] != names]
    patients = {}
    if patient_csv:
        with open(patient_csv, encoding='utf-8-sig', newline='') as f:
            for row in csv.DictReader(f):
                key = row['image_relative_path'].replace('\\', '/')
                if key in patients or not row['patient_id'].strip():
                    raise ValueError('Invalid or duplicate patient mapping')
                patients[key] = row['patient_id'].strip()
    rows, orphan_labels, summary = [], [], {}
    for split in ('train','val','test'):
        images = sorted(p for p in (data/split/'images').rglob('*') if p.suffix.lower() in IMAGE_EXTS)
        expected, stems = set(), Counter()
        for p in images:
            rel = p.relative_to(data/split/'images')
            label = data/split/'labels'/rel.with_suffix('.txt')
            expected.add(label)
            stems[str(rel.with_suffix(''))] += 1
            row = dict(split=split, image=str(p), label=str(label), relative=str(p.relative_to(data)),
                       errors=[], boxes=[], patient_id=patients.get(str(p.relative_to(data)).replace('\\','/')))
            row['sha256'] = digest(p)
            try:
                with Image.open(p) as im:
                    im.load()
                    rgb = im.convert('RGB')
                    row['size'] = list(rgb.size)
                    row['pixel_sha256'] = hashlib.sha256(str(rgb.size).encode()+rgb.tobytes()).hexdigest()
                    if im.getexif().get(274, 1) != 1:
                        row['errors'].append('EXIF orientation requires annotation review')
            except Exception as exc:
                row['errors'].append('image decode failed: '+str(exc))
            if not label.exists():
                row['label_status'] = 'missing'
                row['errors'].append('missing label; not a negative sample')
            else:
                try:
                    row['label_sha256'] = digest(label)
                    boxes, errors = parse_label(label.read_text(encoding='utf-8-sig'))
                    row['boxes'] = boxes
                    row['errors'].extend(errors)
                    row['label_status'] = 'invalid' if errors else ('valid' if boxes else 'empty')
                except Exception as exc:
                    row['label_status'] = 'invalid'
                    row['errors'].append('label read failed: '+str(exc))
            rows.append(row)
        ambiguous = {s for s,n in stems.items() if n > 1}
        for row in rows:
            if row['split'] == split and str(Path(row['image']).relative_to(data/split/'images').with_suffix('')) in ambiguous:
                row['errors'].append('multiple images share one label stem')
        orphan_labels.extend(str(p) for p in (data/split/'labels').rglob('*.txt') if p not in expected)
        selected = [r for r in rows if r['split'] == split]
        summary[split] = dict(images=len(selected), label_status=dict(Counter(r['label_status'] for r in selected)),
                              images_with_errors=sum(bool(r['errors']) for r in selected))
        print(f'Audited {split}: {len(selected)} images', flush=True)
    duplicates, patient_leaks = [], []
    for key in ('sha256','pixel_sha256'):
        groups = defaultdict(list)
        for row in rows:
            if row.get(key): groups[row[key]].append(row)
        for hash_value, group in groups.items():
            if len(group) > 1:
                duplicates.append(dict(kind=key, hash=hash_value, images=[r['relative'] for r in group],
                    cross_split=len({r['split'] for r in group}) > 1,
                    annotation_conflict=len({json.dumps(sorted(r['boxes'])) for r in group}) > 1))
    by_patient = defaultdict(list)
    for r in rows:
        if r['patient_id']: by_patient[r['patient_id']].append(r)
    for pid, group in by_patient.items():
        if len({r['split'] for r in group}) > 1:
            patient_leaks.append(dict(patient_id=pid, images=[r['relative'] for r in group]))
    blockers = []
    if class_conflicts: blockers.append('Class mapping conflicts')
    if any(r['errors'] for r in rows): blockers.append('Invalid images or missing/invalid labels')
    if orphan_labels: blockers.append('Orphan labels need review')
    if any(d['cross_split'] for d in duplicates): blockers.append('Cross-split exact image leakage')
    if any(d['annotation_conflict'] for d in duplicates): blockers.append('Identical images have numerically different parsed annotations; review required')
    if patient_leaks: blockers.append('Cross-split patient leakage')
    if patient_csv and any(not r['patient_id'] for r in rows): blockers.append('Incomplete patient mapping')
    counts = []
    for split in summary:
        selected = [r for r in rows if r['split'] == split]
        for cid, name in enumerate(names):
            counts.append(dict(split=split, class_id=cid, name=name,
                images=sum(any(b[0] == cid for b in r['boxes']) for r in selected),
                boxes=sum(b[0] == cid for r in selected for b in r['boxes'])))
    report = dict(source=str(source), txt_root=str(data), class_files=[str(p) for p in class_files], class_mappings=mappings,
                  names=names, class_conflicts=class_conflicts, summary=summary, blockers=blockers,
                  duplicates=duplicates, orphan_labels=orphan_labels, patient_leaks=patient_leaks,
                  patient_check='CSV supplied' if patient_csv else 'Unavailable: filenames are not confirmed patient IDs',
                  limitations=['Exact byte and decoded pixel hashes only; near duplicates require human review.',
                               'Syntactically valid annotations still require semantic review.'],
                  class_counts=counts, class_count_scope='All successfully parsed nonduplicate rows, including EXIF-flagged images; invalid rows excluded',
                  raw_class_id_box_counts=dict(Counter(b[0] for r in rows for b in r['boxes'])))
    write_json(output/'audit.json', report)
    write_json(output/'manifest.json', rows)
    with (output/'class_counts.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(counts[0])); writer.writeheader(); writer.writerows(counts)
    rng = random.Random(42)
    visual = output/'visualizations'; visual.mkdir(parents=True, exist_ok=True)
    for split in summary:
        selected = [r for r in rows if r['split'] == split and 'size' in r]
        sample = rng.sample(selected, min(6, len(selected)))
        # Include one example of each class beyond the random sample.
        for cid in range(21):
            example = next((r for r in selected if any(b[0] == cid for b in r['boxes'])), None)
            if example and example not in sample: sample.append(example)
        for i, r in enumerate(sample):
            with Image.open(r['image']) as im:
                im = im.convert('RGB'); im.thumbnail((1000,1000))
                draw = ImageDraw.Draw(im); w,h = im.size
                for cid,x,y,bw,bh in r['boxes']:
                    color = ((cid*71+100)%256, (cid*113+80)%256, (cid*47+150)%256)
                    xy = [(x-bw/2)*w,(y-bh/2)*h,(x+bw/2)*w,(y+bh/2)*h]
                    draw.rectangle(xy, outline=color, width=3)
                    draw.text((max(0,xy[0]),max(0,xy[1])), f'{cid}: {names[cid]}', fill=color, stroke_width=1, stroke_fill='black')
                im.save(visual/f'{split}_{i:02d}.jpg')
    lines = ['# Dataset audit', '', 'TXT only; COCO/XML images were not merged.', '',
             'Class order: local classes.txt (21 entries); dataset README 20-class order is stale.',
             'If class_conflicts is nonempty, names in counts/visualizations use the first candidate only and are UNCONFIRMED.', '',
             '## Split counts', '', '```json', json.dumps(summary,indent=2), '```', '',
             '## Blocking findings', '', *(['- '+s for s in blockers] or ['None detected.']), '',
             f'Duplicate groups (byte/pixel reports overlap): {len(duplicates)}.',
             f"Exact decoded RGB groups: {sum(d['kind']=='pixel_sha256' for d in duplicates)}; cross-split: {sum(d['kind']=='pixel_sha256' and d['cross_split'] for d in duplicates)}.",
             'Pixel digest = SHA256(str(RGB.size).encode() + RGB.tobytes()), no EXIF transpose. Cross-split means more than one original split string in that group.',
             'annotation_conflict is the legacy field name for strict sorted parsed-box inequality; numeric jitter alone can trigger it. This is not an adjudicated conflict.',
             'Patient check: '+report['patient_check'], '',
             '## Proposed corrections', '',
             'Review conflicting annotations against source images; never choose a class by guessing.',
             'Resolve missing labels with the annotator; do not synthesize empty negatives.',
             'Group identical/near-identical images and confirmed patient IDs before resplitting; preserve a final test holdout.',
             'Write approved corrections only to a new research dataset; rerun audit before formal training.', '',
             'Details: audit.json, manifest.json, class_counts.csv, visualizations/.',
             'No semantic annotation correctness or patient independence is claimed.']
    (output/'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Audit complete. Blocking findings: {len(blockers)}. Reports saved under research.')
    return report

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=DATA_ROOT)
    p.add_argument('--output', type=Path, default=ROOT/'results'/'data_audit')
    p.add_argument('--patient-csv', type=Path, help='CSV columns: image_relative_path,patient_id (relative to TXT root)')
    a = p.parse_args(); audit(a.source, a.output, a.patient_csv)
