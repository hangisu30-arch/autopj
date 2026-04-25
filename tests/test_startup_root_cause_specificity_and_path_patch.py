from pathlib import Path

from app.validation.post_generation_repair import _runtime_invalid_entries
from app.validation.runtime_smoke import _enrich_startup_failure


def test_enrich_startup_failure_skips_stack_frame_root_cause(tmp_path: Path):
    output = """
2026-04-05 12:58:28 ERROR [org.springframework.boot.SpringApplication] Application run failed
org.springframework.beans.factory.BeanCreationException: Error creating bean with name 'dataSourceScriptDatabaseInitializer'
Caused by: org.springframework.jdbc.datasource.init.ScriptStatementFailedException: Failed to execute SQL script statement #1 of class path resource [db/schema.sql]: ALTER TABLE member_account ADD COLUMN role_cd VARCHAR(20)
Caused by: java.sql.SQLSyntaxErrorException: Duplicate column name 'role_cd'
at com.mysql.cj.jdbc.exceptions.SQLExceptionsMapping.translateException(SQLExceptionsMapping.java:122) ~[mysql-connector-j-8.3.0.jar:8.3.0]
"""
    errors = [
        {'code': 'application_run_failed', 'message': 'Spring Boot startup failed', 'snippet': 'Application run failed'},
        {'code': 'bean_creation', 'message': 'Spring bean creation failed', 'snippet': 'BeanCreationException'},
        {'code': 'sql_error', 'message': 'SQL or schema mismatch detected', 'snippet': 'SQLSyntaxErrorException'},
    ]

    enriched_errors, root_cause, signature, startup_log, related_paths = _enrich_startup_failure(output, errors, tmp_path)

    assert root_cause == "java.sql.SQLSyntaxErrorException: Duplicate column name 'role_cd'"
    assert signature.startswith('sql_error|')
    assert 'src/main/resources/db/schema.sql' in related_paths
    assert startup_log == '.autopj_debug/startup_raw.log'
    assert enriched_errors[0]['path'] == 'src/main/resources/db/schema.sql'


def test_runtime_invalid_entries_avoid_generic_index_path_for_backend_startup(tmp_path: Path):
    schema_path = tmp_path / 'src/main/resources/db/schema.sql'
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text('CREATE TABLE member_account (role_cd VARCHAR(20));', encoding='utf-8')

    runtime_validation = {
        'compile': {'status': 'ok'},
        'startup': {
            'status': 'failed',
            'root_cause': "java.sql.SQLSyntaxErrorException: Duplicate column name 'role_cd'",
            'log_tail': 'Caused by: java.sql.SQLSyntaxErrorException: Duplicate column name \'role_cd\' class path resource [db/schema.sql]',
            'related_paths': ['src/main/resources/db/schema.sql'],
            'errors': [
                {
                    'code': 'application_run_failed',
                    'message': 'Spring Boot startup failed',
                    'path': 'src/main/resources/static/index.html',
                },
                {
                    'code': 'bean_creation',
                    'message': 'Spring bean creation failed',
                    'path': 'src/main/resources/static/index.html',
                },
                {
                    'code': 'sql_error',
                    'message': 'SQL or schema mismatch detected',
                    'path': 'src/main/resources/static/index.html',
                },
            ],
        },
        'endpoint_smoke': {'status': 'skipped'},
    }

    issues = _runtime_invalid_entries(tmp_path, runtime_validation)

    assert issues
    assert all(item['path'] == 'src/main/resources/db/schema.sql' for item in issues)
    assert all('index.html' not in item['path'] for item in issues)
