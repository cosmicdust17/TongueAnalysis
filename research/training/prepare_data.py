"""Create a research-only copy and 21-class YOLO configuration from an audit."""
import argparse
import json
from pathlib import Path
import random
import shutil
from common import ROOT, classes, digest, write_json

def prepare(a):
    import yaml
    audit_dir = a.audit.resolve()
    report = json.loads((audit_dir/'audit.json').read_text(encoding='utf-8'))
    rows = json.loads((audit_dir/'manifest.json').read_text(encoding='utf-8'))
    class_file = a.classes or Path(report['class_files'][0])
    if class_file.resolve() not in {Path(p).resolve() for p in report['class_files']}:
        raise ValueError('Class file must be one of the audited local mappings')
    names = classes(class_file)
    if report['class_conflicts'] and not (a.smoke and a.classes):
        raise ValueError('Class mapping conflict; explicit --classes required for smoke only')
    if report['blockers'] and not a.smoke:
        raise ValueError('Audit blocked formal training. Review report.md and re-audit approved corrections.')
    excluded = {r for d in report['duplicates'] for r in d['images']}
    excluded.update(r for d in report['patient_leaks'] for r in d['images'])
    selected = []
    rng = random.Random(42)
    for split in ('train','val','test'):
        if a.smoke and split == 'test': continue
        # The split-local maps disagree at these IDs; do not use ambiguous labels in smoke validation.
        ambiguous_ids = {i for p in report['class_files'] for i,n in enumerate(classes(p)) if n != names[i]}
        pool = [r for r in rows if r['split'] == split and not r['errors'] and
                (not a.smoke or (r['relative'] not in excluded and
                  not any(b[0] in ambiguous_ids for b in r['boxes'])))]
        rng.shuffle(pool)
        selected.extend(pool[:32 if split == 'train' else 16] if a.smoke else pool)
    if not all(any(r['split']==s for r in selected) for s in ('train','val')):
        raise ValueError('Not enough clean samples for train and validation')
    target = (ROOT/'datasets'/('smoke' if a.smoke else 'formal')).resolve()
    if target.exists(): raise FileExistsError('Prepared dataset already exists; use a fresh research workspace')
    config_path = ROOT/'configs'/('tongue21-smoke.yaml' if a.smoke else 'tongue21.yaml')
    if config_path.exists(): raise FileExistsError('Configuration already exists; archive it before preparing again')
    for r in selected:
        if digest(r['image']) != r['sha256'] or digest(r['label']) != r['label_sha256']:
            raise ValueError('Source changed since audit; rerun the audit')
    for r in selected:
        rel = Path(r['relative'])
        image = target/rel
        label = target/r['split']/'labels'/rel.relative_to(Path(r['split'])/'images').with_suffix('.txt')
        image.parent.mkdir(parents=True, exist_ok=True); label.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(r['image'], image); shutil.copyfile(r['label'], label)
    config = dict(path=target.as_posix(), train='train/images', val='val/images', nc=21,
                  names=dict(enumerate(names)))
    if not a.smoke: config['test'] = 'test/images'
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding='utf-8')
    write_json(config_path.with_suffix('.provenance.json'), dict(config_sha256=digest(config_path),
               audit_sha256=digest(audit_dir/'audit.json'), manifest_sha256=digest(audit_dir/'manifest.json'),
               class_files=report['class_files'], selected_class_file=str(class_file), names=names, seed=42,
               excluded_ambiguous_class_ids=sorted(ambiguous_ids),
               smoke=a.smoke, formal_allowed=not report['blockers'] and not a.smoke,
               source_blockers=report['blockers'], excluded_duplicate_images=len(excluded),
               selected=[r['relative'] for r in selected]))
    write_json(target/'class_mapping.json', dict(enumerate(names)))
    write_json(target/'source_manifest.json', selected)
    print(f'Prepared {len(selected)} research copies. Mode: '+('smoke only' if a.smoke else 'formal'))

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit', type=Path, default=ROOT/'results'/'data_audit')
    p.add_argument('--smoke', action='store_true', help='Clean train/val subset only; exclude duplicates; never use test')
    p.add_argument('--classes', type=Path, help='Explicitly confirmed local classes.txt for smoke only when maps conflict')
    prepare(p.parse_args())
