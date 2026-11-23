"""Read the saved real report and verify repeat exports without invoking inference."""
from pathlib import Path
from io import BytesIO
import hashlib,json,time
import httpx
from pypdf import PdfReader
from PIL import Image, ImageChops
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/e2e'
report=json.loads((OUT/'report.json').read_text(encoding='utf8'))
rid=report['id']
with httpx.Client(base_url='http://127.0.0.1:8000/api/v1',trust_env=False,timeout=60) as c:
    login=c.post('/auth/dev-login',json={'role':'user'});login.raise_for_status()
    c.headers['Authorization']='Bearer '+login.json()['access_token']
    def get(path):
        r=c.get(path);r.raise_for_status();return r
    current=get('/reports/'+rid).json()
    assert current==report,'Saved report changed'
    evidence=get('/reports/'+rid+'/evidence').json()['items']
    assert {x['chunk_id'] for x in evidence}==set(report['content']['cited_chunk_ids'])
    assert evidence and all(x['source_review_status']=='approved' for x in evidence)
    native=PdfReader(BytesIO((OUT/'report.pdf').read_bytes()))
    if not (OUT/'report-miniapp.pdf').exists():
        (OUT/'report-miniapp.pdf').write_bytes((OUT/'report.pdf').read_bytes())
    exports=[];times=[]
    for name in ['report.pdf','report-repeat.pdf']:
        started=time.perf_counter();r=get('/reports/'+rid+'/pdf')
        times.append({'request_seconds':time.perf_counter()-started,'render_seconds':float(r.headers['X-PDF-Render-Seconds'])})
        (OUT/name).write_bytes(r.content);exports.append(PdfReader(BytesIO(r.content)))
    texts=[''.join(p.extract_text() for p in pdf.pages) for pdf in exports]
    assert texts[0]==texts[1]==''.join(p.extract_text() for p in native.pages)
    compact=''.join(texts[0].split())
    for item in evidence:
        assert ''.join(item['text'].split()) in compact
        assert item['source_title'] in texts[0]
    assert '白苔' in texts[0] and '未检出裂纹特征' in texts[0]
    assert report['content']['model_version'] in texts[0]
    assert '待复核观察' in texts[0] and 'pdf_page' not in texts[0]
    image0=exports[0].pages[0].images[0]
    assert image0.data==exports[1].pages[0].images[0].data==native.pages[0].images[0].data
    original=Image.open(BytesIO(get('/uploads/'+report['image_id']+'/content').content)).convert('RGB')
    raw_image=next(x.get_object() for x in exports[0].pages[0]['/Resources']['/XObject'].get_object().values() if x.get_object().get('/Subtype')=='/Image')
    embedded=Image.open(BytesIO(raw_image.get_data())).convert('RGB')
    assert original.size==embedded.size
    assert ImageChops.difference(original,embedded).getbbox() is None,'PDF photo differs'
    assert get('/reports/'+rid).json()==report
    metrics=json.loads((OUT/'timings.json').read_text(encoding='utf8'))
    metrics.update(pdf_exports=times,pdf_pages=len(exports[0].pages),repeat_export_same_text_and_photo=True,report_unchanged=True,citation_count=len(evidence))
    (OUT/'timings.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'report_id':rid,'pdf_exports':times,'pages':len(exports[0].pages),'citations':len(evidence),'repeat_export':'same saved text and photo'},ensure_ascii=False))

# MySQL records, file ownership, and raw detector output must agree with the API snapshot.
import sys
sys.path.insert(0,str(ROOT/'backend'))
from app.core.database import SessionLocal
from app.models import Report,Analysis,StoredFile
with SessionLocal() as db:
    saved=db.get(Report,rid);task=db.get(Analysis,saved.analysis_id);photo=db.get(StoredFile,task.image_id)
    assert saved.user_id==task.user_id==photo.owner_id
    assert Path(photo.path).is_absolute() and Path(photo.path).is_file()
    assert 'wxfile:' not in photo.path and 'Temp' not in photo.path
    assert task.symptoms=='近一周口干、乏力，睡眠较浅'
    assert task.result['fusion_result']['detector']=='YOLO11n'
    assert task.result['fusion_result']['qwen']['status']=='valid'
    assert task.result['fusion_result']['qwen_model']=='Qwen/Qwen3-VL-2B-Instruct'
    assert task.result['fusion_result']['detections']==saved.content['yolo_detections']
    assert task.result['model_version']==saved.content['annotations']['model_version']
    print('PASS: MySQL ownership, durable photo, original symptoms, saved YOLO and real Qwen result')
