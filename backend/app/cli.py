import argparse
import getpass
from pathlib import Path
from sqlalchemy import select
from app.core.config import ROOT, settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import User
from app.repositories.graph_repository import graph_repository
from app.services.common import audit


def create_admin(args):
    password = getpass.getpass('New password (at least 10 characters): ')
    if len(password) < 10 or len(password) > 128:
        raise SystemExit('Password must contain 10-128 characters')
    if password != getpass.getpass('Confirm password: '):
        raise SystemExit('Passwords do not match')
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.username == args.username)):
            raise SystemExit('Account already exists; no changes made')
        user = User(username=args.username, nickname='知识管理员' if args.role == 'knowledge_admin' else '运维管理员', role=args.role, password_hash=hash_password(password))
        db.add(user)
        db.flush()
        audit(db, None, '通过本地命令创建管理员账号', category='system')
        db.commit()
    print('Administrator created:', args.username)


def seed_graph(args):
    import json
    data = json.loads((ROOT / 'knowledge/processed/demo-graph.json').read_text(encoding='utf-8'))
    repo = graph_repository()
    existing = repo.all()
    ids = {x['id'] for group in existing.values() for x in group}
    count = 0
    for source in data['sources']:
        if source['id'] not in ids:
            repo.put_source(source)
            count += 1
    for group in ('nodes', 'relations'):
        for item in data[group]:
            if item['id'] not in ids:
                repo.put(group, item)
                count += 1
    repo.close()
    print('Added demo records:', count, '(existing records were preserved)')


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('create-admin')
    create.add_argument('--username', required=True)
    create.add_argument('--role', required=True, choices=['knowledge_admin', 'ops_admin'])
    sub.add_parser('seed-graph')
    args = parser.parse_args()
    settings().validate_runtime()
    if args.command == 'create-admin':
        create_admin(args)
    elif args.command == 'seed-graph':
        seed_graph(args)

if __name__ == '__main__':
    main()
