"""Reproducible conservative target-class subset; originals are never changed."""
import argparse
from collections import Counter, defaultdict
import csv
import itertools
import json
from pathlib import Path
import shutil
import numpy as np
from scipy.optimize import linear_sum_assignment
import yaml
from common import ROOT, digest, write_json
from audit_data import parse_label
from review_data import xyxy

def read_json(p):return json.loads(Path(p).read_text(encoding='utf-8'))

def table(path,rows):
    if not rows:return
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def agreement(a,b,size,tolerance=1.):
    if Counter(x[0] for x in a)!=Counter(x[0] for x in b):return False,[]
    pairs=[]
    for cid in sorted({x[0] for x in a}):
        aa=[xyxy(x,size) for x in a if x[0]==cid];bb=[xyxy(x,size) for x in b if x[0]==cid]
        cost=np.array([[max(abs(u-v) for u,v in zip(x[1:],y[1:])) for y in bb] for x in aa])
        # Minimize the number of edges outside tolerance before minimizing small numeric jitter.
        ii,jj=linear_sum_assignment((cost>tolerance)*1e9+np.minimum(cost,1e6))
        for i,j in zip(ii,jj):pairs.append(dict(original_id=cid,max_edge_delta_pixels=float(cost[i,j])))
    return all(p['max_edge_delta_pixels']<=tolerance for p in pairs),pairs

def clean(a):
    policy=read_json(a.policy);manifest=read_json(a.audit/'manifest.json');audit=read_json(a.audit/'audit.json')
    exact=read_json(a.review/'exact_groups.json');near=read_json(a.review/'near_suspects.json')
    visual=read_json(ROOT/'configs'/'clean_v1_visual_review.json')
    visual_by_id={r['group_id']:r for r in visual['decisions']}
    out=a.output.resolve();logs=a.logs.resolve()
    if ROOT not in out.parents or ROOT not in logs.parents:raise ValueError('Outputs must stay inside research')
    if out.exists() or logs.exists():raise FileExistsError('Output exists; choose fresh --output and --logs')
    selected=set(policy['selected_original_ids']);mapping={old:new for new,old in enumerate(policy['selected_original_ids'])}
    local_maps=[Path(p).read_text(encoding='utf-8-sig').splitlines() for p in audit['class_files']]
    names={old:local_maps[0][old] for old in selected}
    if any(any(m[old]!=names[old] for old in selected) for m in local_maps):raise ValueError('Selected class mapping conflict')
    coco_index=defaultdict(list);coco_sources=[]
    for p in sorted(Path(audit['source']).rglob('annotations/*.json')):
        data=read_json(p);cats={x['id']:x['name'] for x in data['categories']}
        if any(cats.get(old)!=names[old] for old in selected):raise ValueError('Selected COCO category differs from local mapping')
        anns=defaultdict(list)
        for ann in data['annotations']:anns[ann['image_id']].append(ann)
        source=dict(path=str(p),sha256=digest(p));coco_sources.append(source)
        for im in data['images']:
            coco_index[(p.parent.parent.name,im['file_name'])].append(dict(source=source,image_record=im,annotations=anns[im['id']],
                image=str(p.parent.parent/'images'/im['file_name']),declared_ids=set(cats)))
    by_rel={r['relative']:r for r in manifest};reasons=defaultdict(list);target={};corroboration={}
    for i,r in enumerate(manifest):
        rel=r['relative']
        if digest(r['image'])!=r['sha256'] or digest(r['label'])!=r['label_sha256']:raise ValueError('Source changed; rerun original audit')
        boxes,errors=parse_label(Path(r['label']).read_text(encoding='utf-8-sig'))
        if boxes!=r['boxes']:raise ValueError('Parser output changed since original audit')
        if r['errors'] or errors:reasons[rel].append('source_errors_or_EXIF_requires_review')
        if any(b[0] in policy['image_quarantine_if_present'] for b in boxes):reasons[rel].append('ambiguous_or_unselected_unclear_class_present')
        target[rel]=[b for b in boxes if b[0] in selected]
        if not target[rel]:reasons[rel].append('no_retained_target_boxes_absence_unconfirmed_not_negative')
        records=coco_index.get((r['split'],Path(r['image']).name),[])
        if len(records)!=1:reasons[rel].append('no_unique_same_split_same_name_COCO_record')
        else:
            c=records[0];im=c['image_record'];w,h=im['width'],im['height']
            sha=digest(c['image']);converted=[]
            if sha!=r['sha256'] or [w,h]!=r.get('size'):reasons[rel].append('COCO_image_bytes_or_dimensions_differ')
            if any(x['category_id'] not in c['declared_ids'] for x in c['annotations']):reasons[rel].append('COCO_undeclared_category_present')
            for ann in c['annotations']:
                if ann['category_id'] in selected:
                    x,y,bw,bh=ann['bbox'];converted.append([ann['category_id'],(x+bw/2)/w,(y+bh/2)/h,bw/w,bh/h])
            agrees,pairs=agreement(target[rel],converted,(w,h),policy['target_box_max_edge_tolerance_pixels'])
            if not agrees:reasons[rel].append('TXT_COCO_target_set_disagreement')
            corroboration[rel]=dict(coco_json=c['source'],image_id=im['id'],image_sha256=sha,annotation_ids=[x['id'] for x in c['annotations'] if x['category_id'] in selected],
                target_sets_agree=agrees,edge_checks=pairs)
        if (i+1)%500==0:print(f'Checked source evidence: {i+1}/{len(manifest)}',flush=True)
    near_logs=[]
    for pair in sorted(near,key=lambda p:(p['a_split']==p['b_split'],'test' not in (p['a_split'],p['b_split']),p['group_id'])):
        cross=pair['a_split']!=pair['b_split'];viewed=visual_by_id.get(pair['group_id'])
        if cross:
            for rel in (pair['a'],pair['b']):reasons[rel].append('unresolved_cross_split_near_risk:'+pair['group_id'])
        near_logs.append(dict(group_id=pair['group_id'],a=pair['a'],b=pair['b'],cross_split=cross,
            review_status='visually_likely_same_capture_labels_unadjudicated' if viewed else 'not_visually_adjudicated',
            observation=viewed['observation'] if viewed else 'Similarity is only a candidate signal; no duplicate identity decision.',
            decision='quarantine_both_pending_review' if cross else 'retain_if_other_checks_pass_same_split_pending_review',
            evidence=str(a.review/'near'/pair['group_id']/'evidence.json')))
    exact_logs=[]
    for group in exact:
        members=[by_rel[m['relative']] for m in group['members']];diffs=[]
        for x,y in itertools.combinations(members,2):
            agrees,pairs=agreement(target[x['relative']],target[y['relative']],x['size'],policy['target_box_max_edge_tolerance_pixels'])
            diffs.append(dict(a=x['relative'],b=y['relative'],target_sets_agree=agrees,edge_checks=pairs))
        consistent=all(d['target_sets_agree'] for d in diffs)
        group_blocked=not consistent or any(reasons[m['relative']] for m in members)
        keeper=None
        if not group_blocked:
            keeper=min(members,key=lambda m:({'test':0,'val':1,'train':2}[m['split']],m['relative']))['relative']
        for m in members:
            if m['relative']!=keeper:
                reasons[m['relative']].append('exact_group_target_conflict:'+group['group_id'] if not consistent else
                    ('exact_group_member_requires_review:'+group['group_id'] if group_blocked else 'exact_duplicate_nonrepresentative:'+group['group_id']))
        exact_logs.append(dict(group_id=group['group_id'],cross_split=group['cross_split'],retained_original=keeper,
            removed_from_training=[m['image'] for m in members if m['relative']!=keeper],
            retained_source_path=by_rel[keeper]['image'] if keeper else None,
            decision='retain_one_agreeing_target_set' if keeper else 'quarantine_whole_group',
            annotation_basis='All original target sets agree within 1px and each agrees with same-file COCO; retain original holdout priority.' if keeper else
                'No annotation adjudication guessed: target disagreement or existing source/near risk quarantines all members.',
            target_comparisons=diffs,member_reasons={m['relative']:reasons[m['relative']] for m in members},
            evidence=str(a.review/group['evidence'])))
    out.mkdir(parents=True);logs.mkdir(parents=True)
    for s in ('train','val','test'):
        (out/s/'images').mkdir(parents=True);(out/s/'labels').mkdir()
    records=[];isolated_boxes=[]
    for r in manifest:
        rel=r['relative'];excluded=bool(reasons[rel]);base=out/'quarantine' if excluded else out
        destination=base/rel;label=base/r['split']/'labels'/Path(r['image']).with_suffix('.txt').name
        destination.parent.mkdir(parents=True,exist_ok=True);label.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(r['image'],destination)
        if excluded:shutil.copyfile(r['label'],label)
        else:
            converted=[[mapping[b[0]],*b[1:]] for b in target[rel]]
            label.write_text(''.join(str(b[0])+' '+' '.join(format(v,'.12g') for v in b[1:])+'\n' for b in converted),encoding='utf-8')
        for b in r['boxes']:
            if excluded or b[0] not in selected:isolated_boxes.append(dict(relative=rel,original_class_id=b[0],box=b,
                reason='image_quarantine' if excluded else 'known_non_target_annotation_excluded'))
        records.append(dict(source_image=r['image'],source_label=r['label'],original_relative=rel,original_split=r['split'],
            image_sha256=r['sha256'],source_label_sha256=r['label_sha256'],source_pixel_sha256=r.get('pixel_sha256'),
            destination=str(destination),destination_label=str(label),destination_label_sha256=digest(label),
            status='quarantined' if excluded else 'retained',reasons=reasons[rel],
            original_boxes=r['boxes'],retained_original_boxes=[] if excluded else target[rel],corroboration=corroboration.get(rel)))
    class_rows=[]
    for old,name in enumerate(local_maps[0]):
        class_rows.append(dict(original_id=old,original_name=name,new_id=mapping.get(old),
            new_name=name if old in selected else None,
            decision='retain_target' if old in selected else ('known_out_of_scope_annotation_only' if old in policy['known_out_of_scope_ids'] else 'quarantine_entire_image_if_present'),
            basis='Stable ID/name in all local class files, original TXT YAML and all COCO categories; every retained image also has matching COCO target boxes.' if old in selected else 'Not selected for v1; no 19/20 exchange or inferred medical mapping.'))
    write_json(out/'class_mapping.json',class_rows);table(logs/'class_mapping.csv',class_rows)
    write_json(logs/'clean_manifest.json',records);write_json(logs/'isolated_annotations.json',isolated_boxes)
    write_json(logs/'exact_group_decisions.json',exact_logs);write_json(logs/'near_pair_decisions.json',near_logs)
    table(logs/'exact_79_decisions.csv',[dict(group_id=g['group_id'],decision=g['decision'],retained_path=g['retained_source_path'] or '',
        removed_paths=json.dumps(g['removed_from_training'],ensure_ascii=False),annotation_basis=g['annotation_basis']) for g in exact_logs if g['cross_split']])
    table(logs/'near_pair_decisions.csv',near_logs)
    table(logs/'quarantine.csv',[dict(original_path=r['source_image'],original_split=r['original_split'],quarantine_path=r['destination'],reasons=';'.join(r['reasons'])) for r in records if r['status']=='quarantined'])
    config_path=out/'data.yaml'
    config_path.write_text(yaml.safe_dump(dict(path=out.as_posix(),train='train/images',val='val/images',test='test/images',nc=len(mapping),
        names={new:names[old] for old,new in mapping.items()}),sort_keys=False,allow_unicode=True),encoding='utf-8')
    sources={str(p.resolve()):digest(p) for p in [a.policy,a.audit/'audit.json',a.audit/'manifest.json',a.review/'exact_groups.json',a.review/'near_suspects.json',ROOT/'configs'/'clean_v1_visual_review.json']}
    write_json(logs/'build.json',dict(policy=policy,input_hashes=sources,coco_sources=coco_sources,script_sha256=digest(__file__),
        dataset=str(out),config=str(config_path),manifest_sha256=digest(logs/'clean_manifest.json'),original_to_new=mapping,
        original_names=names,split_counts=dict(Counter(r['original_split'] for r in records if r['status']=='retained')),
        quarantined=sum(r['status']=='quarantined' for r in records),negative_images=0))
    (logs/'clean_dataset_snapshot.py').write_text(Path(__file__).read_text(encoding='utf-8'),encoding='utf-8')
    shutil.copyfile(a.policy,logs/'policy.json');shutil.copyfile(ROOT/'configs'/'clean_v1_visual_review.json',logs/'visual_review.json')
    print('Clean copy and quarantine created. Run audit_clean.py before training.',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit',type=Path,default=ROOT/'results'/'data_audit')
    p.add_argument('--review',type=Path,default=ROOT/'results'/'data_review')
    p.add_argument('--policy',type=Path,default=ROOT/'configs'/'clean_v1_policy.json')
    p.add_argument('--output',type=Path,default=ROOT/'datasets'/'clean_v1')
    p.add_argument('--logs',type=Path,default=ROOT/'results'/'clean_v1')
    clean(p.parse_args())
