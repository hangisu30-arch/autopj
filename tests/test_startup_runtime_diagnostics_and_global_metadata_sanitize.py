from pathlib import Path

from app.validation.runtime_smoke import parse_backend_log_errors
from app.validation.post_generation_repair import _sanitize_all_frontend_metadata
from app.validation.project_auto_repair import _repair_startup_sql_schema_issue


def test_parse_backend_log_errors_extracts_schema_path_and_initializer_source():
    text = """
Application run failed
Caused by: org.springframework.jdbc.datasource.init.ScriptStatementFailedException: Failed to execute SQL script statement #1 of class path resource [schema.sql]: ALTER TABLE member_account ADD COLUMN role_cd VARCHAR(20);
Caused by: java.sql.SQLSyntaxErrorException: Duplicate column name 'role_cd'
    at egovframework.test.config.LoginDatabaseInitializer.lambda$0(LoginDatabaseInitializer.java:32)
"""
    errors = parse_backend_log_errors(text)
    sql = next((e for e in errors if e.get('code') == 'sql_error'), None)
    assert sql is not None
    assert sql.get('schema_path') == 'src/main/resources/schema.sql'
    assert sql.get('path') in {'src/main/java/egovframework/test/config/LoginDatabaseInitializer.java', 'src/main/resources/schema.sql'}


def test_global_metadata_sanitize_cleans_all_frontend_files(tmp_path: Path):
    ui = tmp_path / 'src/main/webapp/WEB-INF/views/memberSchedule'
    ui.mkdir(parents=True)
    for name in ('memberScheduleList.jsp', 'memberScheduleForm.jsp'):
        (ui / name).write_text('<div>${item.db}</div>\n<th>schemaName</th>', encoding='utf-8')
    changed = _sanitize_all_frontend_metadata(tmp_path)
    assert len(changed) == 2
    assert 'db' not in (ui / 'memberScheduleList.jsp').read_text(encoding='utf-8')
    assert 'schemaName' not in (ui / 'memberScheduleForm.jsp').read_text(encoding='utf-8')


def test_repair_startup_sql_schema_issue_rewrites_initializer_java(tmp_path: Path):
    target = tmp_path / 'src/main/java/egovframework/test/config/LoginDatabaseInitializer.java'
    target.parent.mkdir(parents=True)
    target.write_text('package egovframework.test.config;\npublic class LoginDatabaseInitializer {}', encoding='utf-8')
    ok = _repair_startup_sql_schema_issue(target, {'details': {}}, tmp_path)
    body = target.read_text(encoding='utf-8')
    assert ok is True
    assert 'setContinueOnError(true);' in body
    assert 'class LoginDatabaseInitializer' in body
