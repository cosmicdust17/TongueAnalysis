"""Read-only train/val fissure candidate mining and manual-review export."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random
import shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from common import ROOT, digest, write_json
from audit_data import parse_label

OUT=ROOT/'results'/'fissure_review'

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))

def normalized_xyxy(boxes,size):
    w,h=size
    return [[c,(x-bw/2)*w,(y-bh/2)*h,(x+bw/2)*w,(y+bh/2)*h] for c,x,y,bw,bh in boxes]

def overlaps(pred,truth):
    area=max(0,pred[2]-pred[0])*max(0,pred[3]-pred[1]);ious=[];covers=[]
    for box in truth:
        b=box[1:];inter=max(0,min(pred[2],b[2])-max(pred[0],b[0]))*max(0,min(pred[3],b[3])-max(pred[1],b[1]))
        ba=max(0,b[2]-b[0])*max(0,b[3]-b[1])
        ious.append(inter/max(1e-12,area+ba-inter));covers.append(inter/max(1e-12,area))
    return max(ious,default=0),max(covers,default=0)

def draw_panel(image,boxes,title,target_id=2):
    im=image.copy();w,h=im.size;im.thumbnail((620,500));sx=im.width/w;sy=im.height/h
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',15);d=ImageDraw.Draw(im)
    for b in boxes:
        c,x1,y1,x2,y2=b[:5];score=b[5] if len(b)>5 else None
        color='red' if score is not None else ('lime' if c==target_id else 'cyan')
        d.rectangle((x1*sx,y1*sy,x2*sx,y2*sy),outline=color,width=3)
        text=f'ID {c}'+(f' score={score:.3f}' if score is not None else '')
        d.text((max(0,x1*sx),max(0,y1*sy)),text,font=font,fill='white',stroke_width=2,stroke_fill='black')
    canvas=Image.new('RGB',(640,550),'white');canvas.paste(im,(10,40));ImageDraw.Draw(canvas).text((10,10),title,font=font,fill='black')
    return canvas

def contact(rows,path,predictions=True):
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',14)
    canvas=Image.new('RGB',(1200,320*((len(rows)+3)//4)),'white');d=ImageDraw.Draw(canvas)
    for i,r in enumerate(rows):
        with Image.open(r['image']) as source:im=source.convert('RGB')
        w,h=im.size;im.thumbnail((290,265));draw=ImageDraw.Draw(im)
        if predictions:
            for b in r.get('novel_predictions',[]):
                x1,y1,x2,y2=b['xyxy_pixels'];draw.rectangle((x1*im.width/w,y1*im.height/h,x2*im.width/w,y2*im.height/h),outline='red',width=2)
        x=i%4*300;y=i//4*320
        canvas.paste(im,(x+5,y+42));d.text((x+5,y+2),r['review_key']+' '+r['split'],font=font,fill='black')
        d.text((x+5,y+21),Path(r['image']).name[:26],font=font,fill='black')
    path.parent.mkdir(parents=True,exist_ok=True);canvas.save(path)

def scan(a):
    from ultralytics import YOLO
    import torch
    if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable; no automatic CPU scan')
    if (OUT/'scan.json').exists():raise FileExistsError('Scan already exists; reuse it for export')
    OUT.mkdir(parents=True,exist_ok=True)
    frozen=OUT/'model_snapshot'/'best.pt';frozen.parent.mkdir(exist_ok=True)
    before=digest(a.weights);shutil.copyfile(a.weights,frozen)
    if digest(a.weights)!=before or digest(frozen)!=before:raise RuntimeError('Weight file changed during snapshot')
    model=YOLO(str(frozen))
    if model.names.get(2)!='liewenshe' or len(model.names)!=7:raise ValueError('Expected clean_v1 checkpoint with fissure ID 2')
    all_rows=read(ROOT/'results'/'clean_v1'/'clean_manifest.json')
    rows=[r for r in all_rows if r['status']=='retained' and r['original_split'] in ('train','val')]
    docs={};ann_index={};catnames={}
    for split in ('train','val'):
        p=Path(next(r['corroboration']['coco_json']['path'] for r in rows if r['original_split']==split))
        doc=read(p);docs[split]=dict(path=str(p),sha256=digest(p))
        idx=defaultdict(list)
        for x in doc['annotations']:idx[x['image_id']].append(x)
        ann_index[split]=idx;catnames[split]=doc['categories']
    scanned=[]
    for start in range(0,len(rows),8):
        batch=rows[start:start+8]
        for r in batch:
            if digest(r['destination'])!=r['image_sha256'] or digest(r['destination_label'])!=r['destination_label_sha256'] or digest(r['source_label'])!=r['source_label_sha256']:
                raise ValueError('Input changed after cleaning')
        results=model.predict([r['destination'] for r in batch],classes=[2],conf=a.conf,iou=.5,
            imgsz=640,batch=8,device=0,half=False,verbose=False,save=False,max_det=100)
        for r,result in zip(batch,results):
            split=r['original_split'];clean,errors=parse_label(Path(r['destination_label']).read_text(encoding='utf-8-sig'),7)
            raw,raw_errors=parse_label(Path(r['source_label']).read_text(encoding='utf-8-sig'),21)
            if errors or raw_errors:raise ValueError('Invalid label in retained train/val')
            h,w=result.orig_shape;truth=normalized_xyxy([b for b in clean if b[0]==2],(w,h))
            predictions=[]
            for box in result.boxes:
                xy=box.xyxy[0].tolist();score=float(box.conf.item());iou,cover=overlaps(xy,truth)
                predictions.append(dict(model_class_id=2,original_class_id=7,class_name='liewenshe',model_score=score,
                    xyxy_pixels=xy,max_gt_fissure_iou=iou,max_gt_fissure_prediction_coverage=cover,
                    novel_region=iou<.1 and cover<.2))
            novel=[p for p in predictions if p['novel_region']]
            anns=ann_index[split][r['corroboration']['image_id']];coco=[]
            for ann in anns:
                x,y,bw,bh=ann['bbox'];coco.append(dict(annotation_id=ann['id'],category_id=ann['category_id'],
                    bbox_xywh_pixels=ann['bbox'],normalized_yolo=[ann['category_id'],(x+bw/2)/w,(y+bh/2)/h,bw/w,bh/h]))
            source_fissure=[b for b in raw if b[0]==7];coco_fissure=[b for b in coco if b['category_id']==7]
            scanned.append(dict(review_key=f'S{len(scanned)+1:04d}',split=split,image=r['destination'],source_image=r['source_image'],
                image_sha256=r['image_sha256'],source_label=r['source_label'],source_label_sha256=digest(r['source_label']),
                clean_label=r['destination_label'],clean_label_sha256=digest(r['destination_label']),
                width=w,height=h,source_txt_boxes=raw,clean_boxes=clean,coco=coco,coco_source=docs[split],coco_image_id=r['corroboration']['image_id'],
                source_fissure_count=len(source_fissure),coco_fissure_count=len(coco_fissure),clean_fissure_count=len(truth),
                predictions=predictions,novel_predictions=novel,novel_max_score=max((p['model_score'] for p in novel),default=0)))
        if start%200==0:print(f'Predicted train/val: {min(start+8,len(rows))}/{len(rows)}',flush=True)
    metadata=dict(weights_source=str(a.weights.resolve()),weights_sha256=before,frozen_weights=str(frozen),model_names=model.names,
        original_fissure_id=7,clean_fissure_id=2,confidence=a.conf,nms_iou=.5,novel_gt_iou_max=.1,novel_prediction_coverage_max=.2,
        imgsz=640,seed=42,splits=['train','val'],torch=torch.__version__,ultralytics=__import__('ultralytics').__version__,
        manifest_sha256=digest(ROOT/'results'/'clean_v1'/'clean_manifest.json'),coco_sources=docs,
        note='Candidate mining, not annotation adjudication. Train predictions are in-sample; no test images read.')
    write_json(OUT/'scan.json',dict(metadata=metadata,images=scanned))
    shortlist=[]
    for split in ('train','val'):
        pool=sorted([r for r in scanned if r['split']==split and r['novel_predictions']],key=lambda r:(r['clean_fissure_count']!=0,-r['novel_max_score'],r['review_key']))[:40]
        shortlist.extend(pool)
        for k in range(0,len(pool),20):contact(pool[k:k+20],OUT/'screening'/f'{split}_top_{k//20+1}.jpg')
    random_pool=random.Random(42).sample(scanned,40)
    for k in range(0,40,20):contact(random_pool[k:k+20],OUT/'screening'/f'random_{k//20+1}.jpg',False)
    write_json(OUT/'shortlist.json',[dict(review_key=r['review_key'],split=r['split'],file=Path(r['image']).name,
        score=r['novel_max_score'],gt=r['clean_fissure_count']) for r in shortlist])
    write_json(OUT/'random_sample.json',[dict(review_key=r['review_key'],split=r['split'],image=r['image'],score=r['novel_max_score'],gt=r['clean_fissure_count']) for r in random_pool])
    (OUT/'script_snapshot.py').write_text(Path(__file__).read_text(encoding='utf-8'),encoding='utf-8')
    print(f'Scan complete: {len(scanned)} train/val images; {sum(bool(r["novel_predictions"]) for r in scanned)} with novel-region predictions.')

def export(a):
    if (OUT/'manual_review'/'summary.json').exists():
        raise FileExistsError('Human-reviewed checklist exists; export would overwrite user decisions')
    scan=read(OUT/'scan.json');selection=read(OUT/'selection.json');by_id={r['review_key']:r for r in scan['images']}
    assert 20<=len(selection['candidates'])<=30
    assert len({x['review_key'] for x in selection['candidates']})==len(selection['candidates'])
    table=[]
    for k,choice in enumerate(selection['candidates'],1):
        r=by_id[choice['review_key']];assert r['split'] in ('train','val')
        if digest(r['image'])!=r['image_sha256'] or digest(r['source_image'])!=r['image_sha256'] or digest(r['source_label'])!=r['source_label_sha256'] or digest(r['clean_label'])!=r['clean_label_sha256'] or digest(r['coco_source']['path'])!=r['coco_source']['sha256']:
            raise ValueError('Reviewed image or annotation changed')
        folder=OUT/'candidates'/f'{k:02d}_{r["review_key"]}';folder.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(r['image'],folder/('original'+Path(r['image']).suffix))
        shutil.copyfile(r['source_label'],folder/'source_txt.txt');shutil.copyfile(r['clean_label'],folder/'clean_label.txt')
        write_json(folder/'coco_annotations.json',dict(source=r['coco_source'],image_id=r['coco_image_id'],annotations=r['coco']))
        write_json(folder/'predictions.json',dict(model=scan['metadata'],predictions=r['predictions']))
        write_json(folder/'evidence.json',dict(candidate=choice,**r,review_status='pending_human_review',automatic_label_changes=False))
        with Image.open(r['image']) as source:im=source.convert('RGB')
        size=im.size
        panels=[draw_panel(im,normalized_xyxy(r['source_txt_boxes'],size),'Original TXT (fissure original ID 7)',7),
            draw_panel(im,normalized_xyxy([x['normalized_yolo'] for x in r['coco']],size),'COCO source (fissure original ID 7)',7),
            draw_panel(im,normalized_xyxy(r['clean_boxes'],size),'Clean v1 (fissure new ID 2)'),
            draw_panel(im,[[2,*p['xyxy_pixels'],p['model_score']] for p in r['predictions']],f'Frozen model, conf >= {scan["metadata"]["confidence"]}')]
        canvas=Image.new('RGB',(1280,1100),'white')
        for i,p in enumerate(panels):canvas.paste(p,((i%2)*640,(i//2)*550))
        canvas.save(folder/'comparison.jpg')
        row=dict(candidate_id=f'{k:02d}_{r["review_key"]}',split=r['split'],source_image=r['source_image'],
            clean_image=r['image'],image_sha256=r['image_sha256'],source_txt_fissures=r['source_fissure_count'],
            coco_fissures=r['coco_fissure_count'],clean_fissures=r['clean_fissure_count'],
            highest_novel_prediction_score=r['novel_max_score'] if r['novel_predictions'] else None,selection_method=choice['method'],candidate_reason=choice['reason'],
            comparison=f'candidates/{folder.name}/comparison.jpg',evidence=f'candidates/{folder.name}/evidence.json',
            human_decision='',human_comment='',reviewer='')
        table.append(row)
    with (OUT/'candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
    write_json(OUT/'candidates.json',dict(metadata=scan['metadata'],selection=selection,candidates=table))
    split_counts=Counter(r['split'] for r in table)
    random_count=sum(r['selection_method']=='random_visual_blindspot' for r in table)
    source_counts=Counter((r['source_txt_fissures'],r['coco_fissures'],r['clean_fissures']) for r in table)
    summary=dict(candidates=len(table),split_counts=dict(split_counts),confidence=scan['metadata']['confidence'],
        scanned_images=len(scan['images']),novel_prediction_images=sum(bool(r['novel_predictions']) for r in scan['images']),
        random_checked=len(read(OUT/'random_sample.json')),random_blindspot_candidates=random_count,
        weights_sha256=scan['metadata']['weights_sha256'],test_image_access=False,label_edits=False,training_started=False)
    write_json(OUT/'summary.json',summary)
    lines=['# 疑似裂纹漏标候选','',
        f'共{len(table)}张，仅train/val。原始裂纹ID=7，clean_v1 ID=2。没有补标、训练或读取测试集图片。',
        f"本次扫描{summary['scanned_images']}张train/val图片，低阈值conf={summary['confidence']}，NMS IoU=0.5；{summary['novel_prediction_images']}张存在未被现有裂纹框覆盖的预测区域。未覆盖区域定义为对现有裂纹框的最大IoU<0.1且预测框被覆盖比例<0.2。",
        f"最终{len(table)}张：train {split_counts['train']}张、val {split_counts['val']}张；{len(table)-random_count}张来自预测辅助筛查，{random_count}张来自seed=42的{summary['random_checked']}张随机抽查且模型未出框。{source_counts[(0,0,0)]}张三份来源均无裂纹框，另{source_counts[(1,1,1)]}张三份来源均有1个裂纹框，待检查框外漏标或边界差异。数量一致不代表临床真值正确。",
        '每例包含原图副本、原TXT、COCO标注、清洗标签、全部低阈值裂纹预测，以及四联对照图。绿色/青色为既有标签，红色为预测；框上显示所在格式的ID，不能将不同格式的2号含义混用。',
        '模型分数不是医学概率；训练集预测为训练内结果。低阈值可能把正常沟纹、反光或舌缘误报为裂纹。三份标签一致缺框也只能提示共同漏标可能，不能确认医学真值。',
        '[可填写人工决定的CSV](candidates.csv) / [完整JSON](candidates.json) / [随机抽样记录](random_sample.json)','',
        '| 候选 | Split | TXT/COCO/clean裂纹框数 | 最高未覆盖预测分 | 原因 | 对照 |','|---|---|---|---|---|---|']
    for r in table:
        score=f"{r['highest_novel_prediction_score']:.4f}" if r['highest_novel_prediction_score'] is not None else '无达到阈值的预测'
        lines.append(f"| {r['candidate_id']} | {r['split']} | {r['source_txt_fissures']}/{r['coco_fissures']}/{r['clean_fissures']} | {score} | {r['candidate_reason']} | [四联图]({r['comparison']}) / [依据]({r['evidence']}) |")
    lines += ['', '筛查设置及模型SHA见candidates.json/scan.json。候选选择与目视记录见selection.json。原始TXT和清洗标签哈希导出时再次核对；源COCO仅读取train.json与val.json。',
        '复现：在工程根目录运行 research/.venv/Scripts/python.exe research/training/review_fissures.py export；scan子命令会拒绝覆盖已有扫描。人工确认后再另行制定补标规则，本轮标签保持原样。']
    lines += ['', '随机抽查中未入选的图片不是已确认负样本。无达到阈值的预测用null/空值记录，不伪造0分预测；scan.json中的novel_max_score=0仅为排序占位值。',
        f"使用冻结的clean_v1 best.pt，SHA-256：`{scan['metadata']['weights_sha256']}`。预测权重副本保存在model_snapshot/best.pt，不使用原21类冒烟权重。"]
    (OUT/'README.md').write_text('\n'.join(lines),encoding='utf-8')
    (OUT/'export_script_snapshot.py').write_text(Path(__file__).read_text(encoding='utf-8'),encoding='utf-8')
    print(f'Exported {len(table)} candidates. Labels unchanged; no training or test access.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['scan','export'])
    p.add_argument('--weights',type=Path,default=ROOT/'results'/'formal'/'clean-v1-yolo11n-seed42'/'weights'/'best.pt')
    p.add_argument('--conf',type=float,default=.05)
    a=p.parse_args();scan(a) if a.action=='scan' else export(a)
