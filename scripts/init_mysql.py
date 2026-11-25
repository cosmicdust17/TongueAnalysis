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
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Index, MetaData, create_mock_engine, inspect
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable, CreateIndex
from app.core.database import Base, engine
import app.models


def alembic_config():
    return Config(str(ROOT / 'backend/alembic.ini'))


def baseline_metadata():
    metadata = MetaData()

    def capture(ddl, *args, **kwargs):
        if isinstance(ddl, CreateTable):
            ddl.element.to_metadata(metadata)
        elif isinstance(ddl, CreateIndex):
            index = ddl.element
            table = metadata.tables[index.table.name]
            Index(index.name, *(table.c[col.name] for col in index.columns), unique=index.unique)
        else:
            raise RuntimeError(f'Unexpected DDL in baseline: {type(ddl).__name__}')

    baseline = ScriptDirectory.from_config(alembic_config()).get_revision('0001')
    with Operations.context(MigrationContext.configure(connection=create_mock_engine('mysql://', capture))):
        baseline.module.upgrade()
    return metadata


def check_reference_sql(metadata=None):
    if metadata is None:
        metadata = baseline_metadata()
    def normalize(statement):
        statement = re.sub(r'ENGINE=.*$', '', statement, flags=re.S)
        if statement.lstrip().upper().startswith('CREATE TABLE'):
            first, *definitions, last = statement.strip().splitlines()
            columns, constraints = [], []
            for line in definitions:
                line = line.strip().rstrip(',')
                group = constraints if line.upper().startswith(('PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY', 'CONSTRAINT')) else columns
                group.append(line)
            statement = first + ','.join(columns + sorted(constraints)) + last
        return re.sub(r'\s+', '', statement.replace('`', '')).lower()
    sql = (ROOT / 'sql/01_schema.sql').read_text(encoding='utf-8')
    sql = re.sub(r'--[^\n]*', '', sql)
    supplied = {normalize(s.strip()) for s in sql.split(';') if s.strip().upper().startswith('CREATE ')}
    generated = set()
    for table in metadata.sorted_tables:
        generated.add(normalize(str(CreateTable(table).compile(dialect=mysql.dialect()))))
        generated.update(normalize(str(CreateIndex(i).compile(dialect=mysql.dialect()))) for i in table.indexes)
    if supplied != generated:
        raise RuntimeError('sql/01_schema.sql differs from revision 0001; no database changes made')


def check_schema(connection, metadata):
    differences = compare_metadata(MigrationContext.configure(connection, opts={'compare_type': True}), metadata)
    inspector = inspect(connection)
    for table in metadata.sorted_tables:
        expected = [c.name for c in table.primary_key.columns]
        if inspector.get_pk_constraint(table.name)['constrained_columns'] != expected:
            differences.append(('primary_key_mismatch', table.name))
    if differences:
        raise RuntimeError(f'Existing schema differs from the expected revision: {differences}')


def main():
    baseline = baseline_metadata()
    check_reference_sql(baseline)
    if engine.dialect.name != 'mysql':
        raise SystemExit('DATABASE_URL must point to real MySQL in F:/code/tongue-analysis/.env; SQLite is not accepted.')
    config = alembic_config()
    head = ScriptDirectory.from_config(config).get_current_head()
    stamp = None
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names()) - {'alembic_version'}
        current = MigrationContext.configure(connection).get_current_revision()
        if tables == set(baseline.tables) and current in (None, '0001'):
            check_schema(connection, baseline)
            if current is None:
                stamp = '0001'
        elif tables == set(Base.metadata.tables) and current in (None, head):
            check_schema(connection, Base.metadata)
            if current is None:
                stamp = head
        elif tables or current is not None:
            raise RuntimeError('Partial or unexpected schema or revision; no changes made')
    if stamp:
        command.stamp(config, stamp)
    command.upgrade(config, 'head')
    with engine.connect() as connection:
        check_schema(connection, Base.metadata)
    print(f'PASS: MySQL schema matches ORM at revision {head}.')


if __name__ == '__main__':
    main()
