from io import BytesIO
from unittest.mock import patch
import pytest
from PIL import Image
from pypdf import PdfReader
from app.integrations.inference.schemas import ModelResult
from app.services.analysis_service import process_one
from test_workflows import API


@pytest.mark.parametrize('size,boxes', [((600,400),[[0.,0.,1.,1.],[.1,.2,.5,.7]]),((600,400),[]),((300,900),[[.2,.1,.9,.95]])])
def test_report_annotations_survive_model_switch(client,tokens,tmp_path,size,boxes):
    photo=BytesIO(); Image.new('RGB',size,'#b98f91').save(photo,format='JPEG')
    h=tokens['user']
    fid=client.post(API+'/uploads',headers=h,files={'file':('photo.jpg',photo.getvalue(),'image/jpeg')}).json()['id']
    task=client.post(API+'/analyses',headers=h,json={'image_id':fid,'symptoms':'标注验收','duration':'近一周'}).json()
    result=ModelResult(model_version='clean_v1-snapshot',tongue_features=[],fusion_result={'detector':'YOLO11n','weights_sha256':'v1',
        'detections':[{'class_id':4,'class_name':'baitaishe','score':.8,'box_xyxy_normalized':b} for b in boxes]})
    async def analyze(*args): return result
    with patch('app.services.analysis_service.model_adapter') as factory:
        factory.return_value.analyze=analyze
        assert process_one()
    rid=client.get(API+'/analyses/'+task['id'],headers=h).json()['report_id']
    snapshot=client.get(API+'/reports/'+rid,headers=h).json()['content']['annotations']
    assert snapshot['model_version']=='clean_v1-snapshot'
    assert [b['xyxy'] for b in snapshot['detections']]==boxes
    with patch('app.services.analysis_service.model_adapter',side_effect=AssertionError('Historical report must not infer')):
        assert client.get(API+'/reports/'+rid,headers=h).json()['content']['annotations']==snapshot
        pdf=client.get(API+'/reports/'+rid+'/pdf',headers=h)
    assert pdf.status_code==200
    text=''.join(p.extract_text() for p in PdfReader(BytesIO(pdf.content)).pages)
    assert ('白苔' if boxes else '本次未检出可标注的舌象特征') in text
    assert 'clean_v1-snapshot' not in text
    assert '用户 ID' in text and '待复核' not in text
    image = PdfReader(BytesIO(pdf.content)).pages[0].images[0]
    rendered = Image.open(BytesIO(image.data))
    assert rendered.mode == 'RGB' and rendered.size == size
    assert len(set(rendered.getpixel((0, 0)))) > 1
    (tmp_path/'report.pdf').write_bytes(pdf.content)
