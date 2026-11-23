"""Read-only evidence review of exact duplicates, near candidates and format mappings."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.fft import dctn
from scipy.optimize import linear_sum_assignment
from audit_data import IMAGE_EXTS, parse_label
from common import ROOT, digest, write_json

def rgb(path):
    with Image.open(path) as im:
        return im.convert('RGB')  # Match audit: raw decoded orientation, no EXIF transpose.

def xyxy(box, size):
    c,x,y,w,h = box; iw,ih = size
    return [c,(x-w/2)*iw,(y-h/2)*ih,(x+w/2)*iw,(y+h/2)*ih]

def iou(a,b):
    inter=max(0,min(a[3],b[3])-max(a[1],b[1]))*max(0,min(a[4],b[4])-max(a[2],b[2]))
    area=lambda r:max(0,r[3]-r[1])*max(0,r[4]-r[2])
    return inter/max(1e-12,area(a)+area(b)-inter)

def compare(a,b,size):
    aa=[xyxy(x,size) for x in a]; bb=[xyxy(x,size) for x in b]
    exact_a=Counter(tuple(x) for x in a); exact_b=Counter(tuple(x) for x in b)
    matches=[]; used_a=set(); used_b=set()
    if aa and bb:
        # Match geometry first; do not hide same-box class changes by forcing class agreement.
        cost=np.array([[1-iou(x,y)+(0 if x[0]==y[0] else 1e-6) for y in bb] for x in aa])
        ia,ib=linear_sum_assignment(cost)
        for j,k in zip(ia,ib):
            x,y=aa[j],bb[k]; overlap=iou(x,y); delta=max(abs(u-v) for u,v in zip(x[1:],y[1:]))
            if overlap < .5 and delta > 2: continue
            used_a.add(int(j)); used_b.add(int(k))
            kind='class_id_difference' if x[0]!=y[0] else ('within_1px' if delta<=1 else 'geometry_difference')
            matches.append(dict(a_index=int(j),b_index=int(k),a=a[j],b=b[k],iou=overlap,max_edge_delta_pixels=delta,kind=kind))
    missing_a=[dict(index=j,box=x) for j,x in enumerate(a) if j not in used_a]
    missing_b=[dict(index=j,box=x) for j,x in enumerate(b) if j not in used_b]
    kinds=sorted({x['kind'] for x in matches if x['kind']!='within_1px'})
    if missing_a or missing_b: kinds.append('unmatched_instances')
    classification='exact_annotations' if exact_a==exact_b else ('numeric_difference_within_1px' if not kinds else '+'.join(kinds))
    return dict(classification=classification,exact_equal=exact_a==exact_b,
                only_a=[list(x) for x in (exact_a-exact_b).elements()],
                only_b=[list(x) for x in (exact_b-exact_a).elements()],
                matched=matches,unmatched_a=missing_a,unmatched_b=missing_b)

def board(items, output, boxes=False):
    # Resized previews; original paths and hashes remain in JSON/Markdown.
    cell_w,cell_h=640,570; columns=min(3,len(items))
    canvas=Image.new('RGB',(columns*cell_w,math.ceil(len(items)/columns)*cell_h),'white')
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',15)
    for idx,item in enumerate(items):
        im=rgb(item['image']); ow,oh=im.size; im.thumbnail((620,480))
        if boxes:
            draw=ImageDraw.Draw(im)
            for n,b in enumerate(item.get('boxes',[])):
                c,x1,y1,x2,y2=xyxy(b,(ow,oh)); sx=im.width/ow; sy=im.height/oh
                color=((int(c)*71+80)%220,(int(c)*113+40)%220,(int(c)*47+100)%220)
                draw.rectangle((x1*sx,y1*sy,x2*sx,y2*sy),outline=color,width=3)
                draw.text((max(0,x1*sx),max(0,y1*sy)),f'#{n} ID {c}',font=font,fill='white',stroke_width=2,stroke_fill='black')
        x=(idx%columns)*cell_w;y=(idx//columns)*cell_h
        canvas.paste(im,(x+10,y+75));draw=ImageDraw.Draw(canvas)
        title=item.get('title',item.get('relative',Path(item['image']).name)).replace('\\','/')
        draw.text((x+10,y+8),title[:78],font=font,fill='black')
        draw.text((x+10,y+30),f"Raw {ow}x{oh}; boxes={len(item.get('boxes',[]))}",font=font,fill='black')
    output.parent.mkdir(parents=True,exist_ok=True);canvas.save(output)

def write_csv(path, rows):
    if not rows:return
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def exact_review(manifest,out):
    grouped=defaultdict(list)
    for r in manifest:
        if r.get('pixel_sha256'):grouped[r['pixel_sha256']].append(r)
    groups=[];flat=[]
    for hash_value,rows in sorted(grouped.items()):
        if len(rows)<2:continue
        gid=f'exact_{len(groups)+1:03d}';members=[];base=rgb(rows[0]['image'])
        for r in rows:
            sha=digest(r['image'])
            if sha!=r['sha256'] or digest(r['label'])!=r['label_sha256']:
                raise ValueError('Source changed since audit; rerun audit before review')
            im=rgb(r['image']); equal=im.size==base.size and im.tobytes()==base.tobytes()
            if not equal:raise ValueError('Stored pixel hash group failed direct pixel comparison')
            boxes,errors=parse_label(Path(r['label']).read_text(encoding='utf-8-sig'))
            member=dict(image=r['image'],relative=r['relative'],split=r['split'],sha256=sha,
                        pixel_sha256=hash_value,pixels_equal_to_first=equal,label=r['label'],
                        label_sha256=r['label_sha256'],boxes=boxes,label_errors=errors,
                        raw_label=Path(r['label']).read_text(encoding='utf-8-sig'))
            members.append(member)
            flat.append(dict(group_id=gid,cross_split=len({x['split'] for x in rows})>1,
                image=r['image'],original_split=r['split'],sha256=sha,pixel_sha256=hash_value,
                pixels_equal_to_first=equal,parsed_boxes=json.dumps(boxes)))
        diffs=[dict(a=members[j]['relative'],b=members[k]['relative'],
                    **compare(members[j]['boxes'],members[k]['boxes'],base.size)) for j,k in itertools.combinations(range(len(members)),2)]
        group=dict(group_id=gid,cross_split=len({r['split'] for r in rows})>1,
                   file_bytes_all_identical=len({r['sha256'] for r in rows})==1,
                   pixels_all_identical=True,members=members,pairwise_annotation_differences=diffs,
                   review_status='pending',approved_action='',reviewer='',rationale='')
        folder=out/'groups'/gid;folder.mkdir(parents=True,exist_ok=True)
        write_json(folder/'evidence.json',group)
        board(rows,folder/'originals.jpg');board(rows,folder/'annotations.jpg',True)
        group['evidence']=f'groups/{gid}/evidence.json';group['originals']=f'groups/{gid}/originals.jpg';group['annotations']=f'groups/{gid}/annotations.jpg'
        groups.append(group)
    write_json(out/'exact_groups.json',groups)
    write_csv(out/'exact_members.csv',flat)
    cross=[g for g in groups if g['cross_split']]
    write_json(out/'cross_split_79.json',cross)
    lines=['# Cross-split exact pixel groups','',
        'Grouped by SHA256(str(RGB.size).encode() + RGB.tobytes()), without EXIF transpose.',
        'Every member was rehashed and directly compared byte-for-byte in decoded RGB; different split strings define cross-split.',
        'Strict annotation inequality is not proof of a substantive labeling conflict. 1px tolerance is a review heuristic, not approval.', '']
    for g in cross:
        lines += [f"## {g['group_id']}",'',f"[Originals]({g['originals']}) | [Boxes]({g['annotations']}) | [Full differences]({g['evidence']})",'',
                  '| Original split | Image path | File SHA-256 | Pixels identical |','|---|---|---|---|']
        for m in g['members']:lines.append(f"| {m['split']} | {m['image']} | {m['sha256']} | true |")
        for d in g['pairwise_annotation_differences']:
            lines += ['',f"{d['a']} vs {d['b']}: **{d['classification']}**",'',
                      'Only A (class_id, xc, yc, w, h): `'+json.dumps(d['only_a'])+'`',
                      'Only B (class_id, xc, yc, w, h): `'+json.dumps(d['only_b'])+'`']
    (out/'cross_split_79.md').write_text('\n'.join(lines),encoding='utf-8')
    print(f'Exact review complete: {len(groups)} groups; {len(cross)} cross-split',flush=True)
    return groups

def near_review(rows,out):
    cache=out/'near_features.json'
    if cache.exists():features=json.loads(cache.read_text(encoding='utf-8'))
    else:
        features=[]
        for i,r in enumerate(rows):
            if digest(r['image'])!=r['sha256']:raise ValueError('Image changed since audit')
            im=rgb(r['image']);small=np.asarray(im.convert('L').resize((32,32)),dtype=float)
            coeff=dctn(small,type=2,norm='ortho')[:8,:8].flatten();threshold=np.median(coeff[1:])
            bits=coeff>threshold;bits[0]=False
            h=sum(int(v)<<j for j,v in enumerate(bits))
            features.append(dict(relative=r['relative'],sha256=r['sha256'],phash=h,aspect=im.width/im.height))
            if (i+1)%500==0:print(f'Near-duplicate features: {i+1}/{len(rows)}',flush=True)
        write_json(cache,features)
    if [(f['relative'],f['sha256']) for f in features] != [(r['relative'],r['sha256']) for r in rows]:
        raise ValueError('Feature cache does not match audited manifest')
    candidates=[];suspects=[]
    for i,f in enumerate(features):
        for j in range(i+1,len(features)):
            g=features[j]
            if rows[i].get('pixel_sha256')==rows[j].get('pixel_sha256'):continue
            distance=(f['phash']^g['phash']).bit_count()
            if distance>6 or abs(f['aspect']/g['aspect']-1)>.03:continue
            a=np.asarray(rgb(rows[i]['image']).resize((128,128)),dtype=float)
            b=np.asarray(rgb(rows[j]['image']).resize((128,128)),dtype=float)
            mae=float(np.abs(a-b).mean());av=a.mean(axis=2).flatten();bv=b.mean(axis=2).flatten()
            corr=float(np.corrcoef(av,bv)[0,1]) if av.std()>0 and bv.std()>0 else 0.
            suspect=mae<=12 and corr>=.98
            record=dict(a=rows[i]['relative'],b=rows[j]['relative'],a_image=rows[i]['image'],b_image=rows[j]['image'],
                a_boxes=rows[i]['boxes'],b_boxes=rows[j]['boxes'],a_label=rows[i]['label'],b_label=rows[j]['label'],
                a_split=rows[i]['split'],b_split=rows[j]['split'],a_sha256=f['sha256'],b_sha256=g['sha256'],
                phash_hamming=distance,resized_rgb_mae=mae,gray_correlation=corr,
                decoded_pixels_identical=False,suspected_near_duplicate=suspect,
                annotation_difference_at_128px=compare(rows[i]['boxes'],rows[j]['boxes'],(128,128)),
                review_status='pending',approved_action='',reviewer='',rationale='')
            if suspect:
                nid=f'near_{len(suspects)+1:04d}';record['group_id']=nid
                board([rows[i],rows[j]],out/'near'/nid/'originals.jpg')
                board([rows[i],rows[j]],out/'near'/nid/'annotations.jpg',True)
                record['originals']=f'near/{nid}/originals.jpg';record['annotations']=f'near/{nid}/annotations.jpg'
                write_json(out/'near'/nid/'evidence.json',record);suspects.append(record)
            candidates.append(record)
    write_json(out/'near_candidates.json',candidates);write_json(out/'near_suspects.json',suspects)
    lines=['# Suspected near duplicate pairs','',
        'Candidates only; no automatic merging or deletion. Scores use resized previews, not original-pixel identity.','',
        '| Pair | Image A (original split/path) | Image B | pHash distance | RGB MAE | Correlation | Comparison |',
        '|---|---|---|---|---|---|---|']
    for s in suspects:
        lines.append(f"| {s['group_id']} | {s['a']} | {s['b']} | {s['phash_hamming']} | {s['resized_rgb_mae']:.3f} | {s['gray_correlation']:.5f} | [Originals]({s['originals']}) / [Boxes]({s['annotations']}) / [Evidence](near/{s['group_id']}/evidence.json) |")
    (out/'near_review.md').write_text('\n'.join(lines),encoding='utf-8')
    print(f'Near review complete: {len(candidates)} candidates; {len(suspects)} suspects (not confirmed)',flush=True)
    return suspects

def format_review(rows,source,out):
    coco_docs=[];coco_hash=defaultdict(list);xml_hash=defaultdict(list);coco_counts={};xml_counts=defaultdict(Counter)
    for p in sorted(source.rglob('annotations/*.json')):
        d=json.loads(p.read_text(encoding='utf-8'));split=p.parent.parent.name
        categories={x['id']:x['name'] for x in d['categories']};by_id=defaultdict(list)
        for ann in d['annotations']:by_id[ann['image_id']].append(ann)
        coco_counts[split]=dict(counts=dict(Counter(x['category_id'] for x in d['annotations'])),categories=categories,
            undeclared_ids=sorted({x['category_id'] for x in d['annotations']}-set(categories)),json=str(p),sha256=digest(p))
        for im in d['images']:
            image=p.parent.parent/'images'/im['file_name']
            item=dict(image=str(image),split=split,json=str(p),image_record=im,annotations=by_id[im['id']],categories=categories)
            coco_hash[digest(image)].append(item)
        coco_docs.append((p,d))
        print(f'Indexed COCO image hashes: {split}',flush=True)
    sibling_indices={};image_digests={};xml_binding_issues=[]
    for xml_index,p in enumerate(source.rglob('*.xml'),1):
        tree=ET.parse(p).getroot();filename=tree.findtext('filename');im=p.parent/filename
        objects=[]
        for obj in tree.findall('object'):
            name=obj.findtext('name');xml_counts[p.parent.name][name]+=1
            bb=obj.find('bndbox');objects.append(dict(name=name,xyxy=[float(bb.findtext(k)) for k in ('xmin','ymin','xmax','ymax')]))
        if p.parent not in sibling_indices:
            idx=defaultdict(list)
            for q in p.parent.iterdir():
                if q.suffix.lower() in IMAGE_EXTS:idx[q.stem].append(q)
            sibling_indices[p.parent]=idx
        siblings=sibling_indices[p.parent].get(p.stem,[])
        header_agrees=Path(filename).stem==p.stem
        if not header_agrees:xml_binding_issues.append(dict(xml=str(p),declared_filename=filename,sibling_images=[str(q) for q in siblings]))
        bindings=[(q,'sibling_stem_candidate') for q in siblings]
        if im.exists() and im not in siblings:bindings.append((im,'declared_filename_candidate'))
        for candidate,binding in bindings:
            if candidate not in image_digests:image_digests[candidate]=digest(candidate)
            xml_hash[image_digests[candidate]].append(dict(xml=str(p),image=str(candidate),objects=objects,sha256=digest(p),
                declared_filename=filename,filename_matches_xml_stem=header_agrees,binding=binding,
                declared_size=[int(tree.findtext('size/width')),int(tree.findtext('size/height'))]))
        if xml_index%1000==0:print(f'Indexed XML image hashes: {xml_index}',flush=True)
    selected=[]
    for split in ('train','val','test'):
        for cid in (18,19,20):
            selected.extend([r for r in rows if r['split']==split and any(b[0]==cid for b in r['boxes'])][:2])
    # Include COCO 20 and undeclared 21 even when their TXT IDs differ.
    txt_hash=defaultdict(list)
    for r in rows:txt_hash[r['sha256']].append(r)
    for h,items in coco_hash.items():
        if any(any(a['category_id'] in (20,21) for a in it['annotations']) for it in items):
            for r in txt_hash.get(h,[])[:1]:
                if r not in selected and sum(any(b[0] in (18,19,20) for b in x['boxes']) for x in selected)<30:selected.append(r)
    evidence=[]
    for n,r in enumerate(selected,1):
        h=r['sha256'];folder=out/'mapping'/f'sample_{n:02d}';items=[dict(r,title='TXT '+r['relative'])];matches=[]
        for c in coco_hash.get(h,[]):
            size=(c['image_record']['width'],c['image_record']['height']);boxes=[]
            for ann in c['annotations']:
                x,y,w,hh=ann['bbox'];boxes.append([ann['category_id'],(x+w/2)/size[0],(y+hh/2)/size[1],w/size[0],hh/size[1]])
            same_pixels=rgb(r['image']).tobytes()==rgb(c['image']).tobytes() and rgb(r['image']).size==size
            diff=compare(r['boxes'],boxes,size)
            matches.append(dict(format='COCO',source=c,image_sha256=h,pixels_identical=same_pixels,boxes=boxes,comparison=diff))
            items.append(dict(image=c['image'],boxes=boxes,title='COCO '+c['split']+'/'+Path(c['image']).name))
        for x in xml_hash.get(h,[]):
            size=r['size'];boxes=[]
            for obj in x['objects']:
                if not obj['name'].isdigit():continue
                x1,y1,x2,y2=obj['xyxy'];boxes.append([int(obj['name']),(x1+x2)/2/size[0],(y1+y2)/2/size[1],(x2-x1)/size[0],(y2-y1)/size[1]])
            matches.append(dict(format='XML',source=x,image_sha256=h,pixels_identical=rgb(r['image']).tobytes()==rgb(x['image']).tobytes(),
                boxes=boxes,comparison=compare(r['boxes'],boxes,size),coordinate_note='Raw VOC values; no +1 or -1 assumed; allow <=1px rounding for review'))
            items.append(dict(image=x['image'],boxes=boxes,title='XML '+Path(x['xml']).name+' '+x['binding']))
        record=dict(sample_id=f'sample_{n:02d}',txt=r,matches=matches,
                    note='Same image established by SHA-256 and RGB comparison; geometry matched without assuming category order. Numeric XML names do not independently prove medical meanings.')
        folder.mkdir(parents=True,exist_ok=True);write_json(folder/'evidence.json',record)
        board(items,folder/'originals.jpg');board(items,folder/'annotations.jpg',True);evidence.append(record)
    write_json(out/'mapping_evidence.json',dict(coco=coco_counts,xml_name_counts={s:dict(v) for s,v in xml_counts.items()},
        xml_filename_mismatch_count=len(xml_binding_issues),xml_binding_issues=xml_binding_issues,samples=evidence))
    mapping_rows=[]
    for e in evidence:
        for match in e['matches']:
            for pair in match['comparison']['matched']:
                if pair['a'][0] not in (18,19,20) and pair['b'][0] not in (18,19,20,21):continue
                source_entry=match['source'];cat=pair['b'][0]
                mapping_rows.append(dict(sample=e['sample_id'],txt_image=e['txt']['image'],txt_split=e['txt']['split'],
                    image_sha256=e['txt']['sha256'],txt_id=pair['a'][0],format=match['format'],other_id=cat,
                    declared_name=source_entry['categories'].get(cat,'UNDECLARED') if match['format']=='COCO' else 'NUMERIC_NAME_ONLY',
                    annotation_path=source_entry.get('json',source_entry.get('xml')),binding=source_entry.get('binding','COCO image_id foreign key'),
                    iou=pair['iou'],max_edge_delta_pixels=pair['max_edge_delta_pixels'],
                    evidence=f"mapping/{e['sample_id']}/evidence.json",approval='pending'))
    write_csv(out/'mapping_evidence.csv',mapping_rows)
    print(f'Format review complete: {len(evidence)} samples; {len(mapping_rows)} target box matches',flush=True)
    return mapping_rows,coco_counts

def main(a):
    out=a.output.resolve()
    if ROOT not in out.parents:raise ValueError('Review output must stay inside research')
    out.mkdir(parents=True,exist_ok=True)
    snapshot_name='format_review_script_snapshot.py' if a.formats_only else 'review_script_snapshot.py'
    (out/snapshot_name).write_text(Path(__file__).read_text(encoding='utf-8'),encoding='utf-8')
    audit=json.loads((a.audit/'audit.json').read_text(encoding='utf-8'))
    rows=json.loads((a.audit/'manifest.json').read_text(encoding='utf-8'))
    groups=json.loads((out/'exact_groups.json').read_text(encoding='utf-8')) if a.formats_only else exact_review(rows,out)
    near=json.loads((out/'near_suspects.json').read_text(encoding='utf-8')) if a.formats_only else near_review(rows,out)
    if a.formats_only:
        by_relative={r['relative']:r for r in rows}
        for pair in near:
            for side in ('a','b'):
                r=by_relative[pair[side]]
                pair[side+'_boxes']=r['boxes'];pair[side+'_label']=r['label']
            write_json(out/'near'/pair['group_id']/'evidence.json',pair)
        write_json(out/'near_suspects.json',near)
    mappings,coco=format_review(rows,Path(audit['source']),out)
    cross=[g for g in groups if g['cross_split']]
    classifications=Counter(d['classification'] for g in groups for d in g['pairwise_annotation_differences'])
    summary=dict(exact_groups=len(groups),cross_split_groups=len(cross),cross_split_images=sum(len(g['members']) for g in cross),
        annotation_pair_classifications=dict(classifications),near_suspect_pairs=len(near),mapping_rows=len(mappings),
        audit_sha256=digest(a.audit/'audit.json'),manifest_sha256=digest(a.audit/'manifest.json'),
        script_sha256=digest(__file__),execution_mode='formats_only' if a.formats_only else 'all',
        detection_script_sha256=digest(out/'review_script_snapshot.py'),
        exact_evidence_sha256=digest(out/'exact_groups.json'),near_evidence_sha256=digest(out/'near_suspects.json'),
        formal_training_allowed=False,cleaning_performed=False)
    write_json(out/'summary.json',summary)
    checklist=[]
    for g in groups:
        checklist.append(dict(review_id=g['group_id'],kind='exact_cross_split' if g['cross_split'] else 'exact_within_split',
            evidence=g['evidence'],status='pending',approved_action='',reviewer='',rationale=''))
    for n in near:checklist.append(dict(review_id=n['group_id'],kind='suspected_near',evidence=f"near/{n['group_id']}/evidence.json",status='pending',approved_action='',reviewer='',rationale=''))
    checklist.append(dict(review_id='mapping_18_21',kind='class_mapping',evidence='mapping_evidence.csv',status='pending',approved_action='',reviewer='',rationale=''))
    write_csv(out/'review_checklist.csv',checklist)
    lines=['# Data review checklist','','```json',json.dumps(summary,indent=2),'```','',
        '[All 79 cross-split groups with paths, hashes and label differences](cross_split_79.md)',
        '[Machine-readable exact groups](exact_groups.json) | [Member table](exact_members.csv)',
        '[Near suspects](near_suspects.json) | [All screened candidates](near_candidates.json)',
        '[Near candidate comparison images](near_review.md)',
        '[Mapping box evidence](mapping_evidence.csv) | [Full mapping sources and counts](mapping_evidence.json)',
        '[Review decisions to fill](review_checklist.csv)','',
        'Exact pixel groups were independently verified by direct RGB byte comparison and fresh file SHA-256.',
        'Annotation inequality from the old audit is an exact numeric comparison, not an adjudicated annotation conflict.',
        'Geometry-first Hungarian matching: IoU >=0.5 or max edge difference <=2px; <=1px same-class changes are rounding candidates only.',
        'Near heuristic: 63 AC pHash bits from 32x32 grayscale DCT, Hamming <=6, aspect ratio difference <=3%, then 128x128 RGB MAE <=12 and gray correlation >=0.98.',
        'Near pairs are independent candidates, not transitive duplicate groups; rotations, crops and changed viewpoints may be missed.',
        'No patient IDs inferred, no source edits, no automatic cleaning, no training.', '',
        'Next: adjudicate mappings and each group; record reviewer/rationale/approved action; write corrected copies under research; split by confirmed patient and duplicate components; freeze final holdout; rerun full audit; train only after all blocking findings are resolved.']
    (out/'review.md').write_text('\n'.join(lines),encoding='utf-8')
    print('Review artifacts saved. Formal training remains blocked.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audit',type=Path,default=ROOT/'results'/'data_audit')
    p.add_argument('--output',type=Path,default=ROOT/'results'/'data_review')
    p.add_argument('--formats-only',action='store_true',help='Refresh format evidence; retain previously verified exact/near evidence')
    main(p.parse_args())
