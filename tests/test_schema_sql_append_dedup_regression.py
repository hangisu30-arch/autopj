from pathlib import Path

from app.io.execution_core_apply import _append_sql_file


def test_append_sql_file_replaces_existing_same_table_definition_instead_of_duplicating(tmp_path: Path):
    resources = tmp_path / 'src/main/resources'
    resources.mkdir(parents=True, exist_ok=True)
    schema = resources / 'schema.sql'
    schema.write_text(
        'CREATE TABLE IF NOT EXISTS tb_users (id VARCHAR(64) PRIMARY KEY);\n\n'
        'CREATE TABLE IF NOT EXISTS tb_schedule (schedule_id VARCHAR(64) PRIMARY KEY);\n',
        encoding='utf-8',
    )

    _append_sql_file(tmp_path, 'schema.sql', 'CREATE TABLE IF NOT EXISTS tb_users (id VARCHAR(64) PRIMARY KEY, login_id VARCHAR(100));')

    body = schema.read_text(encoding='utf-8')
    assert body.lower().count('create table if not exists tb_users') == 1
    assert 'login_id VARCHAR(100)' in body
    assert body.lower().count('create table if not exists tb_schedule') == 1
