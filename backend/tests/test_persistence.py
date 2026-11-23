from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfReader
from sqlalchemy import select, func
from app.core.config import settings, Settings
from app.core.database import SessionLocal, engine
from app.models import Analysis, StoredFile, Evidence
from test_workflows import complete, API


def test_retrieval_disabled_persists_without_graph(client, tokens, monkeypatch):
    monkeypatch.setattr(settings(), 'knowledge_retrieval_enabled', False)
    monkeypatch.setattr(settings(), 'graph_provider', 'neo4j')
    monkeypatch.setattr(settings(), 'neo4j_password', '')
    settings().validate_runtime()
    with patch('app.integrations.retrieval.retriever.graph_repository', side_effect=AssertionError('Graph must not be contacted')):
        rid, aid, fid = complete(client, tokens['user'])
    engine.dispose()
    with SessionLocal() as db:
        task, image = db.get(Analysis, aid), db.get(StoredFile, fid)
        assert task.symptoms == '口干，乏力，睡眠较浅' and task.duration == '近一周'
        assert task.image_id == fid and task.result['model_version'] == 'mock-fixture-1.0'
        assert Path(image.path).is_absolute() and Path(image.path).is_file()
        assert image.owner_id == task.user_id
        assert db.scalar(select(func.count()).select_from(Evidence)) == 0
    report = client.get(API + '/reports/' + rid, headers=tokens['user']).json()
    assert report['content']['evidence_status'] == 'disabled'
    assert '知识检索尚未启用' in report['content']['summary']
    assert report['content']['evidence_count'] == 0 and report['is_demo']
    pdf = client.get(API + '/reports/' + rid + '/pdf', headers=tokens['user'])
    assert '暂缺可直接对应的教材依据' in ''.join(p.extract_text() for p in PdfReader(BytesIO(pdf.content)).pages)
    assert client.get(API + '/knowledge/overview', headers=tokens['knowledge_admin']).status_code == 503
    with patch('app.api.operations.graph_repository', side_effect=AssertionError('Graph must not be contacted')):
        assert client.get(API + '/operations/overview', headers=tokens['ops_admin']).status_code == 200


def test_supplied_sql_matches_orm():
    import importlib.util
    path = Path(__file__).resolve().parents[2] / 'scripts/init_mysql.py'
    spec = importlib.util.spec_from_file_location('init_mysql', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.check_reference_sql()
