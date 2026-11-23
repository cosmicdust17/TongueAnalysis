"""Neo4j is authoritative. JSON storage is an explicit local-development option."""
import json
from functools import lru_cache
from pathlib import Path
from threading import RLock
from uuid import uuid4
from datetime import datetime, timezone
from neo4j import GraphDatabase
from app.core.config import settings

class GraphConflict(ValueError):
    pass

def stamp():
    return datetime.now(timezone.utc).isoformat()

class DemoGraphRepository:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = RLock()
    def _read(self):
        if self.path.exists():
            return json.loads(self.path.read_text(encoding='utf-8'))
        return {'nodes': [], 'relations': [], 'sources': []}
    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.path)
    def ping(self):
        with self.lock:
            self._read()
        return True
    def all(self):
        with self.lock:
            return self._read()
    def put_source(self, value):
        with self.lock:
            data = self._read()
            data['sources'] = [s for s in data['sources'] if s['id'] != value['id']] + [value]
            self._write(data)
        return value
    def delete_source(self, sid):
        with self.lock:
            data = self._read()
            if any(n['source_id'] == sid for n in data['nodes'] + data['relations']):
                raise GraphConflict('来源仍被实体或关系引用')
            if not any(s['id'] == sid for s in data['sources']):
                raise GraphConflict('来源不存在')
            data['sources'] = [s for s in data['sources'] if s['id'] != sid]
            self._write(data)
    def put(self, collection, value):
        with self.lock:
            data = self._read()
            _validate(data, collection, value)
            data[collection] = [x for x in data[collection] if x['id'] != value['id']] + [value]
            self._write(data)
        return value
    def delete(self, collection, eid):
        with self.lock:
            data = self._read()
            if not any(x['id'] == eid for x in data[collection]):
                raise GraphConflict('记录不存在')
            if collection == 'nodes' and any(r['source'] == eid or r['target'] == eid for r in data['relations']):
                raise GraphConflict('请先删除关联关系')
            data[collection] = [x for x in data[collection] if x['id'] != eid]
            self._write(data)
    def close(self):
        pass

def _validate(data, collection, value):
    source = next((s for s in data['sources'] if s['id'] == value['source_id']), None)
    if not source:
        raise GraphConflict('来源不存在，请先创建来源文档')
    value['is_demo'] = bool(source.get('is_demo'))
    if collection == 'relations':
        nodes = {n['id']: n for n in data['nodes']}
        if value['source'] not in nodes or value['target'] not in nodes:
            raise GraphConflict('关系的起点或终点不存在')
        if value['source'] == value['target']:
            raise GraphConflict('不能关联同一个实体')
        if value['status'] == 'published' and any(nodes[k]['status'] != 'published' for k in (value['source'], value['target'])):
            raise GraphConflict('关系两端实体均发布后，才能发布关系')
        value['is_demo'] |= any(nodes[k].get('is_demo', False) for k in (value['source'], value['target']))

class Neo4jRepository:
    def __init__(self):
        s = settings()
        self.driver = GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password), connection_timeout=5, max_transaction_retry_time=5)
        self.database = s.neo4j_database
    def ping(self):
        self.driver.verify_connectivity()
        return True
    def _run(self, fn, write=False):
        with self.driver.session(database=self.database) as session:
            return session.execute_write(fn) if write else session.execute_read(fn)
    def all(self):
        def read(tx):
            nodes = [dict(r['n']) for r in tx.run('MATCH (n:KnowledgeEntity) RETURN n LIMIT 10001')]
            relations = [dict(r['r']) | {'source': r['sid'], 'target': r['tid']} for r in tx.run('MATCH (a:KnowledgeEntity)-[r:RELATES_TO]->(b:KnowledgeEntity) RETURN r,a.id AS sid,b.id AS tid LIMIT 20001')]
            sources = [dict(r['s']) for r in tx.run('MATCH (s:Source) RETURN s LIMIT 10001')]
            if len(nodes) > 10000 or len(relations) > 20000 or len(sources) > 10000:
                raise GraphConflict('当前版本图谱规模超过读取上限，请调整为分页查询后继续使用')
            return {'nodes': nodes, 'relations': relations, 'sources': sources}
        return self._run(read)
    def put_source(self, value):
        self._run(lambda tx: tx.run('MERGE (s:Source {id:$id}) SET s += $props', id=value['id'], props=value).consume(), True)
        return value
    def delete_source(self, sid):
        def write(tx):
            if tx.run('MATCH (:KnowledgeEntity)-[:FROM_SOURCE]->(s:Source {id:$id}) RETURN s LIMIT 1', id=sid).single() or tx.run('MATCH ()-[r:RELATES_TO]->() WHERE r.source_id=$id RETURN r LIMIT 1', id=sid).single():
                raise GraphConflict('来源仍被实体或关系引用')
            row = tx.run('MATCH (s:Source {id:$id}) DELETE s RETURN count(*) AS n', id=sid).single()
            if not row['n']:
                raise GraphConflict('来源不存在')
        self._run(write, True)
    def put(self, collection, value):
        def write(tx):
            source = tx.run('MATCH (s:Source {id:$id}) RETURN s', id=value['source_id']).single()
            if not source:
                raise GraphConflict('来源不存在，请先创建来源文档')
            value['is_demo'] = bool(source['s'].get('is_demo', False))
            if collection == 'nodes':
                tx.run('MERGE (n:KnowledgeEntity {id:$id}) SET n += $props WITH n OPTIONAL MATCH (n)-[old:FROM_SOURCE]->() DELETE old WITH DISTINCT n MATCH (s:Source {id:$sid}) MERGE (n)-[:FROM_SOURCE]->(s)', id=value['id'], sid=value['source_id'], props=value).consume()
            else:
                ends = list(tx.run('MATCH (n:KnowledgeEntity) WHERE n.id IN $ids RETURN n', ids=[value['source'], value['target']]))
                if len(ends) != 2:
                    raise GraphConflict('关系两端必须是两个已存在的实体')
                if value['status'] == 'published' and any(r['n']['status'] != 'published' for r in ends):
                    raise GraphConflict('关系两端实体均发布后，才能发布关系')
                value['is_demo'] |= any(r['n'].get('is_demo', False) for r in ends)
                tx.run('MATCH ()-[r:RELATES_TO {id:$id}]->() DELETE r', id=value['id']).consume()
                props = {k: v for k, v in value.items() if k not in ('source', 'target')}
                tx.run('MATCH (a:KnowledgeEntity {id:$a}),(b:KnowledgeEntity {id:$b}) CREATE (a)-[r:RELATES_TO]->(b) SET r += $props', a=value['source'], b=value['target'], props=props).consume()
            return value
        return self._run(write, True)
    def delete(self, collection, eid):
        def write(tx):
            if collection == 'nodes':
                if tx.run('MATCH (n:KnowledgeEntity {id:$id})-[r:RELATES_TO]-() RETURN r LIMIT 1', id=eid).single():
                    raise GraphConflict('请先删除关联关系')
                row = tx.run('MATCH (n:KnowledgeEntity {id:$id}) DETACH DELETE n RETURN count(*) AS n', id=eid).single()
            else:
                row = tx.run('MATCH ()-[r:RELATES_TO {id:$id}]->() DELETE r RETURN count(*) AS n', id=eid).single()
            if not row['n']:
                raise GraphConflict('记录不存在')
        self._run(write, True)
    def close(self):
        self.driver.close()

@lru_cache
def graph_repository():
    s = settings()
    return DemoGraphRepository(s.graph_demo_path) if s.graph_provider == 'demo' else Neo4jRepository()
