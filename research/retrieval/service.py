import hmac
import os
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from .core import LocalIndex, Models, retrieve


class RetrieveRequest(BaseModel):
    symptoms: str = Field(default='', max_length=4000)
    tongue_features: str = Field(default='', max_length=2000)
    top_k: int = Field(default=5, ge=1, le=50)
    candidate_count: int = Field(default=40, ge=1, le=200)

    @model_validator(mode='after')
    def validate_query(self):
        if not self.symptoms.strip() and not self.tongue_features.strip():
            raise ValueError('Provide symptoms or tongue_features')
        if self.top_k > self.candidate_count:
            raise ValueError('top_k must not exceed candidate_count')
        return self


def create_app(index=None, models=None, store=None, *, graph_only=False):
    injected = index is not None
    owns_store = store is None

    @asynccontextmanager
    async def lifespan(app):
        nonlocal index, models, store
        if graph_only:
            if store is None:
                from .neo import NeoStore
                store = NeoStore()
        elif not injected:
            models = Models()
            models.load_reranker()
            backend = os.getenv('RETRIEVAL_BACKEND', 'neo4j')
            if backend == 'local':
                index = LocalIndex(os.environ['RETRIEVAL_INDEX_PATH'], models)
            elif backend == 'neo4j':
                from .neo import NeoIndex, NeoStore
                store = NeoStore()
                index = NeoIndex(store, os.environ['RETRIEVAL_INDEX_ID'], models)
            else:
                raise ValueError('Unsupported RETRIEVAL_BACKEND')
        yield
        if store and owns_store:
            store.close()

    app = FastAPI(title='Local textbook retrieval', lifespan=lifespan)

    def admin(x_admin_token: str = Header(default='')):
        expected = os.getenv('RETRIEVAL_ADMIN_TOKEN', '')
        if not expected or not hmac.compare_digest(x_admin_token, expected):
            raise HTTPException(401, 'Administrator token required')

    def graph_store():
        if store is None:
            raise HTTPException(503, 'Neo4j graph unavailable in this backend')
        return store

    @app.get('/health')
    def health():
        if graph_only:
            return {'status': 'ok', 'mode': 'graph-only'}
        return {'status': 'ok', 'index_id': index.manifest['index_id']}

    @app.post('/v1/retrieve')
    def search(body: RetrieveRequest):
        if graph_only:
            raise HTTPException(503, 'Vector retrieval is disabled in graph-only mode')
        return retrieve(index, models, body.symptoms, body.tongue_features, body.candidate_count, body.top_k)

    @app.get('/v1/graph')
    def graph(chunk_id: str | None = None, limit: int = Query(100, ge=1, le=500)):
        return {'relations': graph_store().graph(chunk_id, limit)}

    @app.get('/v1/admin/graph', dependencies=[Depends(admin)])
    def admin_graph(chunk_id: str | None = None, limit: int = Query(100, ge=1, le=500), include_test: bool = False):
        relations = graph_store().graph(chunk_id, limit, include_test=include_test)
        nodes = {n['entity_id']: n for r in relations for n in [r['source'], r['target']]}
        return {'nodes': list(nodes.values()), 'edges': relations}

    @app.get('/v1/admin/chunks/{chunk_id}', dependencies=[Depends(admin)])
    def source(chunk_id: str):
        import json
        result = graph_store().run('MATCH (c:RetrievalChunk {chunk_id:$id}) RETURN c.payload AS payload', id=chunk_id)
        if not result:
            raise HTTPException(404, 'Chunk not found')
        return json.loads(result[0]['payload'])

    @app.get('/v1/admin/candidates', dependencies=[Depends(admin)])
    def candidates():
        from .io_utils import rows
        path = os.getenv('RETRIEVAL_REVIEW_FILE')
        if not path:
            raise HTTPException(503, 'Review file not configured')
        return {'items': rows(path)}

    return app


app = create_app()
