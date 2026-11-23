import asyncio
import hashlib
import json
import httpx
from app.core.config import settings
from app.integrations.inference.schemas import ModelResult
from app.integrations.generation.generator import build_report
from app.integrations.retrieval.http import retrieve_http


def test_saved_boxes_are_the_only_visual_source():
    snapshot={'available':True,'detections':[{'class_name':'baitaishe','name':'白苔','score':.8}]}
    result=ModelResult(model_version='clean_v1',tongue_features=[{'name':'红舌','value':'Qwen额外观察'}],
        fusion_result={'detector':'YOLO11n','qwen':{'status':'valid','output':{
            'symptoms_summary':'口干，乏力','analysis':'用户近一周口干，乏力。舌面有裂纹且舌质红。',
            'cited_chunk_ids':[]}}})
    report=build_report(result,'近一周口干，乏力','近一周',[],snapshot)
    assert {x['name'] for x in report['tongue_features']}=={'白苔','裂纹'}
    assert report['summary']=='用户近一周口干，乏力。舌面有裂纹且舌质红。'
    assert report['pending_observations']==[]
    assert snapshot['detections']==[{'class_name':'baitaishe','name':'白苔','score':.8}]
    assert report['symptoms_summary']=='口干，乏力'


def test_unreviewed_and_low_confidence_chunks_cannot_publish(monkeypatch,tmp_path):
    s=settings()
    monkeypatch.setattr(s,'retrieval_require_reviewed',True)
    monkeypatch.setattr(s,'retrieval_base_url','http://local')
    review=tmp_path/'review.json';monkeypatch.setattr(s,'retrieval_review_file',str(review))
    valid={'chunk_id':'reviewed','text':'测试原文','source_title':'测试书名','location':{'pdf_page':67}}
    identity=hashlib.sha256(json.dumps({k:valid[k] for k in ('text','source_title','location')},ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    review.write_text(json.dumps({'reviewed':{'status':'approved','content_sha256':identity,'reviewer':'test'}}))
    evidence=[valid,{**valid,'chunk_id':'unreviewed'},{**valid,'chunk_id':'low_ocr','location':{'pdf_page':57}}]
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'evidence':evidence}))) as c:
            status,chunks=await retrieve_http(c,'测试',[])
            assert status=='available' and [x['chunk_id'] for x in chunks]==['reviewed']
        valid['text']='内容变化'
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'evidence':[valid]}))) as c:
            assert await retrieve_http(c,'测试',[])==('empty',[])
    asyncio.run(scenario())


def test_model_service_reuses_bound_detector_snapshot(monkeypatch):
    import importlib.util
    from pathlib import Path
    from fastapi.testclient import TestClient
    root=Path(__file__).resolve().parents[2]/'model-service'
    monkeypatch.syspath_prepend(str(root))
    spec=importlib.util.spec_from_file_location('model_service_snapshot_test',root/'app.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    monkeypatch.setattr(module,'multimodal',False)
    monkeypatch.setattr(module.predictor,'load',lambda:setattr(module.predictor,'version','test-v1'))
    monkeypatch.setattr(module.predictor,'analyze',lambda *args:(_ for _ in ()).throw(AssertionError('Must not detect twice')))
    monkeypatch.setenv('MODEL_API_KEY','')
    image=b'bound-upload-bytes'
    snapshot=ModelResult(model_version='test-v1',tongue_features=[],fusion_result={
        'image_sha256':hashlib.sha256(image).hexdigest(),'detections':[]}).model_dump_json()
    with TestClient(module.app) as c:
        response=c.post('/v1/infer',files={'image':('image.jpg',image,'image/jpeg')},data={'symptoms':'test','detector_result':snapshot})
        assert response.status_code==200 and response.json()['model_version']=='test-v1'
        response=c.post('/v1/infer',files={'image':('image.jpg',b'different','image/jpeg')},data={'symptoms':'test','detector_result':snapshot})
        assert response.status_code==422
