from io import BytesIO
import asyncio
import httpx
import pytest
from PIL import Image
from pypdf import PdfReader
from sqlalchemy import select, func
from app.core.database import SessionLocal
from app.core.config import settings, Settings
from app.core.security import issue_token, hash_password
from app.models import User, Analysis, Report, Evidence
from app.repositories.graph_repository import graph_repository
from app.services.analysis_service import process_one, recover_interrupted
from app.integrations.inference.http import HttpAdapter
from app.integrations.inference.schemas import ModelResult

API = '/api/v1'

def image_bytes():
    out = BytesIO()
    Image.new('RGB',(128,128),(200,120,125)).save(out,format='PNG')
    return out.getvalue()

def submit(client, headers, symptoms='口干，乏力，睡眠较浅'):
    upload = client.post(API+'/uploads', files={'file':('tongue.png',image_bytes(),'image/png')},headers=headers)
    assert upload.status_code == 201, upload.text
    task = client.post(API+'/analyses',json={'image_id':upload.json()['id'],'symptoms':symptoms,'duration':'近一周'},headers=headers)
    assert task.status_code == 202, task.text
    return task.json()['id'], upload.json()['id']

def complete(client, headers, symptoms='口干，乏力，睡眠较浅'):
    aid, fid = submit(client, headers, symptoms)
    assert process_one()
    task = client.get(API+'/analyses/'+aid,headers=headers).json()
    assert task['status'] == 'completed', task
    return task['report_id'], aid, fid

def test_complete_analysis_history_evidence_and_pdf(client,tokens):
    h=tokens['user']
    rid,aid,fid=complete(client,h)
    report=client.get(API+'/reports/'+rid,headers=h).json()
    assert report['is_demo'] is True
    assert '模拟' in report['content']['summary']
    assert report['content']['tongue_features'][0]['confidence'] is None
    assert report['content']['model_version']=='mock-fixture-1.0'
    history=client.get(API+'/reports?q=乏力',headers=h).json()
    assert history['total']==1 and history['items'][0]['id']==rid
    evidence=client.get(API+'/reports/'+rid+'/evidence',headers=h).json()
    assert evidence['snapshot'] and len(evidence['items'])>0
    assert all(e['citation'] and e['is_demo'] for e in evidence['items'])
    pdf=client.get(API+'/reports/'+rid+'/pdf',headers=h)
    assert pdf.status_code==200 and pdf.content.startswith(b'%PDF-')
    reader=PdfReader(BytesIO(pdf.content))
    assert len(reader.pages)>0 and '示例' in ''.join(page.extract_text() for page in reader.pages)
    assert client.get(API+'/uploads/'+fid+'/content',headers=h).headers['content-type'].startswith('image/jpeg')
    assert process_one() is False
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Report))==1

def test_report_and_files_are_private(client,tokens):
    rid,aid,fid=complete(client,tokens['user'])
    with SessionLocal() as db:
        other=User(username='other',nickname='other',role='user')
        db.add(other);db.commit()
        headers={'Authorization':'Bearer '+issue_token(other)}
    for url in [f'/reports/{rid}',f'/reports/{rid}/pdf',f'/reports/{rid}/evidence',f'/analyses/{aid}',f'/uploads/{fid}/content']:
        assert client.get(API+url,headers=headers).status_code==404
    assert client.post(API+'/analyses',json={'image_id':fid,'symptoms':'口干'},headers=headers).status_code==400
    assert client.get(API+'/reports',headers=headers).json()['total']==0
    assert client.get(API+'/reports/'+rid,headers=tokens['ops_admin']).status_code==403
    assert client.get(API+'/knowledge/entities',headers=tokens['user']).status_code==403
    assert client.get(API+'/operations/overview',headers=tokens['knowledge_admin']).status_code==403

def test_upload_and_input_validation(client,tokens,monkeypatch):
    h=tokens['user']
    assert client.post(API+'/uploads',files={'file':('bad.jpg',b'not-an-image','image/jpeg')},headers=h).status_code==400
    assert client.post(API+'/uploads?purpose=document',files={'file':('doc.txt',b'hello','text/plain')},headers=h).status_code==403
    monkeypatch.setattr(settings(),'upload_max_mb',1)
    assert client.post(API+'/uploads',files={'file':('large.jpg',b'x'*(1024*1024+1),'image/jpeg')},headers=h).status_code==413
    assert client.post(API+'/analyses',json={'image_id':'x','symptoms':'   '},headers=h).status_code==422
    assert client.get(API+'/reports').status_code==401

def test_login_logout_and_disabled_user(client,tokens):
    assert client.post(API+'/auth/logout',headers=tokens['user']).status_code==200
    assert client.get(API+'/users/me',headers=tokens['user']).status_code==401
    login=client.post(API+'/auth/dev-login',json={'role':'user'}).json()
    h={'Authorization':'Bearer '+login['access_token']}
    uid=login['user']['id']
    response=client.put(API+'/operations/users/'+uid+'/status',json={'active':False},headers=tokens['ops_admin'])
    assert response.status_code==200 and response.json()['active'] is False
    assert client.get(API+'/users/me',headers=h).status_code==401
    assert client.post(API+'/auth/dev-login',json={'role':'user'}).status_code==403

def test_password_change_revokes_sessions(client,tokens):
    with SessionLocal() as db:
        user=User(username='real-admin',role='ops_admin',password_hash=hash_password('old-password-123'))
        db.add(user);db.commit()
    login=client.post(API+'/auth/login',json={'username':'real-admin','password':'old-password-123'})
    assert login.status_code==200
    h={'Authorization':'Bearer '+login.json()['access_token']}
    assert client.post(API+'/users/me/password',json={'old_password':'bad','new_password':'new-password-123'},headers=h).status_code==400
    assert client.post(API+'/users/me/password',json={'old_password':'old-password-123','new_password':'new-password-123'},headers=h).status_code==200
    assert client.get(API+'/users/me',headers=h).status_code==401
    assert client.post(API+'/auth/login',json={'username':'real-admin','password':'new-password-123'}).status_code==200

def test_graph_publication_and_source_integrity(client,tokens):
    h=tokens['knowledge_admin']
    source=client.post(API+'/knowledge/sources',json={'title':'Test source','citation':'Test fixture, page 1','is_demo':True},headers=h).json()
    body={'name':'口干知识','kind':'症状','text':'测试快照内容','source_id':source['id'],'aliases':['口干'],'status':'pending'}
    entity=client.post(API+'/knowledge/entities',json=body,headers=h)
    assert entity.status_code==201
    eid=entity.json()['id']
    assert client.delete(API+'/knowledge/sources/'+source['id'],headers=h).status_code==409
    relbody={'source':eid,'target':'demo-tired','kind':'相关','source_id':source['id'],'status':'pending'}
    rel=client.post(API+'/knowledge/relations',json=relbody,headers=h).json()
    assert client.post(API+'/knowledge/relations/'+rel['id']+'/publish',headers=h).status_code==409
    assert client.post(API+'/knowledge/entities/'+eid+'/publish',headers=h).status_code==200
    assert client.post(API+'/knowledge/relations/'+rel['id']+'/publish',headers=h).status_code==200
    assert client.delete(API+'/knowledge/entities/'+eid,headers=h).status_code==409
    rid,_,_=complete(client,tokens['user'],'口干知识，乏力')
    snapshots=client.get(API+'/reports/'+rid+'/evidence',headers=tokens['user']).json()['items']
    assert any(e['entity_id']==eid for e in snapshots)
    before=next(e for e in snapshots if e['entity_id']==eid)
    assert before['text']=='测试快照内容'
    assert client.put(API+'/knowledge/entities/'+eid,json=body|{'text':'已修改','status':'draft'},headers=h).status_code==200
    after=client.get(API+'/reports/'+rid+'/evidence',headers=tokens['user']).json()['items']
    assert next(e for e in after if e['entity_id']==eid)['text']=='测试快照内容'
    assert client.delete(API+'/knowledge/relations/'+rel['id'],headers=h).status_code==200
    assert client.delete(API+'/knowledge/entities/'+eid,headers=h).status_code==200
    assert client.delete(API+'/knowledge/sources/'+source['id'],headers=h).status_code==200

def test_unpublished_knowledge_never_retrieved(client,tokens):
    h=tokens['knowledge_admin']
    body={'name':'自定义测试症状','kind':'症状','text':'不可提前进入报告','source_id':'demo-source-symptom','aliases':[],'status':'pending'}
    item=client.post(API+'/knowledge/entities',json=body,headers=h).json()
    rid,_,_=complete(client,tokens['user'],'自定义测试症状')
    evidence=client.get(API+'/reports/'+rid+'/evidence',headers=tokens['user']).json()['items']
    assert all(e['entity_id']!=item['id'] for e in evidence)

def test_failure_alert_and_retry(client,tokens,monkeypatch):
    import app.services.analysis_service as module
    class BrokenModel:
        async def analyze(self,*args):
            raise httpx.ReadTimeout('Model timeout')
    aid,_=submit(client,tokens['user'])
    with monkeypatch.context() as patch:
        patch.setattr(module,'model_adapter',lambda:BrokenModel())
        assert process_one()
    task=client.get(API+'/analyses/'+aid,headers=tokens['user']).json()
    assert task['status']=='failed' and not task['report_id']
    alerts=client.get(API+'/operations/alerts',headers=tokens['ops_admin']).json()['items']
    assert len(alerts)==1 and not alerts[0]['resolved']
    assert client.post(API+'/analyses/'+aid+'/retry',headers=tokens['user']).status_code==202
    assert process_one()
    assert client.get(API+'/analyses/'+aid,headers=tokens['user']).json()['status']=='completed'
    assert client.post(API+'/operations/alerts/'+alerts[0]['id']+'/resolve',headers=tokens['ops_admin']).status_code==200

def test_task_recovery_is_idempotent(client,tokens):
    aid,_=submit(client,tokens['user'])
    with SessionLocal() as db:
        db.get(Analysis,aid).status='running';db.commit()
    recover_interrupted()
    assert process_one()
    recover_interrupted()
    assert process_one() is False
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Report).where(Report.analysis_id==aid))==1

def test_ops_metrics_use_real_records_and_date_validation(client,tokens):
    complete(client,tokens['user'])
    h=tokens['ops_admin']
    result=client.get(API+'/operations/overview',headers=h).json()
    assert result['today_analyses']==1 and result['report_count']==1 and result['status']=='mock'
    assert next(s for s in result['services'] if s['key']=='model')['status']=='mock'
    assert client.get(API+'/operations/logs?date=bad',headers=h).status_code==422
    assert client.get(API+'/operations/logs?q=任务完成&category=system',headers=h).json()['total']==1

def test_dev_mode_is_gated(client,monkeypatch):
    monkeypatch.setattr(settings(),'dev_login_enabled',False)
    assert client.post(API+'/auth/dev-login',json={'role':'ops_admin'}).status_code==404
    with pytest.raises(RuntimeError):
        Settings(_env_file=None,app_env='production',dev_login_enabled=True,jwt_secret='a'*40,graph_provider='demo').validate_runtime()

@pytest.mark.parametrize('mode',['valid','bad-schema','timeout'])
def test_http_model_adapter_contract(monkeypatch,tmp_path,mode):
    image=tmp_path/'input.jpg';image.write_bytes(image_bytes())
    original=httpx.AsyncClient
    async def handler(request):
        assert request.url.path=='/v1/infer'
        assert 'multipart/form-data' in request.headers['content-type']
        if mode=='timeout':raise httpx.ReadTimeout('timeout')
        if mode=='bad-schema':return httpx.Response(200,json={'invented':'result'})
        return httpx.Response(200,json={'schema_version':'1.0','model_version':'trained-test','is_demo':False,'tongue_features':[{'name':'舌色','value':'测试标签','confidence':.8}],'fusion_result':{'query_terms':['测试标签']}})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    if mode=='valid':
        result=asyncio.run(HttpAdapter().analyze(str(image),'测试症状'))
        assert result.model_version=='trained-test' and result.is_demo is False
    else:
        with pytest.raises(Exception):asyncio.run(HttpAdapter().analyze(str(image),'测试症状'))

def test_document_source_roundtrip_and_edit(client,tokens):
    h=tokens['knowledge_admin']
    file=client.post(API+'/uploads?purpose=document',headers=h,files={'file':('fixture.txt','测试文档原文'.encode(),'text/plain')})
    assert file.status_code==201
    source=client.post(API+'/knowledge/sources',headers=h,json={'title':'原始标题','citation':'真实出处的测试样例','file_id':file.json()['id'],'is_demo':True}).json()
    assert source['file_type'].startswith('text/plain')
    changed=client.put(API+'/knowledge/sources/'+source['id'],headers=h,json={'title':'更新标题','citation':'更新出处','file_id':file.json()['id'],'is_demo':True})
    assert changed.status_code==200 and changed.json()['title']=='更新标题'
    assert client.get(API+'/uploads/'+file.json()['id']+'/content',headers=h).text=='测试文档原文'
    forbidden=client.put(API+'/knowledge/sources/'+source['id'],headers=h,json={'title':'去除示例标签','citation':'test','is_demo':False})
    assert forbidden.status_code==409

def test_graph_import_is_atomic_and_requires_publication(tmp_path):
    import importlib.util,json
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('graph_import',Path(__file__).resolve().parents[2]/'knowledge/scripts/import_graph.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    raw={'sources':[{'id':'import-src','title':'导入样例','citation':'联调资料','is_demo':True}],
         'nodes':[{'id':'import-node','name':'导入测试','kind':'症状','text':'需要审核','source_id':'missing-source'}], 'relations':[]}
    path=tmp_path/'graph.json';path.write_text(json.dumps(raw),encoding='utf-8')
    before=graph_repository().all()
    with pytest.raises(ValueError):module.import_file(path)
    assert graph_repository().all()==before
    raw['nodes'][0]['source_id']='import-src';raw['nodes'][0]['status']='published'
    path.write_text(json.dumps(raw),encoding='utf-8')
    assert module.import_file(path)['nodes']==1
    saved=next(x for x in graph_repository().all()['nodes'] if x['id']=='import-node')
    assert saved['status']=='pending' and saved['is_demo']
    with pytest.raises(ValueError):module.import_file(path)

def test_unconnected_model_service_never_returns_predictions(monkeypatch):
    monkeypatch.setenv('MODEL_WEIGHTS', 'nonexistent-test-weights.pt')
    import importlib.util,sys
    from pathlib import Path
    from fastapi.testclient import TestClient
    root=Path(__file__).resolve().parents[2]/'model-service'
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.setenv('MODEL_API_KEY','')
    spec=importlib.util.spec_from_file_location('model_service_app',root/'app.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with TestClient(module.app) as service:
        assert service.get('/health').json()['ready'] is False
        result=service.post('/v1/infer',data={'symptoms':'测试'},files={'image':('test.png',image_bytes(),'image/png')})
        assert result.status_code==503
