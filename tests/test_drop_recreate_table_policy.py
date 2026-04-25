from pathlib import Path

from execution_core.builtin_crud import schema_for
from app.io.execution_core_apply import _write_schema_sql_from_schemas, _append_sql_file, _apply_mysql_ddl


def test_write_schema_sql_from_schemas_uses_drop_and_recreate(tmp_path: Path):
    schema = schema_for('Notice')
    path = _write_schema_sql_from_schemas(tmp_path, {'Notice': schema})
    body = path.read_text(encoding='utf-8')
    assert f"DROP TABLE IF EXISTS `{schema.table}`;" in body
    assert f"CREATE TABLE IF NOT EXISTS {schema.table} (" in body


def test_append_sql_file_normalizes_to_drop_and_recreate(tmp_path: Path):
    body = 'CREATE TABLE IF NOT EXISTS login (login_id VARCHAR(64) PRIMARY KEY);'
    path = _append_sql_file(tmp_path, 'schema.sql', body)
    rendered = path.read_text(encoding='utf-8')
    assert 'DROP TABLE IF EXISTS `login`;' in rendered
    assert 'CREATE TABLE IF NOT EXISTS login (login_id VARCHAR(64) PRIMARY KEY);' in rendered


def test_apply_mysql_ddl_drops_existing_tables_before_create(tmp_path: Path, monkeypatch):
    executed = []

    class FakeCursor:
        def execute(self, sql, params=None):
            executed.append((sql, params))
        def fetchall(self):
            return [('notice',)]
        def close(self):
            pass

    class FakeConn:
        def __init__(self):
            self.cur = FakeCursor()
        def cursor(self):
            return self.cur
        def commit(self):
            pass
        def close(self):
            pass

    class FakeConnector:
        def connect(self, **kwargs):
            return FakeConn()

    import sys, types
    mysql_mod = types.ModuleType('mysql')
    mysql_mod.connector = FakeConnector()
    monkeypatch.setitem(sys.modules, 'mysql', mysql_mod)
    monkeypatch.setitem(sys.modules, 'mysql.connector', mysql_mod.connector)

    resources = tmp_path / 'src/main/resources'
    resources.mkdir(parents=True)
    (resources / 'schema.sql').write_text('CREATE TABLE IF NOT EXISTS notice (id VARCHAR(64) PRIMARY KEY);', encoding='utf-8')

    result = _apply_mysql_ddl({'host':'localhost','port':3306,'user':'u','password':'p','database':'db'}, [], project_root=tmp_path)

    sqls = [sql for sql, _ in executed]
    assert any('DROP TABLE IF EXISTS `notice`' in sql for sql in sqls)
    assert any('CREATE TABLE IF NOT EXISTS notice (id VARCHAR(64) PRIMARY KEY);' in sql for sql in sqls)
    assert result.startswith('ok(')
