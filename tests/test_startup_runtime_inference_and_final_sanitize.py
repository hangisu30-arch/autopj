from pathlib import Path

from app.validation.post_generation_repair import _runtime_invalid_entries, _sanitize_all_frontend_ui_files


def test_runtime_invalid_entries_infers_project_path_from_startup_text(tmp_path: Path):
    schema = tmp_path / 'schema.sql'
    schema.write_text('alter table x add column y int;\n', encoding='utf-8')
    runtime_validation = {
        'startup': {
            'status': 'failed',
            'log_tail': 'Caused by: org.springframework.jdbc.datasource.init.ScriptStatementFailedException: Failed to execute SQL script statement #1 of class path resource [schema.sql]',
            'errors': [
                {
                    'path': 'src/main/java/org/springframework/beans/factory/support/AbstractAutowireCapableBeanFactory.java',
                    'message': 'Spring bean creation failed',
                    'snippet': 'class path resource [schema.sql]',
                    'type': 'bean_creation',
                }
            ],
        }
    }
    issues = _runtime_invalid_entries(runtime_validation, tmp_path)
    assert issues
    assert issues[0]['path'] == 'schema.sql'


def test_global_sanitize_removes_metadata_from_list_like_ui(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<td>${item.db}</td>\n<th>schemaName</th>\n<div data-name="tableName"></div>\n', encoding='utf-8')
    changed = _sanitize_all_frontend_ui_files(tmp_path, 'non-auth UI must not expose generation metadata fields such as db/schemaName/tableName/packageName')
    assert 'src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleList.jsp' in changed
    body = jsp.read_text(encoding='utf-8')
    assert 'db' not in body
    assert 'schemaName' not in body
    assert 'tableName' not in body
