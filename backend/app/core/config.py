from pathlib import Path
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_ROOT = ROOT.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(str(ROOT / '.env'), str(WORKSPACE_ROOT / '.env')), extra='ignore')
    app_env: str = 'production'
    database_url: str = 'mysql+pymysql://tongue_app:change_me@127.0.0.1:3306/tongue_analysis?charset=utf8mb4'
    jwt_secret: str = ''
    token_hours: int = Field(default=12, ge=1, le=168)
    dev_login_enabled: bool = False
    auto_create_schema: bool = False
    worker_enabled: bool = True
    graph_provider: str = 'neo4j'
    knowledge_retrieval_enabled: bool = True
    neo4j_uri: str = 'bolt://127.0.0.1:7687'
    neo4j_user: str = 'neo4j'
    neo4j_password: str = ''
    neo4j_database: str = 'neo4j'
    graph_demo_path: str = str(ROOT / 'storage/demo-graph.json')
    model_provider: str = 'mock'
    multimodal_enabled: bool = False
    retrieval_base_url: str = ''
    retrieval_graph_base_url: str = ''
    retrieval_timeout_seconds: int = Field(default=3, ge=1, le=30)
    retrieval_candidate_count: int = Field(default=12, ge=5, le=200)
    retrieval_require_reviewed: bool = False
    retrieval_review_file: str = str(ROOT / 'research/retrieval/data/source-review.json')
    model_base_url: str = 'http://127.0.0.1:8001'
    model_api_key: str = ''
    model_timeout_seconds: int = Field(default=120, ge=1, le=600)
    wechat_appid: str = ''
    wechat_secret: str = ''
    storage_path: str = str(ROOT / 'storage')
    upload_max_mb: int = Field(default=10, ge=1, le=30)
    cors_origins: str = 'http://localhost:5173,http://127.0.0.1:5173'

    def validate_runtime(self):
        if len(self.jwt_secret) < 32 or self.jwt_secret.startswith('REPLACE_'):
            raise RuntimeError('JWT_SECRET must contain at least 32 characters')
        if self.app_env != 'development' and (self.dev_login_enabled or (self.knowledge_retrieval_enabled and self.graph_provider == 'demo') or self.auto_create_schema):
            raise RuntimeError('Development login / demo graph / auto-create require APP_ENV=development')
        if self.model_provider not in ('mock', 'http') or self.graph_provider not in ('demo', 'neo4j'):
            raise RuntimeError('Unsupported model or graph provider')
        if (self.knowledge_retrieval_enabled and not (self.multimodal_enabled and self.model_provider == 'http')
                and self.graph_provider == 'neo4j' and not self.neo4j_password):
            raise RuntimeError('NEO4J_PASSWORD is required')

@lru_cache
def settings():
    return Settings()
