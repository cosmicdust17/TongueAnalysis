"""Create first-run local configuration. Never overwrite existing configuration."""
import argparse
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--local-demo', action='store_true', help='Use SQLite and the explicitly labeled JSON graph for local evaluation')
args = parser.parse_args()
if (root / '.env').exists():
    raise SystemExit('.env already exists; edit it manually. No configuration was overwritten.')
mysql_password, root_password, graph_password = [secrets.token_hex(16) for _ in range(3)]
text = (root / '.env.example').read_text(encoding='utf-8')
text = text.replace('REPLACE_WITH_AT_LEAST_32_RANDOM_CHARACTERS', secrets.token_hex(32))
text = text.replace('REPLACE_ROOT_PASSWORD', root_password)
# The three different passwords remain distinct.
text = text.replace('tongue_app:REPLACE_PASSWORD@', 'tongue_app:' + mysql_password + '@')
text = text.replace('NEO4J_PASSWORD=REPLACE_PASSWORD', 'NEO4J_PASSWORD=' + graph_password)
text = text.replace('MYSQL_PASSWORD=REPLACE_PASSWORD', 'MYSQL_PASSWORD=' + mysql_password)
if args.local_demo:
    db_path = (root / 'storage/local-demo.db').as_posix()
    text = text.replace(next(line for line in text.splitlines() if line.startswith('DATABASE_URL=')), 'DATABASE_URL=sqlite:///' + db_path)
    text = text.replace('GRAPH_PROVIDER=neo4j', 'GRAPH_PROVIDER=demo')
(root / '.env').write_text(text, encoding='utf-8')
try:
    (root / '.env').chmod(0o600)
except OSError:
    pass
mini_env = root / 'miniapp/.env'
if not mini_env.exists():
    mini_env.write_text((root / 'miniapp/.env.example').read_text(encoding='utf-8'), encoding='utf-8')
print('Created local configuration. Existing source files were preserved.')
print('Mode:', 'SQLite + JSON graph (local demo)' if args.local_demo else 'MySQL + Neo4j')
