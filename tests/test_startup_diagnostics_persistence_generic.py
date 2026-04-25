from pathlib import Path

from app.ui.post_validation_logging import post_validation_diagnostic_lines, post_validation_failure_message
from app.validation.post_generation_repair import _startup_failure_signature, _startup_runtime_to_static_issues
from app.validation.runtime_smoke import _derive_startup_failure_signature, _extract_related_project_paths, _extract_startup_root_cause


def test_extract_startup_root_cause_prefers_nested_exception():
    output = """
2026-04-05 13:36:21,890  WARN [org.springframework.boot.web.servlet.context.AnnotationConfigServletWebServerApplicationContext] Exception encountered during context initialization - cancelling refresh attempt: org.springframework.beans.factory.BeanCreationException: Error creating bean with name 'dataSourceScriptDatabaseInitializer'; nested exception is org.springframework.jdbc.datasource.init.ScriptStatementFailedException: Failed to execute SQL script statement #2 of class path resource [data.sql]: INSERT INTO member_schedule (schedule_id, password) VALUES ('admin','x'); nested exception is java.sql.SQLSyntaxErrorException: Unknown column 'password' in 'field list'
Application run failed
at com.mysql.cj.jdbc.exceptions.SQLExceptionsMapping.translateException(SQLExceptionsMapping.java:122)
"""
    root = _extract_startup_root_cause(output, [{'code': 'sql_error', 'snippet': output}])
    assert 'Unknown column' in root
    assert 'SQLExceptionsMapping.translateException' not in root


def test_startup_related_paths_and_signature_use_explicit_diagnostics(tmp_path: Path):
    data = tmp_path / 'src/main/resources/data.sql'
    data.parent.mkdir(parents=True, exist_ok=True)
    data.write_text('select 1;\n', encoding='utf-8')
    output = "Failed to execute SQL script statement #2 of class path resource [data.sql]: INSERT INTO member_schedule (schedule_id, password) VALUES (\'admin\',\'x\'); nested exception is java.sql.SQLSyntaxErrorException: Unknown column \'password\' in \'field list\'"
    related = _extract_related_project_paths(tmp_path, output)
    assert 'src/main/resources/data.sql' in related
    signature = _derive_startup_failure_signature(output, [{'code': 'sql_error', 'snippet': output}], "java.sql.SQLSyntaxErrorException: Unknown column 'password' in 'field list'")
    assert signature.startswith('sql_error|')


def test_startup_runtime_to_static_issues_falls_back_to_related_paths(tmp_path: Path):
    data = tmp_path / 'src/main/resources/data.sql'
    data.parent.mkdir(parents=True, exist_ok=True)
    data.write_text('select 1;\n', encoding='utf-8')
    runtime_validation = {
        'startup': {
            'status': 'failed',
            'root_cause': "java.sql.SQLSyntaxErrorException: Unknown column 'password' in 'field list'",
            'failure_signature': 'sql_error|unknown column password',
            'related_paths': ['src/main/resources/data.sql'],
            'errors': [],
        }
    }
    issues = _startup_runtime_to_static_issues(tmp_path, runtime_validation)
    assert issues
    assert issues[0]['path'] == 'src/main/resources/data.sql'
    assert _startup_failure_signature(runtime_validation) == 'sql_error|unknown column password'


def test_post_validation_logging_includes_startup_diagnostics():
    post_validation = {
        'remaining_invalid_count': 1,
        'remaining_invalid_files': [{'path': 'src/main/resources/data.sql', 'reason': 'SQL or schema mismatch detected'}],
        'runtime_validation': {
            'compile': {'status': 'ok'},
            'startup': {
                'status': 'failed',
                'root_cause': "java.sql.SQLSyntaxErrorException: Unknown column 'password' in 'field list'",
                'failure_signature': 'sql_error|unknown column password',
                'startup_log': '.autopj_debug/startup_raw.log',
            },
            'endpoint_smoke': {'status': 'skipped'},
        },
        'startup_repair_rounds': [{
            'round': 1,
            'targets': ['src/main/resources/data.sql'],
            'changed': [],
            'skipped': [],
            'before': {'compile_status': 'ok', 'startup_status': 'failed', 'endpoint_smoke_status': 'skipped'},
            'after': {'compile_status': 'ok', 'startup_status': 'failed', 'endpoint_smoke_status': 'skipped', 'startup_root_cause': "java.sql.SQLSyntaxErrorException: Unknown column 'password' in 'field list'", 'startup_signature': 'sql_error|unknown column password', 'startup_log': '.autopj_debug/startup_raw.log', 'compile_errors': [], 'endpoint_errors': []},
            'terminal_failure': 'startup_failure_unchanged',
        }],
    }
    message = post_validation_failure_message(post_validation)
    lines = post_validation_diagnostic_lines(post_validation)
    assert 'startup_root_cause=' in message
    assert 'startup_signature=' in message
    assert 'startup_log=.autopj_debug/startup_raw.log' in message
    assert any('root_cause=' in line for line in lines)
    assert any('signature=' in line for line in lines)
    assert any('log=.autopj_debug/startup_raw.log' in line for line in lines)
