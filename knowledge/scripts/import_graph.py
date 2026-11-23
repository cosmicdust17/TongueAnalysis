"""Validate the complete JSON first; import in one transaction, never overwrite IDs.

All imported entities/relations become pending, even if input says published.
Run from root: python knowledge/scripts/import_graph.py path/to/graph.json
"""
import argparse
import json
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'backend'))
from app.schemas import DocumentIn, EntityIn, RelationIn
from app.repositories.graph_repository import graph_repository, DemoGraphRepository, stamp, _validate
from app.core.config import settings


def import_file(path):
    settings().validate_runtime()
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError('JSON exceeds 10MB')
    raw = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(raw, dict) or set(raw) != {'sources', 'nodes', 'relations'}:
        raise ValueError('JSON requires exactly sources, nodes, relations arrays')
    repo = graph_repository()
    existing = repo.all()
    additions = {key: [] for key in existing}
    seen = {item['id'] for group in existing.values() for item in group}
    for group, limit in [('sources', 1000), ('nodes', 1000), ('relations', 2000)]:
        if not isinstance(raw[group], list) or len(raw[group]) > limit:
            raise ValueError(f'{group} exceeds {limit} records')
        for item in raw[group]:
            eid = item.get('id')
            if not isinstance(eid, str) or not 1 <= len(eid) <= 36 or eid in seen:
                raise ValueError(f'Duplicate/existing/invalid id: {eid}')
            seen.add(eid)
            if group == 'sources':
                value = DocumentIn.model_validate({k: item[k] for k in ('title', 'citation', 'is_demo') if k in item}).model_dump(exclude_none=True)
            else:
                model = EntityIn if group == 'nodes' else RelationIn
                allowed = set(model.model_fields)
                value = model.model_validate({k: v for k, v in item.items() if k in allowed and k != 'status'} | {'status': 'pending'}).model_dump()
            additions[group].append(value | {'id': eid, 'updated_at': stamp()})
    merged = {key: existing[key] + additions[key] for key in existing}
    for group in ('nodes', 'relations'):
        for item in additions[group]:
            _validate(merged, group, item)
    if isinstance(repo, DemoGraphRepository):
        with repo.lock:
            # Compare before committing to avoid losing changes made during validation.
            if repo._read() != existing:
                raise ValueError('Graph changed during validation; retry the import')
            repo._write(merged)
    else:
        def write(tx):
            tx.run('UNWIND $rows AS row CREATE (s:Source) SET s += row', rows=additions['sources']).consume()
            tx.run('UNWIND $rows AS row CREATE (n:KnowledgeEntity) SET n += row WITH n MATCH (s:Source {id:n.source_id}) CREATE (n)-[:FROM_SOURCE]->(s)', rows=additions['nodes']).consume()
            tx.run('UNWIND $rows AS row MATCH (a:KnowledgeEntity {id:row.source}), (b:KnowledgeEntity {id:row.target}) CREATE (a)-[r:RELATES_TO]->(b) SET r += row', rows=additions['relations']).consume()
        repo._run(write, write=True)
    repo.close()
    return {k: len(v) for k, v in additions.items()}

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('file', type=Path)
    args = parser.parse_args()
    print(import_file(args.file))
