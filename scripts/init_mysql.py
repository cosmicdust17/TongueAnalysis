"""Check SQL/ORM and existing MySQL tables before upgrade or stamp; never drop data."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from alembic import command
from alembic.config import Config
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable, CreateIndex
from app.core.database import Base, engine
import app.models


def check_reference_sql():
    def normalize(statement):
        statement = re.sub(r'ENGINE=.*$', '', statement, flags=re.S)
        return re.sub(r'\s+', '', statement.replace('`', '')).lower()
    sql = (ROOT / 'sql/01_schema.sql').read_text(encoding='utf-8')
    sql = re.sub(r'--[^\n]*', '', sql)
    supplied = {normalize(s.strip()) for s in sql.split(';') if s.strip().upper().startswith('CREATE ')}
    generated = set()
    for table in Base.metadata.sorted_tables:
        generated.add(normalize(str(CreateTable(table).compile(dialect=mysql.dialect()))))
        generated.update(normalize(str(CreateIndex(i).compile(dialect=mysql.dialect()))) for i in table.indexes)
    if supplied != generated:
        raise RuntimeError('sql/01_schema.sql differs from ORM tables, columns, keys or indexes; no database changes made')


def check_schema(connection):
    differences = compare_metadata(MigrationContext.configure(connection, opts={'compare_type': True}), Base.metadata)
    inspector = inspect(connection)
    for table in Base.metadata.sorted_tables:
        expected = [c.name for c in table.primary_key.columns]
        if inspector.get_pk_constraint(table.name)['constrained_columns'] != expected:
            differences.append(('primary_key_mismatch', table.name))
    if differences:
        raise RuntimeError(f'Existing schema differs from ORM; no stamp performed: {differences}')


def main():
    check_reference_sql()
    if engine.dialect.name != 'mysql':
        raise SystemExit('DATABASE_URL must point to real MySQL in F:/code/tongue-analysis/.env; SQLite is not accepted.')
    config = Config(str(ROOT / 'backend/alembic.ini'))
    config.set_main_option('script_location', str(ROOT / 'backend/migrations'))
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names()) - {'alembic_version'}
        expected = set(Base.metadata.tables)
        if not tables:
            action = 'upgrade'
        elif tables != expected:
            raise RuntimeError(f'Partial or unexpected schema; no changes made. Missing: {expected-tables}; extra: {tables-expected}')
        else:
            check_schema(connection)
            current = MigrationContext.configure(connection).get_current_revision()
            if current not in (None, '0001'):
                raise RuntimeError('Unknown migration revision; no changes made')
            action = 'stamp' if current is None else 'upgrade'
    getattr(command, action)(config, 'head')
    with engine.connect() as connection:
        check_schema(connection)
    print(f'PASS: SQL, ORM and MySQL schema agree; alembic {action} head completed.')


if __name__ == '__main__':
    main()
