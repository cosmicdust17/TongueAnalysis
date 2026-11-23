"""Independently re-audit the physical cleaned copy before enabling its config."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from PIL import Image
import hashlib
import yaml
from audit_data import IMAGE_EXTS, parse_label
from clean_dataset import read_json, table
from common import ROOT, digest, write_json

def audit_clean(a):
    data=a.data.resolve();logs=a.logs.resolve();config_path=data/'data.yaml'
    config=yaml.safe_load(config_path.read_text(encoding='utf-8'));nc=config['nc']
    manifest=read_json(logs/'clean_manifest.json');build=read_json(logs/'build.json')
    if digest(logs/'clean_manifest.json')!=build['manifest_sha256']:raise ValueError('Build manifest changed')
    expected={str(Path(r['destination']).resolve()):r for r in manifest if r['status']=='retained'}
    blockers=[];actual=[];counts=[];byte_groups=defaultdict(list);pixel_groups=defaultdict(list)
    for s in ('train','val','test'):
        image_root=data/s/'images';label_root=data/s/'labels'
        images=sorted(p for p in image_root.rglob('*') if p.suffix.lower() in IMAGE_EXTS)
        expected_labels=set()
        for i,p in enumerate(images):
            label=label_root/p.relative_to(image_root).with_suffix('.txt');expected_labels.add(label)
            errors=[];source=expected.get(str(p.resolve()))
            if source is None:errors.append('Unexpected image not present in clean manifest')
            sha=digest(p)
            if source and sha!=source['image_sha256']:errors.append('Copied image hash mismatch')
            try:
                with Image.open(p) as im:
                    im.load();rgb=im.convert('RGB');size=rgb.size
                    pixels=hashlib.sha256(str(size).encode()+rgb.tobytes()).hexdigest()
                    if im.getexif().get(274,1)!=1:errors.append('Unresolved EXIF orientation')
                byte_groups[sha].append(str(p));pixel_groups[pixels].append(str(p))
            except Exception as e:errors.append('Decode failed: '+str(e))
            boxes=[]
            if not label.is_file():errors.append('Missing label; not a negative sample')
            else:
                boxes,parse_errors=parse_label(label.read_text(encoding='utf-8-sig'),nc)
                errors.extend(parse_errors)
                if not boxes:errors.append('Empty target label; no negative confirmation')
                if source and digest(label)!=source['destination_label_sha256']:errors.append('Converted label hash mismatch')
                if source:
                    wanted=[[build['original_to_new'][str(b[0])],*b[1:]] for b in source['retained_original_boxes']]
                    if len(boxes)!=len(wanted) or any(x[0]!=y[0] or max(abs(u-v) for u,v in zip(x[1:],y[1:]))>1e-10 for x,y in zip(boxes,wanted)):
                        errors.append('Converted boxes differ from original-to-new mapping')
            row=dict(split=s,image=str(p),label=str(label),sha256=sha,boxes=boxes,errors=errors)
            actual.append(row)
            if errors:blockers.append(dict(image=str(p),errors=errors))
            if (i+1)%500==0:print(f'Re-audited {s}: {i+1}/{len(images)}',flush=True)
        orphan=[str(p) for p in label_root.rglob('*.txt') if p not in expected_labels]
        if orphan:blockers.append(dict(orphan_labels=orphan))
        subset=[r for r in actual if r['split']==s]
        for cid,name in config['names'].items():
            counts.append(dict(split=s,new_id=cid,original_id=next(int(k) for k,v in build['original_to_new'].items() if v==cid),name=name,
                images=sum(any(b[0]==cid for b in r['boxes']) for r in subset),boxes=sum(b[0]==cid for r in subset for b in r['boxes'])))
    observed={str(Path(r['image']).resolve()) for r in actual}
    if observed!=set(expected):blockers.append(dict(missing_or_extra_images=sorted(observed.symmetric_difference(expected))))
    duplicates=[dict(kind=k,images=v) for k,g in [('file_sha256',byte_groups),('pixel_sha256',pixel_groups)] for v in g.values() if len(v)>1]
    if duplicates:blockers.append(dict(exact_duplicate_groups=len(duplicates)))
    for c in counts:
        if c['images']==0:blockers.append(dict(class_absent=c))
    # Quarantine is a physical copy, not deletion or conversion into negative samples.
    quarantine_errors=[]
    for r in manifest:
        if r['status']=='quarantined' and (not Path(r['destination']).is_file() or not Path(r['destination_label']).is_file() or
            digest(r['destination'])!=r['image_sha256'] or digest(r['destination_label'])!=r['source_label_sha256']):
            quarantine_errors.append(r['original_relative'])
    if quarantine_errors:blockers.append(dict(quarantine_copy_errors=quarantine_errors))
    by_rel={r['original_relative']:r for r in manifest};near=read_json(logs/'near_pair_decisions.json');remaining=[]
    for p in near:
        q=dict(p,a_clean_status=by_rel[p['a']]['status'],b_clean_status=by_rel[p['b']]['status'])
        q['both_in_clean']=q['a_clean_status']==q['b_clean_status']=='retained'
        remaining.append(q)
    live_cross=[p for p in remaining if p['cross_split'] and p['both_in_clean']]
    if live_cross:blockers.append(dict(unresolved_active_cross_split_near_pairs=len(live_cross)))
    mapping_evidence={}
    source_audit=read_json(ROOT/'results'/'data_audit'/'audit.json')
    for file in source_audit['class_files']:
        mapping_evidence[file]=dict(sha256=digest(file),names=Path(file).read_text(encoding='utf-8-sig').splitlines())
    txt_yaml=Path(source_audit['txt_root'])/'shezhenv3-txt.yaml';old_yaml=yaml.safe_load(txt_yaml.read_text(encoding='utf-8-sig'))
    for old,new in build['original_to_new'].items():
        if old_yaml['names'].get(int(old))!=config['names'][new]:blockers.append(dict(original_yaml_mapping_disagrees=old))
    write_json(logs/'mapping_sources.json',dict(class_files=mapping_evidence,original_txt_yaml=str(txt_yaml),original_txt_yaml_sha256=digest(txt_yaml),
        original_txt_yaml_names=old_yaml['names'],coco_sources=build['coco_sources'],note='19/20 excluded; inconsistent names not resolved by this subset'))
    table(logs/'class_counts.csv',counts);write_json(logs/'reaudit_manifest.json',actual)
    write_json(logs/'remaining_near_review.json',remaining)
    summary=dict(split_images=dict(Counter(r['split'] for r in actual)),total_images=len(actual),negative_images=0,
        quarantined_images=sum(r['status']=='quarantined' for r in manifest),class_counts=counts,
        missing_labels=sum(not Path(r['label']).is_file() for r in actual),empty_labels=sum(not r['boxes'] for r in actual),
        images_with_errors=sum(bool(r['errors']) for r in actual),exact_duplicates=duplicates,cross_split_exact_duplicates=0 if not duplicates else 'see details',
        source_near_candidates=len(near),source_cross_split_near_candidates=sum(p['cross_split'] for p in near),
        visually_reviewed_near_pairs=sum(p['review_status'].startswith('visually') for p in near),
        active_unresolved_cross_split_near_pairs=len(live_cross),active_same_split_near_pairs=sum(not p['cross_split'] and p['both_in_clean'] for p in remaining),
        patient_independence='unknown; no confirmed patient IDs',blockers=blockers,formal_allowed=not blockers,
        limitation='Conservative source-label subset, not clinical ground-truth adjudication; near detector is not exhaustive')
    write_json(logs/'reaudit.json',summary)
    provenance=dict(config_sha256=digest(config_path),nc=nc,names=config['names'],smoke=False,formal_allowed=not blockers,
        dataset_version='tongue-clean-v1',original_to_new=build['original_to_new'],original_names=build['original_names'],
        audit=str(logs/'reaudit.json'),audit_sha256=digest(logs/'reaudit.json'),clean_manifest=str(logs/'clean_manifest.json'),
        clean_manifest_sha256=digest(logs/'clean_manifest.json'),seed=42,source_blockers='Isolated in quarantine; see clean logs')
    write_json(config_path.with_suffix('.provenance.json'),provenance)
    lines=['# Clean v1 re-audit','', '```json',json.dumps({k:v for k,v in summary.items() if k!='class_counts'},indent=2),'```','',
        '| Split | New ID | Original ID | Name | Images | Boxes |','|---|---|---|---|---|---|']
    lines += [f"| {c['split']} | {c['new_id']} | {c['original_id']} | {c['name']} | {c['images']} | {c['boxes']} |" for c in counts]
    lines += ['', 'Retained images preserve original splits. Exact groups with incompatible target sets are fully quarantined; agreeing sets retain at most one original holdout representative.',
        'Cross-split near candidates are quarantined as unresolved risk, never declared duplicate from score; same-split candidates remain explicitly pending.',
        'No unconfirmed empty target image is used as a negative. Quarantine originals retain all source labels.',
        'Source/target mapping is supported by stable metadata plus per-image TXT/COCO target agreement, not clinical validation.',
        'Patient IDs unknown; unrecognized near duplicates or incomplete source annotations can remain.',
        'Training has not been started. Commands and interpretation are in README.md.']
    (logs/'reaudit.md').write_text('\n'.join(lines),encoding='utf-8')
    (logs/'audit_clean_snapshot.py').write_text(Path(__file__).read_text(encoding='utf-8'),encoding='utf-8')
    print(f'Re-audit completed. Images: {len(actual)}. Blocking findings: {len(blockers)}. Training not started.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,default=ROOT/'datasets'/'clean_v1')
    p.add_argument('--logs',type=Path,default=ROOT/'results'/'clean_v1')
    audit_clean(p.parse_args())
