"""Record user decisions and export box drafts; never edit dataset annotations."""
import csv
import json
import math
from pathlib import Path
import shutil
from collections import Counter
from PIL import Image, ImageDraw, ImageFont
from common import ROOT, digest, write_json
from audit_data import parse_label
from review_fissures import normalized_xyxy

OUT=ROOT/'results'/'fissure_review'
POLICY=ROOT/'configs'/'fissure_human_review_v1.json'

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def draft_box(coords,width,height):
    if len(coords)!=4 or not all(math.isfinite(x) for x in coords):raise ValueError('Invalid draft coordinates')
    x1,y1,x2,y2=coords
    if not 0<=x1<x2<=1 or not 0<=y1<y2<=1:raise ValueError('Draft box outside normalized bounds')
    # Integer edges are review suggestions, not final approved labels.
    px=[math.floor(x1*width),math.floor(y1*height),math.ceil(x2*width),math.ceil(y2*height)]
    return dict(original_class_id=7,clean_class_id=2,class_name='liewenshe',xyxy_normalized=coords,
        xyxy_pixels=px,yolo_normalized=[(x1+x2)/2,(y1+y2)/2,x2-x1,y2-y1],
        author='Codex visual draft',approval='pending_user_confirmation',model_score=None)

def decision(number,evidence,policy):
    present=number in policy['present_numbers'];pred=evidence['predictions']
    counts=(evidence['source_fissure_count'],evidence['coco_fissure_count'],evidence['clean_fissure_count'])
    if not present:
        annotation='confirmed_absent_fissure_only';action='preserve_all_other_classes_no_fissure_box'
        model='false_positive' if pred else 'correct_no_detection'
        comment='用户确认无裂纹；'+('裂纹预测框为误报。' if pred else '模型未出裂纹框，不能记为误报。')+'保留其他类别标注，不把整张图片改成空标签。'
    elif counts==(0,0,0):
        annotation='missing_fissure_annotation';action='add_fissure_box_pending_confirmation'
        model='false_negative_at_recorded_threshold' if not pred else ('partial_localization_user_confirmed' if number==24 else 'detection_present_extent_not_fully_adjudicated')
        comment='用户确认有裂纹；原TXT、COCO、clean均无裂纹框，待补框，保留其他类。'
        if number==27:comment+='冻结模型在conf=0.05下也未出框，同时属于漏标和本次模型漏检。'
        if number==24:comment+='原标签中没有裂纹框；此前看到的不完整框属于模型预测，是预测范围不足，不能误记成原裂纹框不完整。'
    elif number==26:
        annotation='existing_valid_local_box_with_missing_upper_region';action='keep_existing_box_add_missing_region_pending_confirmation'
        model='detection_present_upper_region_needs_annotation_review'
        comment='用户确认有裂纹；三份来源已有一个正确局部框，保留该框。上部/分支未被现有框完整覆盖，建议补充；是否扩展或合并旧框须另行确认。'
    else:
        raise ValueError('Unexpected existing positive annotation; requires explicit review')
    return dict(candidate_number=number,human_presence='present' if present else 'absent',human_decision='有裂纹' if present else '无裂纹',
        reviewer='User',review_date=policy['review_date'],annotation_issue=annotation,annotation_action=action,
        model_assessment=model,model_assessment_scope='Frozen checkpoint, conf=0.05, imgsz=640; not a claim about all model settings',
        human_comment=comment,box_approval='pending_user_confirmation' if present else 'not_applicable',
        preserve_existing_correct_fissure_boxes=True,preserve_other_class_annotations=True,dataset_labels_changed=False)

def panel(image,entries,title):
    ow,oh=image.size;scale=min(740/ow,580/oh)
    im=image.resize((max(1,round(ow*scale)),max(1,round(oh*scale))),Image.Resampling.LANCZOS);d=ImageDraw.Draw(im)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',15)
    for entry in entries:
        x1,y1,x2,y2=entry['xyxy'];color=entry['color'];coords=(x1*im.width/ow,y1*im.height/oh,x2*im.width/ow,y2*im.height/oh)
        d.rectangle(coords,outline=color,width=3)
        d.text((max(0,coords[0]),max(0,coords[1])),entry['label'],font=font,fill='white',stroke_width=2,stroke_fill='black')
    page=Image.new('RGB',(760,630),'white');page.paste(im,(10,40));ImageDraw.Draw(page).text((10,8),title,font=font,fill='black')
    return page

def apply():
    target=OUT/'manual_review'
    if (target/'summary.json').exists():raise FileExistsError('Human review already applied; preserve subsequent user box approvals')
    policy=read(POLICY);data=read(OUT/'candidates.json');rows=data['candidates']
    if len(rows)!=28 or {int(r['candidate_id'][:2]) for r in rows}!=set(range(1,29)):raise ValueError('Candidate numbering differs')
    if set(policy['present_numbers']) & set(policy['absent_numbers']) or set(policy['present_numbers'])|set(policy['absent_numbers'])!=set(range(1,29)):
        raise ValueError('Incomplete or contradictory user decisions')
    assert len(policy['present_numbers'])==25 and len(policy['absent_numbers'])==3
    target.mkdir(parents=True,exist_ok=True);backup=target/'before_human_review';backup.mkdir(exist_ok=True)
    for name in ('candidates.csv','candidates.json','summary.json','README.md'):
        if not (backup/name).exists():shutil.copyfile(OUT/name,backup/name)
    snapshots={};reviews=[];pending=[]
    for row in rows:
        number=int(row['candidate_id'][:2]);e=read(OUT/row['evidence'])
        if row['split'] not in ('train','val'):raise ValueError('Only train/val allowed')
        for path,expected in [(e['source_image'],e['image_sha256']),(e['image'],e['image_sha256']),
            (e['source_label'],e['source_label_sha256']),(e['clean_label'],e['clean_label_sha256']),
            (e['coco_source']['path'],e['coco_source']['sha256'])]:
            actual=digest(path)
            if actual!=expected:raise ValueError('Input changed since candidate review: '+path)
            snapshots[path]=actual
        source,_=parse_label(Path(e['source_label']).read_text(encoding='utf-8-sig'),21)
        clean,errors=parse_label(Path(e['clean_label']).read_text(encoding='utf-8-sig'),7)
        actual_counts=(sum(b[0]==7 for b in source),sum(b['category_id']==7 for b in e['coco']),sum(b[0]==2 for b in clean))
        if errors or actual_counts!=(e['source_fissure_count'],e['coco_fissure_count'],e['clean_fissure_count']):raise ValueError('Label count mismatch')
        result=decision(number,e,policy);result['candidate_id']=row['candidate_id']
        proposals=[]
        if result['human_presence']=='present':
            spec=policy['proposals'][str(number)]
            proposals=[draft_box(box,e['width'],e['height']) for box in spec['boxes']]
            folder=target/'pending_boxes'/row['candidate_id'];folder.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(e['image'],folder/('original'+Path(e['image']).suffix))
            shutil.copyfile(e['source_label'],folder/'source_txt.txt');shutil.copyfile(e['clean_label'],folder/'clean_label.txt')
            shutil.copyfile(OUT/'candidates'/row['candidate_id']/'coco_annotations.json',folder/'coco_annotations.json')
            shutil.copyfile(OUT/'candidates'/row['candidate_id']/'predictions.json',folder/'model_predictions_reference.json')
            suggestion=dict(candidate_id=row['candidate_id'],decision=result,width=e['width'],height=e['height'],
                existing_fissure_boxes=[b for b in clean if b[0]==2],existing_other_classes=[b for b in clean if b[0]!=2],
                proposed_additions=proposals,proposed_replacements=[],proposal_note=spec['note'],
                instance_policy='Connected visible branches may be grouped; draft boundaries and instance splitting require confirmation.',
                reference_predictions=e['predictions'],automatic_application=False)
            write_json(folder/'suggestions.json',suggestion)
            with Image.open(e['image']) as source_image:im=source_image.convert('RGB')
            old=[dict(xyxy=b[1:],color='lime' if b[0]==2 else 'cyan',label=f'Existing ID {b[0]}') for b in normalized_xyxy(clean,im.size)]
            pred=[dict(xyxy=p['xyxy_pixels'],color='red',label=f"REF ID 2 score={p['model_score']:.3f}") for p in e['predictions']]
            draft=[dict(xyxy=p['xyxy_pixels'],color='orange',label=f'DRAFT {i+1} ID 2 NOT APPROVED') for i,p in enumerate(proposals)]
            pages=[panel(im,[],f"{number:02d} Original (user confirmed fissure)"),panel(im,old,'Existing clean labels (green fissure; cyan other classes)'),
                panel(im,pred,'Frozen model references only, conf >= 0.05'),panel(im,old+draft,'Orange: proposed additions; existing labels preserved')]
            sheet=Image.new('RGB',(1520,1260),'white')
            for i,page in enumerate(pages):sheet.paste(page,((i%2)*760,(i//2)*630))
            sheet.save(folder/'revision_comparison.jpg')
            panel(im,old+draft,'UNAPPROVED DRAFT - confirm boundaries and instance count').save(folder/'suggestion_overlay.jpg')
            result['suggestions']=str((folder/'suggestions.json').relative_to(OUT)).replace('\\','/')
            result['revision_comparison']=str((folder/'revision_comparison.jpg').relative_to(OUT)).replace('\\','/')
            result['suggestion_note']=spec['note'];result['proposed_box_count']=len(proposals)
            pending.append(dict(candidate_number=number,candidate_id=row['candidate_id'],split=row['split'],action=result['annotation_action'],
                annotation_issue=result['annotation_issue'],model_assessment=result['model_assessment'],
                existing_fissure_count=e['clean_fissure_count'],proposed_addition_count=len(proposals),
                source_image=e['source_image'],suggestions=result['suggestions'],comparison=result['revision_comparison'],
                note=spec['note'],box_approval='pending_user_confirmation',approved_boxes='',reviewer_comment=''))
        else:
            result.update(suggestions='',revision_comparison='',suggestion_note='No fissure addition; preserve all other class annotations.',proposed_box_count=0)
        write_json(target/'decisions'/f"{row['candidate_id']}.json",result)
        for key in ('human_decision','human_comment','reviewer','review_date','human_presence','annotation_issue','annotation_action','model_assessment','box_approval','proposed_box_count','revision_comparison','suggestions'):
            row[key]=result[key]
        reviews.append(result)
    for path,sha in snapshots.items():
        if digest(path)!=sha:raise RuntimeError('Source/clean input changed while preparing review')
    summary=dict(review_date=policy['review_date'],candidate_count=len(rows),confirmed_present=sum(x['human_presence']=='present' for x in reviews),
        confirmed_absent=sum(x['human_presence']=='absent' for x in reviews),
        missing_annotation_images=sum(x['annotation_issue']=='missing_fissure_annotation' for x in reviews),
        existing_local_box_preserved_images=[x['candidate_number'] for x in reviews if x['annotation_issue']=='existing_valid_local_box_with_missing_upper_region'],
        false_positive_images=[x['candidate_number'] for x in reviews if x['model_assessment']=='false_positive'],
        false_negative_images_at_conf_005=[x['candidate_number'] for x in reviews if x['model_assessment']=='false_negative_at_recorded_threshold'],
        partial_model_extent_images=[24],correct_no_detection_images=[x['candidate_number'] for x in reviews if x['model_assessment']=='correct_no_detection'],
        pending_box_images=len(pending),suggested_addition_boxes=sum(p['proposed_addition_count'] for p in pending),
        boxes_user_approved=0,source_and_clean_inputs_verified_unchanged=True,dataset_label_edits=False,test_access=False,training_started=False,
        model_sha256=data['metadata']['weights_sha256'],policy_sha256=digest(POLICY),script_sha256=digest(__file__))
    assert summary['confirmed_present']==25 and summary['confirmed_absent']==3
    assert summary['false_positive_images']==[16,22] and summary['false_negative_images_at_conf_005']==[27]
    assert summary['missing_annotation_images']==24 and summary['pending_box_images']==25
    def table(path,entries):
        with path.open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in entries for k in r)))
            writer.writeheader();writer.writerows(entries)
    table(OUT/'candidates.csv',rows);write_json(OUT/'candidates.json',dict(data,human_review_summary=summary,candidates=rows))
    write_json(OUT/'summary.json',dict(read(backup/'summary.json'),human_review=summary))
    table(target/'review_checklist.csv',reviews);table(target/'pending_box_checklist.csv',pending)
    write_json(target/'review.json',dict(summary=summary,decisions=reviews))
    write_json(target/'input_integrity.json',dict(inputs=snapshots,verified_unchanged=True))
    shutil.copyfile(POLICY,target/'user_decisions_and_draft_boxes.json')
    (target/'apply_review_snapshot.py').write_text(Path(__file__).read_text(encoding='utf-8'),encoding='utf-8')
    lines=['# 裂纹人工复核与修订建议','',
        '按原有1–28编号登记，人工存在性结论由用户于2026-11-19提供；建议框由Codex草拟，尚未获用户确认。',
        '**25张有裂纹、3张无裂纹（16、22、28）。** 已更新上级candidates.csv与candidates.json；原挖掘理由仅为历史线索，以本次人工结论为准。', '',
        '## 关键区分', '',
        '- 16、22：用户确认无裂纹，冻结模型有裂纹预测，因此为误报；保留其他类别标注。',
        '- 28：用户确认无裂纹，模型没有裂纹框，因此为正确未检出，不记作误报。',
        '- 27：TXT/COCO/clean裂纹框均为0；模型在conf=0.05下也无框。人工确认有裂纹，故同时存在原标注漏标和本次模型漏检。',
        '- 24：三份标签均无裂纹框，不完整的框来自模型。应记为原标注漏标、模型预测范围不全，而非原裂纹框部分覆盖。建议新建更完整的裂纹框，其他类不改。',
        '- 26：三份来源已有一个局部裂纹框；该局部框保留。上部与分支范围待补充确认，未自动扩大或替换旧框。', '',
        '24张阳性图缺裂纹框；26号另有一个应保留的局部框及待补充区域，共25张进入修订建议目录。', '',
        '[全部28张复核清单](review_checklist.csv) / [25张待补框或补充范围清单](pending_box_checklist.csv) / [完整记录](review.json)', '',
        '## 待确认建议', '',
        '每例单独保存原图、原TXT、COCO、clean标签副本、冻结模型参考框、suggestions.json及修订四联图。橙色框是待确认建议，不是模型真值，也不是已修改标注；绿色是已有裂纹框，青色是其他类，红色仅为模型预测。',
        '25张给出26个建议新增区域（8号暂分两个区域）。网络状/连通分支是否拆为多个实例及所有边界均须用户确认。建议不附置信度，不生成可直接混入训练的YOLO补标文件。',
        '26号采用保留旧局部框并建议补充上部区域的草案，proposed_replacements为空；如果你希望扩展/合并为单框，需明确批准后再实施。', '',
        '| 编号 | 标注处理 | 模型判断 | 修订建议 |','|---|---|---|---|']
    for r in reviews:
        suggestion=f"[四联图]({r['revision_comparison'].removeprefix('manual_review/')}) / [建议框]({r['suggestions'].removeprefix('manual_review/')})" if r['suggestions'] else '不补裂纹框，保留其他类别'
        lines.append(f"| {r['candidate_number']:02d} | {r['annotation_action']} | {r['model_assessment']} | {suggestion} |")
    lines += ['', '## 数据完整性', '',
        '只更新research/results/fissure_review内的人工清单和建议产物，另新增research脚本与决策配置。原TXT、COCO、clean图片和标签的哈希前后核验一致；未读测试集图片、未补标、未训练。',
        '原清单/JSON/摘要/说明已备份至before_human_review。scan.json、selection.json及候选evidence.json保留为历史证据，不用新人工结论覆写当时的模型输出。',
        '模型漏检与误报判断仅适用于本次冻结权重、conf=0.05和imgsz=640；其他阳性图的框精度未逐框批准，不能将“有预测”直接当作正确定位。',
        '下步仅需在pending_box_checklist.csv中确认或调整建议框。未经确认的建议不得用于训练。']
    (target/'README.md').write_text('\n'.join(lines),encoding='utf-8')
    (OUT/'README.md').write_text('# 裂纹复核：人工结论已更新\n\n25张有裂纹、3张无裂纹（16、22、28）；候选编号保持不变。\n\n[人工复核说明和修订建议](manual_review/README.md) / [更新后的28张清单](candidates.csv) / [25张待补框清单](manual_review/pending_box_checklist.csv)。\n\n27号同时漏标与本次模型漏检；24号是原标注缺失及模型框范围不足；26号正确局部框保留，额外区域待确认。16、22为误报，28正确未检出。\n\n建议框均待确认，本轮未改原始数据、clean_v1或测试集，也未训练。初次挖掘记录见manual_review/before_human_review/README.md。\n',encoding='utf-8')
    write_json(target/'summary.json',summary)
    print('Updated 28 reviews: 25 present, 3 absent. Saved 25 pending box proposals; dataset labels unchanged.')

if __name__=='__main__':apply()
