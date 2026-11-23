"""Real authenticated upload -> worker -> persisted report; test split never accessed."""
import argparse, json, sys, time
from pathlib import Path
import httpx
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'backend'))
from app.core.database import SessionLocal
from app.models import Analysis

def run(a):
    out = ROOT/'research/multimodal/results/fissure-regression'/a.phase
    out.mkdir(parents=True, exist_ok=True)
    review = json.loads((ROOT/'research/results/fissure_review/manual_review/review.json').read_text(encoding='utf-8'))
    with httpx.Client(base_url=a.url+'/api/v1', trust_env=False, timeout=300) as c:
        login = c.post('/auth/dev-login', json={'role':'user'}); login.raise_for_status()
        c.headers['Authorization'] = 'Bearer '+login.json()['access_token']
        for number in a.cases:
            decision = next(d for d in review['decisions'] if d['candidate_number']==number)
            cid = decision['candidate_id']
            folder = ROOT/'research/results/fissure_review/candidates'/cid
            reference = json.loads((folder/'evidence.json').read_text(encoding='utf-8'))
            assert reference['split'] in ('train','val')
            image = folder/'original.jpg'
            record = {'case':cid, 'reference':decision, 'provenance':{
                'split':reference['split'], 'source':reference['image'],
                'used_for_review_and_clean_v2_labels':True, 'independent_test':False},
                'symptoms':a.symptoms,
                'symptoms_simulated':True}
            started = time.perf_counter()
            r = c.post('/uploads', files={'file':(cid+'.jpg',image.read_bytes(),'image/jpeg')}); r.raise_for_status()
            record['upload_seconds'] = time.perf_counter()-started
            record['upload_preprocess_seconds'] = r.json().get('preprocess_seconds')
            fid = r.json()['id']
            r = c.post('/analyses',json={'image_id':fid,'symptoms':record['symptoms'],'duration':'近一周'}); r.raise_for_status()
            aid = r.json()['id']; polls=0
            while time.perf_counter()-started < 300:
                r=c.get('/analyses/'+aid); r.raise_for_status(); task=r.json(); polls+=1
                if task['status'] in ('completed','failed'): break
                time.sleep(a.poll)
            record.update(task=task,polls=polls,poll_interval=a.poll)
            record['end_to_end_seconds']=time.perf_counter()-started
            if task['status']=='failed':
                diagnostic=ROOT/'storage/qwen-last-rejected.json'
                if diagnostic.exists(): record['rejected_generation']=json.loads(diagnostic.read_text(encoding='utf-8'))
            if task['status']=='completed':
                r=c.get('/reports/'+task['report_id']); r.raise_for_status(); record['report']=r.json()
                record['end_to_end_seconds']=time.perf_counter()-started
                r=c.get('/reports/'+task['report_id']+'/evidence'); r.raise_for_status(); record['evidence']=r.json()
                with SessionLocal() as db:
                    row=db.get(Analysis,aid)
                    record['raw_result']=row.result
                    record['completion_observation_upper_bound_seconds']= max(0,record['end_to_end_seconds']-(row.updated_at-row.created_at).total_seconds()-record['upload_seconds'])
                pdf_started=time.perf_counter()
                r=c.get('/reports/'+task['report_id']+'/pdf'); r.raise_for_status()
                record['pdf_seconds']=time.perf_counter()-pdf_started
                record['pdf_render_seconds']=r.headers.get('X-PDF-Render-Seconds')
                (out/(cid+'.pdf')).write_bytes(r.content)
            (out/(cid+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'phase':a.phase,'case':cid,'status':task['status'],'seconds':record.get('end_to_end_seconds')},ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--phase',required=True); p.add_argument('--url',default='http://127.0.0.1:8000')
    p.add_argument('--cases',nargs='+',type=int,default=[4,11,16,22,27,28]); p.add_argument('--poll',type=float,default=1.5)
    p.add_argument('--symptoms',default='近一周口干，睡眠欠佳。用户自述舌尖有细纹，是否为图像裂纹请独立观察。')
    run(p.parse_args())
