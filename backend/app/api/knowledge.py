from uuid import uuid4
import asyncio
import hashlib
import json
import logging
from pathlib import Path
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.core.security import require_role
from app.models import User, StoredFile, Document
from app.schemas import EntityIn, RelationIn, DocumentIn
from app.repositories.graph_repository import graph_repository, GraphConflict, stamp
from app.services.common import audit

logger = logging.getLogger(__name__)

def require_knowledge():
    if not settings().knowledge_retrieval_enabled:
        raise HTTPException(503, '知识检索尚未启用')


router = APIRouter(prefix='/knowledge', tags=['知识图谱管理'], dependencies=[Depends(require_knowledge)])
admin = require_role('knowledge_admin')


@router.get('/textbook-graph')
async def textbook_graph(user: User = Depends(admin)):
    config = settings()
    graph_url = config.retrieval_graph_base_url or config.retrieval_base_url
    if not graph_url:
        raise HTTPException(503, '尚未配置教材图谱服务地址')
    # The miniapp times out after 20 seconds. Keep the graph request inside that budget.
    timeout = min(config.retrieval_timeout_seconds, 8)
    try:
        async with asyncio.timeout(timeout), httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            response = await client.get(graph_url.rstrip('/') + '/v1/graph', params={'limit': 500})
        response.raise_for_status()
        relations = response.json()['relations']
        if not isinstance(relations, list):
            raise ValueError('Expected textbook graph relations list')
    except (TimeoutError, httpx.TimeoutException):
        logger.warning('Textbook graph upstream timed out within %s seconds', timeout)
        raise HTTPException(504, '教材图谱服务响应超时，请稍后重试') from None
    except httpx.RequestError as exc:
        logger.warning('Textbook graph upstream unavailable: %s', type(exc).__name__)
        raise HTTPException(503, '无法连接教材图谱服务，请检查服务是否已启动') from None
    except (httpx.HTTPStatusError, ValueError, KeyError, TypeError) as exc:
        logger.warning('Textbook graph upstream response error: %s', type(exc).__name__)
        raise HTTPException(503, '教材图谱服务暂时不可用，请检查 Neo4j 连接后重试') from None

    # Citation verification is optional. If its file cannot be read, leave locations unverified.
    reviews = {}
    try:
        review_path = Path(config.retrieval_review_file)
        if review_path.is_file():
            reviews = json.loads(review_path.read_text(encoding='utf-8-sig'))
            if not isinstance(reviews, dict):
                raise ValueError('Expected a citation review mapping')
    except (OSError, ValueError) as exc:
        logger.warning('Textbook citation review unavailable: %s', type(exc).__name__)
        reviews = {}
    try:
        published = []
        for edge in relations:
            relation, evidence = edge['relation'], edge['evidence']
            if (relation['approved'] is not True or evidence.get('is_demo') or relation.get('is_demo')
                    or evidence.get('retrieval_eligible') is False):
                continue
            statement = edge['source']['name'] + relation['kind'] + (relation.get('object_qualifier') or '') + edge['target']['name']
            location = evidence['location']
            review = reviews.get(evidence['chunk_id'], {})
            if not isinstance(review, dict):
                review = {}
            fingerprint = hashlib.sha256(json.dumps({key: evidence[key] for key in ('text', 'source_title', 'location')},
                                                     ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
            verified = review.get('content_sha256') == fingerprint and (
                review.get('status') == 'approved' or
                (review.get('status') == 'location_verified' and relation['quote'] in review.get('quotes', [])))
            verified_location = {key: location[key] for key in ('printed_page', 'paragraph')
                                 if verified and location.get(key) is not None}
            published.append({**edge, 'relation': {**relation, 'statement': statement},
                              'evidence': {**evidence, 'verified_location': verified_location}})
        return {'relations': published, 'limit_reached': len(relations) == 500}
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        logger.warning('Invalid textbook graph data: %s', type(exc).__name__)
        raise HTTPException(503, '教材图谱服务暂时不可用，请稍后重试') from None

def find(data, collection, eid):
    item = next((n for n in data[collection] if n['id'] == eid), None)
    if not item:
        raise HTTPException(404, '知识记录不存在')
    return item

def log(db, user, action):
    audit(db, user, action)
    db.commit()

@router.get('/overview')
def overview(user: User = Depends(admin)):
    data = graph_repository().all()
    return {'entity_count': len(data['nodes']), 'relation_count': len(data['relations']), 'source_count': len(data['sources']),
            'pending_count': sum(x['status'] == 'pending' for x in data['nodes'] + data['relations']),
            'published_count': sum(x['status'] == 'published' for x in data['nodes']),
            'has_demo_data': any(x.get('is_demo') for x in data['nodes'])}

@router.get('/entities')
def entities(q: str = Query(default='', max_length=100), kind: str = '', status: str = '', user: User = Depends(admin)):
    data = graph_repository().all()
    sources = {s['id']: s for s in data['sources']}
    rows = [n | {'source_title': sources.get(n['source_id'], {}).get('title', '')} for n in data['nodes'] if (not q or q in n['name'] or q in n['text']) and (not kind or n['kind'] == kind) and (not status or n['status'] == status)]
    return {'items': sorted(rows, key=lambda n: n.get('updated_at', ''), reverse=True), 'total': len(rows)}

@router.post('/entities', status_code=201)
def create_entity(body: EntityIn, user: User = Depends(admin), db: Session = Depends(get_db)):
    item = body.model_dump() | {'id': str(uuid4()), 'updated_at': stamp()}
    graph_repository().put('nodes', item)
    log(db, user, '新增图谱实体')
    return item

@router.put('/entities/{eid}')
def update_entity(eid: str, body: EntityIn, user: User = Depends(admin), db: Session = Depends(get_db)):
    find(graph_repository().all(), 'nodes', eid)
    item = body.model_dump() | {'id': eid, 'updated_at': stamp()}
    graph_repository().put('nodes', item)
    log(db, user, '修改图谱实体（重新审核）')
    return item

@router.post('/entities/{eid}/publish')
def publish_entity(eid: str, user: User = Depends(admin), db: Session = Depends(get_db)):
    item = find(graph_repository().all(), 'nodes', eid)
    if item['status'] != 'pending':
        raise HTTPException(409, '请先提交审核后再发布')
    item.update(status='published', updated_at=stamp())
    graph_repository().put('nodes', item)
    log(db, user, '审核发布图谱实体')
    return item

@router.delete('/entities/{eid}')
def delete_entity(eid: str, user: User = Depends(admin), db: Session = Depends(get_db)):
    graph_repository().delete('nodes', eid)
    log(db, user, '删除图谱实体')
    return {'ok': True}

@router.get('/relations')
def relations(user: User = Depends(admin)):
    return {'items': graph_repository().all()['relations']}

@router.post('/relations', status_code=201)
def create_relation(body: RelationIn, user: User = Depends(admin), db: Session = Depends(get_db)):
    item = body.model_dump() | {'id': str(uuid4()), 'updated_at': stamp()}
    graph_repository().put('relations', item)
    log(db, user, '新增图谱关系')
    return item

@router.put('/relations/{rid}')
def update_relation(rid: str, body: RelationIn, user: User = Depends(admin), db: Session = Depends(get_db)):
    find(graph_repository().all(), 'relations', rid)
    item = body.model_dump() | {'id': rid, 'updated_at': stamp()}
    graph_repository().put('relations', item)
    log(db, user, '修改图谱关系（重新审核）')
    return item

@router.post('/relations/{rid}/publish')
def publish_relation(rid: str, user: User = Depends(admin), db: Session = Depends(get_db)):
    item = find(graph_repository().all(), 'relations', rid)
    if item['status'] != 'pending':
        raise HTTPException(409, '请先提交审核后再发布')
    item.update(status='published', updated_at=stamp())
    graph_repository().put('relations', item)
    log(db, user, '审核发布图谱关系')
    return item

@router.delete('/relations/{rid}')
def delete_relation(rid: str, user: User = Depends(admin), db: Session = Depends(get_db)):
    graph_repository().delete('relations', rid)
    log(db, user, '删除图谱关系')
    return {'ok': True}

@router.get('/graph')
def graph(q: str = Query(default='', max_length=100), entity_id: str = '', kind: str = '', user: User = Depends(admin)):
    data = graph_repository().all()
    nodes = data['nodes']
    if q:
        nodes = [n for n in nodes if q in n['name'] or any(q in a for a in n.get('aliases', []))]
    if entity_id:
        find(data, 'nodes', entity_id)
        ids = {entity_id}
        for r in data['relations']:
            if entity_id in (r['source'], r['target']):
                ids.update((r['source'], r['target']))
        nodes = [n for n in nodes if n['id'] in ids]
    if kind:
        nodes = [n for n in nodes if n['kind'] == kind]
    truncated = len(nodes) > 80
    nodes = nodes[:80]
    ids = {n['id'] for n in nodes}
    edges = [r for r in data['relations'] if r['source'] in ids and r['target'] in ids]
    # Sources are returned separately and rendered as provenance cards.
    return {'nodes': nodes, 'relations': edges, 'sources': data['sources'], 'truncated': truncated}

@router.get('/sources')
def sources(q: str = Query(default='', max_length=100), user: User = Depends(admin)):
    rows = graph_repository().all()['sources']
    return {'items': [s for s in rows if not q or q in s['title'] or q in s['citation']]}

@router.post('/sources', status_code=201)
def create_source(body: DocumentIn, user: User = Depends(admin), db: Session = Depends(get_db)):
    if body.file_id:
        file = db.get(StoredFile, body.file_id)
        if not file or file.purpose != 'document' or file.owner_id != user.id:
            raise HTTPException(400, '来源文档无效，请先上传本人文档')
    item = body.model_dump() | {'id': str(uuid4()), 'updated_at': stamp()}
    if body.file_id:
        item.update(file_type=file.content_type, file_name=file.original_name)
    # The provenance object is stored in Neo4j. SQL stores only the uploaded document index.
    graph_repository().put_source({k: v for k, v in item.items() if v is not None})
    if body.file_id:
        db.add(Document(id=item['id'], title=body.title, citation=body.citation, file_id=body.file_id, is_demo=body.is_demo))
    log(db, user, '新增知识来源')
    return item

@router.delete('/sources/{sid}')
def delete_source(sid: str, user: User = Depends(admin), db: Session = Depends(get_db)):
    graph_repository().delete_source(sid)
    document = db.get(Document, sid)
    if document:
        db.delete(document)
    log(db, user, '删除知识来源')
    return {'ok': True}

@router.put('/sources/{sid}')
def update_source(sid: str, body: DocumentIn, user: User = Depends(admin), db: Session = Depends(get_db)):
    existing = find(graph_repository().all(), 'sources', sid)
    if existing.get('is_demo') and not body.is_demo:
        raise HTTPException(409, '示例来源不能改为正式来源，请另建真实来源')
    item = body.model_dump() | {'id': sid, 'updated_at': stamp(), 'file_name': None, 'file_type': None}
    if body.file_id:
        file = db.get(StoredFile, body.file_id)
        if not file or file.purpose != 'document' or (file.owner_id != user.id and existing.get('file_id') != file.id):
            raise HTTPException(400, '来源文档无效')
        item.update(file_type=file.content_type, file_name=file.original_name)
    graph_repository().put_source(item)
    document = db.get(Document, sid)
    if document:
        document.title, document.citation, document.file_id, document.is_demo = body.title, body.citation, body.file_id, body.is_demo
    elif body.file_id:
        db.add(Document(id=sid, title=body.title, citation=body.citation, file_id=body.file_id, is_demo=body.is_demo))
    log(db, user, '修改知识来源')
    return item
