"""Exercise real HTTP and restart persistence; retain MySQL test records for review.

Default: isolated temporary SQLite database. --mysql: configured real MySQL.
Never creates/drops tables in MySQL; run init_mysql.py first.
"""
import argparse
import hashlib
from io import BytesIO
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from time import monotonic, sleep
from uuid import uuid4

import httpx
from PIL import Image
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mysql', action='store_true')
    parser.add_argument('--port', type=int, default=8002)
    args = parser.parse_args()
    load_dotenv(ROOT / '.env')
    load_dotenv(ROOT.parent / '.env', override=True)
    with tempfile.TemporaryDirectory(prefix='tongue-persistence-') as temp:
        env = dict(os.environ)
        env.update(APP_ENV='development', KNOWLEDGE_RETRIEVAL_ENABLED='false',
                   MODEL_PROVIDER='mock', WORKER_ENABLED='true', AUTO_CREATE_SCHEMA='false')
        if args.mysql:
            from sqlalchemy.engine import make_url
            if make_url(env.get('DATABASE_URL', '')).get_backend_name() != 'mysql':
                raise RuntimeError('--mysql requires a real MySQL DATABASE_URL; no fallback allowed')
        else:
            env.update(DATABASE_URL='sqlite:///' + (Path(temp) / 'test.db').as_posix(),
                       STORAGE_PATH=str(Path(temp) / 'files'), JWT_SECRET='isolated-test-' + uuid4().hex)
        os.environ.update(env)
        sys.path.insert(0, str(ROOT / 'backend'))
        from app.core.database import SessionLocal, engine
        from app.models import User, Analysis, StoredFile, Report
        from app.core.security import issue_token
        if not args.mysql:
            subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], cwd=ROOT / 'backend', env=env, check=True)
        # Unique ordinary users: no existing user's account or data is changed.
        with SessionLocal() as db:
            owner = User(username='persistence_' + uuid4().hex, role='user')
            other = User(username='isolation_' + uuid4().hex, role='user')
            db.add_all([owner, other])
            db.commit()
            headers = {'Authorization': 'Bearer ' + issue_token(owner)}
            other_headers = {'Authorization': 'Bearer ' + issue_token(other)}
        base = f'http://127.0.0.1:{args.port}'
        process = None
        log = open(Path(temp) / 'server.log', 'w', encoding='utf-8')
        client = httpx.Client(base_url=base, timeout=10, trust_env=False)

        def stop():
            if process and process.poll() is None:
                # Windows venv launchers have a child interpreter; stop the entire owned tree.
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                                   check=True, capture_output=True)
                else:
                    process.terminate()
                process.wait(timeout=10)

        def start():
            nonlocal process
            process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
                                        '--port', str(args.port), '--workers', '1'], cwd=ROOT / 'backend',
                                       env=env, stdout=log, stderr=log)
            end = monotonic() + 20
            while monotonic() < end:
                if process.poll() is not None:
                    raise RuntimeError('Server exited before startup')
                try:
                    if client.get('/health').status_code == 200:
                        return
                except httpx.TransportError:
                    pass
                sleep(.2)
            raise RuntimeError('Startup timed out')

        def request(method, path, **kwargs):
            response = client.request(method, '/api/v1' + path, headers=headers, **kwargs)
            response.raise_for_status()
            return response

        try:
            start()
            image = BytesIO()
            Image.new('RGB', (96, 96), (190, 130, 135)).save(image, format='PNG')
            fid = request('POST', '/uploads', files={'file': ('persistence-test.png', image.getvalue(), 'image/png')}).json()['id']
            symptoms = '持久化验证：口干、乏力'
            aid = request('POST', '/analyses', json={'image_id': fid, 'symptoms': symptoms, 'duration': '近一周'}).json()['id']
            end = monotonic() + 30
            while monotonic() < end:
                task = request('GET', '/analyses/' + aid).json()
                if task['status'] == 'completed':
                    break
                assert task['status'] != 'failed', task
                sleep(.2)
            else:
                raise RuntimeError('Analysis timed out')
            rid = task['report_id']
            report = request('GET', '/reports/' + rid).json()
            digest = hashlib.sha256(request('GET', f'/uploads/{fid}/content').content).hexdigest()
            assert report['is_demo'] and report['content']['model_version'] == 'mock-fixture-1.0'
            assert report['content']['evidence_status'] == 'disabled'
            assert '知识检索尚未启用' in report['content']['summary']
            assert request('GET', f'/reports/{rid}/evidence').json()['items'] == []
            # Stop the process completely; a new interpreter and SQL connections must reload data.
            stop()
            try:
                client.get('/health')
            except httpx.TransportError:
                pass
            else:
                raise RuntimeError('Old server is still reachable; restart was not verified')
            start()
            assert request('GET', '/reports/' + rid).json() == report
            assert request('GET', '/reports', params={'q': symptoms}).json()['total'] == 1
            assert request('GET', '/analyses/' + aid).json()['status'] == 'completed'
            assert hashlib.sha256(request('GET', f'/uploads/{fid}/content').content).hexdigest() == digest
            pdf = request('GET', f'/reports/{rid}/pdf')
            assert pdf.content.startswith(b'%PDF-') and pdf.headers['content-type'].startswith('application/pdf')
            with SessionLocal() as db:
                task, stored, saved = db.get(Analysis, aid), db.get(StoredFile, fid), db.get(Report, rid)
                assert task.symptoms == symptoms and task.duration == '近一周' and task.image_id == fid
                assert task.result['is_demo'] and task.result['model_version'] == 'mock-fixture-1.0'
                assert stored.owner_id == saved.user_id == task.user_id
                assert Path(stored.path).is_absolute() and Path(stored.path).is_file()
                assert saved.content == report['content'] and saved.analysis_id == aid
            for path in [f'/uploads/{fid}/content', f'/analyses/{aid}', f'/reports/{rid}', f'/reports/{rid}/pdf', f'/reports/{rid}/evidence']:
                assert client.get('/api/v1' + path, headers=other_headers).status_code == 404
            assert client.get('/api/v1/reports', headers=other_headers).json()['total'] == 0
            print('PASS: upload -> analysis -> mock report -> history -> PDF; restart preserves image, symptoms and report; user isolation.')
            print('Database:', 'MySQL' if args.mysql else 'isolated SQLite')
            print('Report ID:', rid)
        finally:
            stop()
            client.close()
            log.close()
            engine.dispose()


if __name__ == '__main__':
    main()
