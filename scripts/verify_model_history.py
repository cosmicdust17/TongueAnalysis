"""After selecting clean_v2 and restarting the model, check clean_v1 report snapshots."""
from pathlib import Path
import json
import sys
import httpx
from pypdf import PdfReader
from io import BytesIO

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.core.config import settings
s=settings()
headers={'Authorization':'Bearer '+s.model_api_key} if s.model_api_key else {}
with httpx.Client(timeout=30,trust_env=False) as c:
    health=c.get(s.model_base_url+'/health',headers=headers);health.raise_for_status()
    assert health.json()['ready'] and health.json()['model_version'].startswith('clean-v2')
    r=c.post('http://127.0.0.1:8000/api/v1/auth/dev-login',json={'role':'user'});r.raise_for_status()
    h={'Authorization':'Bearer '+r.json()['access_token']}
    for record in json.loads((ROOT/'output/pdf/annotation-check/reports.json').read_text(encoding='utf-8')):
        url='http://127.0.0.1:8000/api/v1/reports/'+record['report_id']
        r=c.get(url,headers=h);r.raise_for_status()
        assert r.json()['content']['annotations']==record['annotations']
        pdf=c.get(url+'/pdf',headers=h);pdf.raise_for_status()
        text=''.join(p.extract_text() for p in PdfReader(BytesIO(pdf.content)).pages)
        assert record['annotations']['model_version'] in text and 'clean-v2' not in text
        (ROOT/'output/pdf/annotation-check'/('history-'+record['case']+'.pdf')).write_bytes(pdf.content)
print('PASS: live clean_v2; all three saved clean_v1 snapshots and PDF model versions unchanged.')
