from datetime import datetime
from io import BytesIO
from unittest.mock import patch
from pypdf import PdfReader
from app.core.database import SessionLocal
from app.models import User, Report
from test_workflows import complete, API
from app.services.report_presentation import compose, reading


def test_fusion_observation_wins_without_changing_boxes():
    box={'name':'白苔','class_name':'baitaishe','description':'说明'}
    content={'summary':'舌照观察：舌面可见裂纹，舌色偏红。用户自述：疲劳。教材解释：例子。','annotations':{'detections':[box]}}
    view=compose(content,'睡眠浅','近一周','test',{},datetime(2026,11,23),[])
    assert '可见裂纹' in view['analysis'] and '白苔' not in view['analysis']
    assert content['annotations']['detections']==[box]
    assert view['identity']['age']=='未填写'
    uncertain=compose({'annotations':{'detections':[]}},'口干','','u',{},datetime.now(),[])
    assert '未见可明确描述' in uncertain['analysis'] and '没有裂纹' not in uncertain['analysis']


def test_reference_preserves_conditions_and_reliable_location():
    item={'text':'口干，但欲漱水不欲咽，兼舌质青紫、脉涩者，为血瘀证。','source_title':'中医诊断学',
          'source_review_status':'approved','location':{'chapter':'问诊','printed_page':84,'pdf_page':100,'paragraph':None,'block_on_page':2}}
    view=reading(item)
    assert '只想漱口却不想咽水' in view['explanation'] and '同时出现' in view['explanation']
    assert '印刷第84页' in view['reference'] and '段落' not in view['reference'] and '文本块' not in view['reference']
    item['source_review_status']='unreviewed'
    assert '印刷' not in reading(item)['reference'] and 'PDF 第100页' in reading(item)['reference']


def test_analysis_applies_textbook_to_visible_features_without_symptom_inference():
    entries = [
        {'text': '薄白苔：苔薄白而润。'},
        {'text': '口干，但欲漱水不欲咽，兼舌质青紫、脉涩者，为血瘀证。'},
    ]
    content = {'summary': '观察舌象，舌尖有细裂纹，舌苔白润。舌苔白润。但无明显裂纹，裂纹非主要表现。'}
    view = compose(content, '偶尔口干', '近一周', 'u', {}, datetime(2026, 11, 23), entries)
    assert view['analysis'].startswith('舌尖有细裂纹，舌苔白润。\n')
    assert view['analysis'].count('舌苔白润') == 1
    assert '[1]' in view['analysis'] and '[2]' not in view['analysis']
    assert '血瘀' not in view['analysis'] and '口干' not in view['analysis']
    assert len(view['evidence']) == 2


def test_profile_symptoms_and_repeat_pdf_are_frozen(client,tokens):
    h=tokens['user'];me=client.get(API+'/users/me',headers=h).json()
    client.put(API+'/users/me',headers=h,json={'nickname':'验收用户','age':68,'gender':'女'})
    text='入睡困难，白天乏力。'
    rid,aid,_=complete(client,h,text)
    report=client.get(API+'/reports/'+rid,headers=h).json();view=report['content']['presentation']
    assert view['symptoms_text']==text and view['identity']['user_id']==me['id']
    assert view['identity']['age']==68 and view['identity']['gender']=='女'
    client.put(API+'/users/me',headers=h,json={'nickname':'验收用户','age':35,'gender':'男'})
    with patch('app.services.analysis_service.model_adapter',side_effect=AssertionError('No inference on export')):
        pdf=client.get(API+'/reports/'+rid+'/pdf',headers=h)
        textpdf=''.join(p.extract_text() for p in PdfReader(BytesIO(pdf.content)).pages)
        for forbidden in ['模型','模板','mock-fixture','待复核','联调','生成时快照','页面文本块']:
            assert forbidden not in textpdf
        assert view==client.get(API+'/reports/'+rid,headers=h).json()['content']['presentation']
    assert textpdf.count(view['symptoms_text']) == 1
    assert all(textpdf.count(label) == 1 for label in ('症状自述', '持续时间', '舌象分析'))
    assert '用户自述' not in textpdf and '教材解释' not in textpdf
    second,_,_=complete(client,h,'食欲不振，餐后腹胀。')
    other=client.get(API+'/reports/'+second,headers=h).json()['content']['presentation']
    assert view['advice_items']!=other['advice_items'] and other['identity']['age']==35
    # Legacy report keeps original symptoms and can upgrade/export exactly once.
    with SessionLocal() as db:
        item=db.get(Report,rid);c=dict(item.content)
        saved = dict(view, version=2, observation='舌面可见白苔。', self_report='您提到过口干。', interpretation='还不足以确定体质倾向。')
        saved.pop('analysis')
        c['presentation']=saved;item.content=c;db.commit()
    legacy=client.get(API+'/reports/'+rid,headers=h).json()['content']['presentation']
    assert legacy['symptoms_text']=='入睡困难，白天乏力。'
    assert legacy['analysis']=='舌面可见白苔。' and legacy['identity']==view['identity']
    assert legacy['advice_items']==view['advice_items']
    assert client.get(API+'/reports/'+rid+'/pdf',headers=h).status_code==200
