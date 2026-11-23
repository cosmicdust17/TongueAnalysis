import hashlib,json,os,time
from pathlib import Path
from io import BytesIO
from PIL import Image,ImageOps
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'research/multimodal/results/fissure-regression'
os.environ['YOLO_CONFIG_DIR']=str(OUT/'yolo-settings')
Path(os.environ['YOLO_CONFIG_DIR']).mkdir(parents=True,exist_ok=True)
from ultralytics import YOLO
review=json.loads((ROOT/'research/results/fissure_review/manual_review/review.json').read_text(encoding='utf-8'))
rows=[]
models={}
for version in ('v1','v2'):
    path=ROOT/f'research/results/formal/clean-{version}-yolo11n-seed42/weights/best.pt'
    models[version]=(YOLO(str(path)),hashlib.sha256(path.read_bytes()).hexdigest())
for decision in review['decisions']:
    cid=decision['candidate_id']; folder=ROOT/'research/results/fissure_review/candidates'/cid
    info=json.loads((folder/'evidence.json').read_text(encoding='utf-8'))
    assert info['split'] in ('train','val')
    with Image.open(folder/'original.jpg') as image:
        im=ImageOps.exif_transpose(image).convert('RGB'); im.thumbnail((2048,2048))
        data=BytesIO(); im.save(data,format='JPEG',quality=92); data.seek(0)
        import numpy as np
        bgr=np.asarray(Image.open(data).convert('RGB'))[:,:,::-1]
    row={'case':cid,'human':decision['human_presence'],'split':info['split'],
         'used_for_training':info['split']=='train','used_for_review':True,'test':False,'models':{}}
    for version,(model,sha) in models.items():
        t=time.perf_counter(); result=model.predict(bgr,imgsz=640,conf=.218,device='cpu',verbose=False)[0]
        row['models'][version]={'sha256':sha,'seconds':time.perf_counter()-t,'conf':.218,'imgsz':640,
            'boxes':[{'class_name':model.names[int(b.cls.item())],'score':float(b.conf.item()),'xyxy':b.xyxy[0].tolist()} for b in result.boxes]}
    rows.append(row)
(OUT/'yolo-comparison.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
for version in models:
    tp=fn=fp=tn=0
    for r in rows:
        predicted=any(b['class_name']=='liewenshe' for b in r['models'][version]['boxes'])
        positive=r['human']=='present'
        tp+=predicted and positive; fn+=not predicted and positive; fp+=predicted and not positive; tn+=not predicted and not positive
    print(version,dict(tp=tp,fn=fn,fp=fp,tn=tn),flush=True)
