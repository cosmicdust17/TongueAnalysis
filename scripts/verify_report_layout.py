"""Generate two real reports and compare the app contract with PDF text."""
from pathlib import Path
from time import perf_counter,sleep
from io import BytesIO
import json
import httpx
from pypdf import PdfReader
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/pdf/report-layout-v2';OUT.mkdir(parents=True,exist_ok=True)
forbidden=['模型','Qwen','YOLO','模板','联调','待复核','生成时快照','页面文本块','段落待核对']
def compact(s):return ''.join(s.split())
with httpx.Client(base_url='http://127.0.0.1:8000/api/v1',timeout=60,trust_env=False) as c:
    r=c.post('/auth/dev-login',json={'role':'user'});r.raise_for_status();login=r.json()
    c.headers['Authorization']='Bearer '+login['access_token']
    def call(method,path,**kw):
        r=c.request(method,path,**kw);r.raise_for_status();return r
    original=call('GET','/users/me').json()
    old=call('GET','/reports?page_size=1').json()['items']
    records=[]
    try:
        for name,symptoms,duration,age,gender in [('sleep','最近一周入睡困难，白天乏力，偶尔口干。','近一周',35,'女'),('digestion','最近三天食欲不振，餐后腹胀，睡眠尚可。','近三天',68,'男')]:
            call('PUT','/users/me',json={'nickname':original['nickname'],'age':age,'gender':gender})
            path=ROOT/'storage/uploads/4809160ad7274c03ae3931dd21f29c9a.jpg'
            fid=call('POST','/uploads',files={'file':('tongue.jpg',path.read_bytes(),'image/jpeg')}).json()['id']
            aid=call('POST','/analyses',json={'image_id':fid,'symptoms':symptoms,'duration':duration}).json()['id']
            started=perf_counter()
            for _ in range(360):
                task=call('GET','/analyses/'+aid).json()
                if task['status']=='completed':break
                assert task['status']!='failed','Actual inference failed, see server log'
                sleep(1)
            assert task['status']=='completed'
            report=call('GET','/reports/'+task['report_id']).json();v=report['content']['presentation']
            assert v['symptoms_text']==symptoms and v['duration']==duration
            assert v['identity']['age']==age and v['identity']['gender']==gender and v['identity']['user_id']==original['id']
            public=json.dumps(v,ensure_ascii=False)
            assert all(x not in public for x in forbidden)
            pdf=call('GET','/reports/'+report['id']+'/pdf').content
            (OUT/(name+'.pdf')).write_bytes(pdf)
            text=''.join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)
            for value in [v['analysis'],v['symptoms_text'],v['duration'],*v['identity'].values(),*[i['text'] for i in v['advice_items']]]:
                assert compact(str(value)) in compact(text),str(value)
            assert all(x not in text for x in forbidden)
            for entry in v['evidence']:
                for key in ['quote','explanation','reference']:assert compact(entry[key]) in compact(text)
            again=call('GET','/reports/'+report['id']+'/pdf').content
            assert compact(text)==compact(''.join(p.extract_text() for p in PdfReader(BytesIO(again)).pages))
            assert call('GET','/reports/'+report['id']).json()['content']['presentation']==v
            (OUT/(name+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
            records.append({'case':name,'report_id':report['id'],'analysis_id':aid,'seconds':perf_counter()-started,'citations':len(v['evidence']),'boxes':len(report['content']['annotations']['detections'])})
            print('PASS',json.dumps(records[-1]),flush=True)
        a=json.loads((OUT/'sleep.json').read_text(encoding='utf8'))['content']['presentation']
        b=json.loads((OUT/'digestion.json').read_text(encoding='utf8'))['content']['presentation']
        assert a['advice_items']!=b['advice_items']
        if old:
            rid=old[0]['id'];legacy=call('GET','/reports/'+rid).json()
            v=legacy['content']['presentation'];assert all(x not in json.dumps(v,ensure_ascii=False) for x in forbidden)
            (OUT/'legacy.pdf').write_bytes(call('GET','/reports/'+rid+'/pdf').content)
            (OUT/'legacy.json').write_text(json.dumps(legacy,ensure_ascii=False,indent=2),encoding='utf8')
            records.append({'case':'legacy','report_id':rid,'passed':True})
        (OUT/'checks.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf8')
    finally:
        call('PUT','/users/me',json={'nickname':original['nickname'],'age':original['profile'].get('age'),'gender':original['profile'].get('gender') or '未填写'})
