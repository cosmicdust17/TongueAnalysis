import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from neo4j.exceptions import Neo4jError, DriverError
from app.core.config import settings
from app.core.database import Base, engine
from app.repositories.graph_repository import graph_repository, GraphConflict
from app.api import auth, users, uploads, analyses, reports, knowledge, operations
from app.services.analysis_service import recover_interrupted
from app.tasks.runner import run_worker

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
# HTTP client request logs include code2Session query credentials.
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

@asynccontextmanager
async def lifespan(app):
    s = settings()
    s.validate_runtime()
    if s.auto_create_schema:
        Base.metadata.create_all(engine)
    stop, worker = asyncio.Event(), None
    if s.worker_enabled:
        recover_interrupted()
        worker = asyncio.create_task(run_worker(stop))
    yield
    stop.set()
    if worker:
        await worker
    if s.knowledge_retrieval_enabled:
        graph_repository().close()
    graph_repository.cache_clear()
    engine.dispose()

app = FastAPI(title='舌象智能分析系统', version='1.0.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings().cors_origins.split(',') if x.strip()], allow_credentials=False, allow_methods=['GET', 'POST', 'PATCH', 'PUT', 'DELETE'], allow_headers=['Authorization', 'Content-Type'])

@app.middleware('http')
async def request_id(request: Request, call_next):
    request.state.request_id = uuid4().hex
    response = await call_next(request)
    response.headers['X-Request-ID'] = request.state.request_id
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

@app.exception_handler(GraphConflict)
async def graph_conflict(request, error):
    return JSONResponse(status_code=409, content={'detail': str(error)})

@app.exception_handler(Neo4jError)
@app.exception_handler(DriverError)
async def graph_error(request, error):
    logging.error('Graph service error: %s', type(error).__name__)
    return JSONResponse(status_code=503, content={'detail': '图谱服务暂时不可用，请检查Neo4j连接配置'})

@app.exception_handler(SQLAlchemyError)
async def database_error(request, error):
    logging.error('Database error: %s', type(error).__name__)
    return JSONResponse(status_code=503, content={'detail': '业务数据库暂时不可用，请检查数据库初始化和连接配置'})

@app.get('/health')
def health():
    return {'status': 'ok', 'model_provider': settings().model_provider, 'graph_provider': settings().graph_provider,
            'knowledge_retrieval_enabled': settings().knowledge_retrieval_enabled}

for router in (auth.router, users.router, uploads.router, analyses.router, reports.router, knowledge.router, operations.router):
    app.include_router(router, prefix='/api/v1')
