from pathlib import Path
import types
import sys

from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH
from app.io.execution_core_apply import (
    _apply_mysql_ddl,
    _write_auth_database_initializer,
    _write_schema_sql_from_schemas,
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_write_schema_sql_from_schemas_preserves_existing_schedule_table(tmp_path: Path):
    _write(
        tmp_path / 'src/main/resources/schema.sql',
        'CREATE TABLE IF NOT EXISTS schedule (schedule_id VARCHAR(64) PRIMARY KEY, title VARCHAR(255));\n',
    )
    schema_map = {
        'Login': schema_for('Login', feature_kind=FEATURE_KIND_AUTH),
    }

    path = _write_schema_sql_from_schemas(tmp_path, schema_map)
    body = path.read_text(encoding='utf-8')

    assert 'CREATE TABLE IF NOT EXISTS schedule' in body
    assert 'CREATE TABLE IF NOT EXISTS login' in body
    assert body.lower().count('create table if not exists schedule') == 1
    assert body.lower().count('create table if not exists login') == 1


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.results = []

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        low = str(sql).strip().lower()
        if low.startswith('create table'):
            parts = low.replace('`', '').split()
            name = ''
            if 'exists' in parts:
                idx = parts.index('exists') + 1
                if idx < len(parts):
                    name = parts[idx]
            elif len(parts) >= 3:
                name = parts[2]
            name = name.split('(')[0].strip().strip(';')
            if name:
                self.conn.created_tables.add(name)
        elif 'information_schema.tables' in low:
            self.results = [(name,) for name in sorted(self.conn.created_tables)]

    def fetchall(self):
        return list(self.results)

    def close(self):
        return None


class _FakeConnection:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.executed = []
        self.created_tables = set()

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        return None

    def close(self):
        return None


class _FakeConnectorModule:
    def __init__(self):
        self.connections = []

    def connect(self, **kwargs):
        conn = _FakeConnection(**kwargs)
        if self.connections and 'database' in kwargs:
            conn.created_tables = self.connections[0].created_tables
        self.connections.append(conn)
        return conn


def test_apply_mysql_ddl_uses_schema_sql_and_creates_schedule_table(tmp_path: Path, monkeypatch):
    _write(
        tmp_path / 'src/main/resources/schema.sql',
        '\n\n'.join([
            'CREATE TABLE IF NOT EXISTS schedule (schedule_id VARCHAR(64) PRIMARY KEY, title VARCHAR(255));',
            'CREATE TABLE IF NOT EXISTS login (login_id VARCHAR(64) PRIMARY KEY, password VARCHAR(255));',
        ]) + '\n',
    )

    fake_connector = _FakeConnectorModule()
    mysql_mod = types.ModuleType('mysql')
    mysql_mod.connector = fake_connector
    monkeypatch.setitem(sys.modules, 'mysql', mysql_mod)
    monkeypatch.setitem(sys.modules, 'mysql.connector', fake_connector)

    result = _apply_mysql_ddl(
        {
            'host': 'localhost',
            'port': 3306,
            'user': 'tester',
            'password': 'pw',
            'database': 'egov-auto-db',
        },
        ['CREATE TABLE IF NOT EXISTS login (login_id VARCHAR(64) PRIMARY KEY, password VARCHAR(255));'],
        project_root=tmp_path,
    )

    assert result.startswith('ok(')
    assert 'schedule' in result
    db_conn = fake_connector.connections[-1]
    executed_sql = '\n'.join(sql for sql, _params in db_conn.executed)
    assert 'CREATE TABLE IF NOT EXISTS schedule' in executed_sql
    assert 'CREATE TABLE IF NOT EXISTS login' in executed_sql


def test_login_database_initializer_bootstraps_main_schema_sql(tmp_path: Path):
    path = _write_auth_database_initializer(tmp_path, 'egovframework.test')
    body = path.read_text(encoding='utf-8')

    assert 'schema.sql' in body
    assert 'data.sql' in body
    assert 'login-schema.sql' in body
    assert 'login-data.sql' in body
