from pathlib import Path

from app.ui.post_validation_logging import post_validation_failure_message
from app.validation.post_generation_repair import _startup_failure_signature
from app.validation.runtime_smoke import _enrich_startup_failure


def test_enrich_startup_failure_prefers_specific_caused_by(tmp_path: Path):
    output = """
2026-04-05 12:19:25,273 ERROR [org.springframework.boot.SpringApplication] Application run failed
org.springframework.beans.factory.BeanCreationException: Error creating bean with name 'dataSourceScriptDatabaseInitializer'
Caused by: org.springframework.jdbc.datasource.init.ScriptStatementFailedException: Failed to execute SQL script statement #1 of class path resource [schema.sql]: ALTER TABLE member_account ADD COLUMN role_cd VARCHAR(20)
Caused by: java.sql.SQLSyntaxErrorException: Duplicate column name 'role_cd'
"""
    errors, root_cause, signature, startup_log, related_paths = _enrich_startup_failure(output, [], tmp_path)

    assert "Duplicate column name 'role_cd'" in root_cause
    assert signature.startswith('startup_failure|')
    assert startup_log == '.autopj_debug/startup_raw.log'
    assert 'src/main/resources/schema.sql' in related_paths
    assert (tmp_path / '.autopj_debug' / 'startup_raw.log').exists()
    assert errors[0]['message'] == root_cause


def test_startup_failure_signature_prefers_explicit_signature():
    runtime_validation = {
        'startup': {
            'status': 'failed',
            'failure_signature': 'sql_error|duplicate column role_cd',
            'root_cause': 'java.sql.SQLSyntaxErrorException: Duplicate column name role_cd',
            'errors': [{'code': 'application_run_failed', 'message': 'Application run failed'}],
        }
    }
    assert _startup_failure_signature(runtime_validation) == 'sql_error|duplicate column role_cd'


def test_post_validation_failure_message_includes_startup_diagnostics():
    post_validation = {
        'remaining_invalid_count': 1,
        'remaining_invalid_files': [{'path': '', 'reason': 'spring boot startup validation failed'}],
        'runtime_validation': {
            'compile': {'status': 'ok'},
            'startup': {
                'status': 'failed',
                'root_cause': "java.sql.SQLSyntaxErrorException: Duplicate column name 'role_cd'",
                'failure_signature': 'sql_error|duplicate column role_cd',
                'startup_log': '.autopj_debug/startup_raw.log',
            },
            'endpoint_smoke': {'status': 'skipped'},
        },
    }
    msg = post_validation_failure_message(post_validation)
    assert "startup_root_cause=java.sql.SQLSyntaxErrorException: Duplicate column name 'role_cd'" in msg
    assert 'startup_signature=sql_error|duplicate column role_cd' in msg
    assert 'startup_log=.autopj_debug/startup_raw.log' in msg
