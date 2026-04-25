from pathlib import Path

from app.io.execution_core_apply import _resolve_mysql_apply_inputs


def test_resolve_mysql_apply_inputs_prefers_schema_sql_when_present(tmp_path: Path):
    schema = tmp_path / 'src/main/resources/schema.sql'
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text(
        'CREATE TABLE IF NOT EXISTS schedule (schedule_id VARCHAR(64) PRIMARY KEY);\n\n'
        'CREATE TABLE IF NOT EXISTS login (login_id VARCHAR(64) PRIMARY KEY);\n',
        encoding='utf-8',
    )

    statements, tables, source = _resolve_mysql_apply_inputs(
        tmp_path,
        ['CREATE TABLE IF NOT EXISTS login (login_id VARCHAR(64) PRIMARY KEY);'],
        expected_tables=['login'],
    )

    assert source == 'schema.sql'
    assert len(statements) == 2
    assert tables == ['schedule', 'login']


def test_resolve_mysql_apply_inputs_falls_back_to_ddls_without_schema_sql(tmp_path: Path):
    statements, tables, source = _resolve_mysql_apply_inputs(
        tmp_path,
        [
            'CREATE TABLE IF NOT EXISTS schedule (schedule_id VARCHAR(64) PRIMARY KEY);',
            'CREATE TABLE IF NOT EXISTS login (login_id VARCHAR(64) PRIMARY KEY);',
        ],
        expected_tables=['schedule', 'login'],
    )

    assert source == 'ddls'
    assert len(statements) == 2
    assert tables == ['schedule', 'login']
