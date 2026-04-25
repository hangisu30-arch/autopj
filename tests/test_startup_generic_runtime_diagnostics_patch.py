from pathlib import Path

from app.ui.post_validation_logging import post_validation_failure_message, post_validation_diagnostic_lines
from app.validation.runtime_smoke import parse_backend_log_errors, write_runtime_report
from app.validation.project_auto_repair import _repair_startup_sql_schema_issue


def test_runtime_error_extraction_and_logging_is_generic(tmp_path: Path):
    text = """
Application run failed
Caused by: org.springframework.jdbc.datasource.init.ScriptStatementFailedException: Failed to execute SQL script statement #1 of class path resource [schema.sql]: ALTER TABLE member_account ADD COLUMN role_cd VARCHAR(20) DEFAULT 'USER';
Caused by: java.sql.SQLSyntaxErrorException: Duplicate column name 'role_cd'
    at egovframework.test.config.LoginDatabaseInitializer.lambda$0(LoginDatabaseInitializer.java:32)
"""
    errors = parse_backend_log_errors(text)
    sql = next((e for e in errors if e.get('code') == 'sql_error'), None)
    assert sql is not None
    assert sql.get('schema_path') == 'src/main/resources/schema.sql'
    assert sql.get('path') == 'src/main/java/egovframework/test/config/LoginDatabaseInitializer.java'
    assert 'duplicate column name' in (sql.get('root_cause') or '').lower()
    assert sql.get('failure_signature', '').startswith('sql_error|')

    report = {
        'status': 'failed',
        'compile': {'status': 'ok'},
        'startup': {
            'status': 'failed',
            'raw_output': text,
            'root_cause': sql.get('root_cause'),
            'failure_signature': sql.get('failure_signature'),
            'startup_log': '.autopj_debug/startup_raw.log',
            'errors': errors,
        },
        'endpoint_smoke': {'status': 'skipped'},
    }
    write_runtime_report(tmp_path, report)
    assert (tmp_path / '.autopj_debug/startup_raw.log').exists()
    assert (tmp_path / '.autopj_debug/startup_errors.json').exists()

    post_validation = {
        'remaining_invalid_count': 1,
        'remaining_invalid_files': [{'reason': 'spring boot startup validation failed'}],
        'runtime_validation': report,
    }
    message = post_validation_failure_message(post_validation)
    assert 'startup_root_cause=' in message
    assert 'startup_signature=' in message
    assert 'startup_log=.autopj_debug/startup_raw.log' in message
    lines = post_validation_diagnostic_lines(post_validation)
    assert any(line.startswith('[STARTUP] root_cause=') for line in lines)
    assert any(line.startswith('[STARTUP] signature=') for line in lines)


def test_schema_repair_removes_alter_add_for_existing_create_table_column(tmp_path: Path):
    schema = tmp_path / 'src/main/resources/schema.sql'
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text(
        'CREATE TABLE member_account (\n'
        '    member_id VARCHAR(64),\n'
        '    role_cd VARCHAR(20) DEFAULT \'USER\'\n'
        ');\n\n'
        'ALTER TABLE member_account ADD COLUMN role_cd VARCHAR(20) DEFAULT \'USER\';\n',
        encoding='utf-8',
    )
    changed = _repair_startup_sql_schema_issue(schema, {'details': {}}, tmp_path)
    body = schema.read_text(encoding='utf-8').lower()
    assert changed is True
    assert 'create table member_account' in body
    assert 'alter table member_account add column role_cd' not in body
