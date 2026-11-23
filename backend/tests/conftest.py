import os
import sys
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# This suite deliberately exercises local adapters, never an external user database.
RUN_ROOT = Path(tempfile.mkdtemp(prefix='tongue-tests-'))
os.environ.update(APP_ENV='development', DATABASE_URL='sqlite:///' + str(RUN_ROOT/'test.db'),
    JWT_SECRET='test-only-secret-' + 'a'*40, DEV_LOGIN_ENABLED='true', AUTO_CREATE_SCHEMA='false',
    WORKER_ENABLED='false', KNOWLEDGE_RETRIEVAL_ENABLED='true', GRAPH_PROVIDER='demo', GRAPH_DEMO_PATH=str(RUN_ROOT/'graph.json'),
    STORAGE_PATH=str(RUN_ROOT/'files'), MODEL_PROVIDER='mock', WECHAT_APPID='', WECHAT_SECRET='', RETRIEVAL_REQUIRE_REVIEWED='false', MULTIMODAL_ENABLED='false')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app
from app.core.database import Base, engine, SessionLocal
from app.core.config import settings
from app.repositories.graph_repository import graph_repository
from app.cli import seed_graph

@pytest.fixture(autouse=True)
def reset_state():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    Path(settings().graph_demo_path).unlink(missing_ok=True)
    graph_repository.cache_clear()
    from app.api.auth import _attempts
    _attempts.clear()
    seed_graph(None)
    yield

@pytest.fixture
def client():
    with TestClient(app) as instance:
        yield instance

@pytest.fixture
def tokens(client):
    result = {}
    for role in ['user', 'knowledge_admin', 'ops_admin']:
        response = client.post('/api/v1/auth/dev-login', json={'role':role})
        assert response.status_code == 200, response.text
        result[role] = {'Authorization':'Bearer ' + response.json()['access_token']}
    return result
