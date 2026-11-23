"""Generate three labelled acceptance reports with live YOLO, preserving test records."""
from pathlib import Path
from io import BytesIO
import json
import random
from time import sleep,monotonic
import httpx
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/pdf/annotation-check'
OUT.mkdir(parents=True,exist_ok=True)
photo=ROOT/'storage/uploads/4809160ad7274c03ae3931dd21f29c9a.jpg'
Image.frombytes('RGB',(640,400),random.Random(42).randbytes(640*400*3)).save(OUT/'empty.jpg')
sources={'boxed':photo,'empty':OUT/'empty.jpg',
         'portrait':ROOT/'research/datasets/clean_v1/val/images/tongue (113).jpg'}
records=[]
with httpx.Client(base_url='http://127.0.0.1:8000',timeout=120,trust_env=False) as c:
    session=c.post('/api/v1/auth/dev-login',json={'role':'user'});session.raise_for_status()
    h={'Authorization':'Bearer '+session.json()['access_token']}
    for name,path in sources.items():
        def request(method,url,**kw):
            r=c.request(method,'/api/v1'+url,headers=h,**kw);r.raise_for_status();return r
        fid=request('POST','/uploads',files={'file':(name+'.jpg',path.read_bytes(),'image/jpeg')}).json()['id']
        aid=request('POST','/analyses',json={'image_id':fid,'symptoms':'标注验收：'+name,'duration':'近一周'}).json()['id']
        end=monotonic()+120
        while monotonic()<end:
            task=request('GET','/analyses/'+aid).json()
            if task['status']=='completed':break
            assert task['status']!='failed',task['error']
            sleep(.3)
        else:raise RuntimeError('Timeout')
        rid=task['report_id']
        report=request('GET','/reports/'+rid).json()
        snap=report['content']['annotations']
        if name=='empty':assert not snap['detections']
        else:assert snap['detections']
        assert snap['model_version'].startswith('clean-v1')
        assert request('GET','/reports/'+rid).json()['content']['annotations']==snap
        (OUT/(name+'.pdf')).write_bytes(request('GET','/reports/'+rid+'/pdf').content)
        records.append({'case':name,'report_id':rid,'annotations':snap})
    assert request('GET','/reports').json()['total']>=3
(OUT/'reports.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{'case':r['case'],'report_id':r['report_id'],'boxes':len(r['annotations']['detections'])} for r in records]))
