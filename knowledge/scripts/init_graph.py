"""Run from project root: python knowledge/scripts/init_graph.py"""
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'backend'))
from app.repositories.graph_repository import Neo4jRepository
repo = Neo4jRepository()
for command in (root / 'knowledge/scripts/init.cypher').read_text(encoding='utf-8').split(';'):
    if command.strip():
        repo._run(lambda tx, c=command: tx.run(c).consume(), write=True)
repo.close()
print('Neo4j constraints and indexes initialized; existing graph data preserved.')
