import json,time
from pathlib import Path
import httpx
from dotenv import dotenv_values
root=Path(__file__).resolve().parents[2]
config={**dotenv_values(root/'.env'),**dotenv_values(root.parent/'.env')}
key=config.get('MODEL_API_KEY') or ''
started=time.perf_counter()
with httpx.Client(trust_env=False,timeout=3) as c:
    while time.perf_counter()-started<180:
        try:
            m=c.get('http://127.0.0.1:8002/health',headers={'Authorization':'Bearer '+key} if key else {}).json()
            b=c.get('http://127.0.0.1:8011/health').json()
            print(json.dumps({'model':m,'retrieval':b},ensure_ascii=False),flush=True)
            c.get('http://127.0.0.1:8000/health').raise_for_status()
            if m.get('ready') and b.get('status')=='ok': break
        except (httpx.HTTPError,ValueError) as exc:
            print(type(exc).__name__, flush=True)
        time.sleep(1)
    else: raise RuntimeError('Services not ready')
record={'model':m,'retrieval':b,'wait_for_ready_seconds':time.perf_counter()-started}
(root/'research/multimodal/results/fissure-regression/services.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(record,ensure_ascii=False))
