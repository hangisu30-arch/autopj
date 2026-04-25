from pathlib import Path

from app.validation.post_generation_repair import _sanitize_all_frontend_ui_files, _startup_runtime_to_static_issues
from app.validation.project_auto_repair import _repair_startup_sql_schema_issue


def test_startup_runtime_to_static_issues_remaps_framework_path_to_project_schema(tmp_path: Path):
    schema = tmp_path / 'src/main/resources/schema.sql'
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text('ALTER TABLE member_account ADD COLUMN role_cd VARCHAR(20);\n', encoding='utf-8')

    runtime_validation = {
        'startup': {
            'status': 'failed',
            'log_tail': 'BeanCreationException: boom\nclass path resource [schema.sql]\nDuplicate column name \'role_cd\'',
            'errors': [
                {
                    'code': 'bean_creation',
                    'message': 'Spring bean creation failed',
                    'path': 'src/main/java/org/springframework/beans/factory/support/AbstractAutowireCapableBeanFactory.java',
                    'snippet': 'Failed to execute SQL script statement #1 of class path resource [schema.sql]: ALTER TABLE member_account ADD COLUMN role_cd VARCHAR(20); nested exception is java.sql.SQLSyntaxErrorException: Duplicate column name \'role_cd\'',
                }
            ],
        }
    }

    issues = _startup_runtime_to_static_issues(tmp_path, runtime_validation)
    assert issues
    assert issues[0]['path'] == 'src/main/resources/schema.sql'
    assert issues[0]['repairable'] is True


def test_sanitize_all_frontend_ui_files_removes_metadata_from_related_views(tmp_path: Path):
    base = tmp_path / 'src/main/webapp/WEB-INF/views/memberSchedule'
    base.mkdir(parents=True, exist_ok=True)
    for name in ['memberScheduleList.jsp', 'memberScheduleDetail.jsp']:
        (base / name).write_text('<div>${memberScheduleVO.db}</div>\n<span>${memberScheduleVO.schemaName}</span>\n', encoding='utf-8')

    changed = _sanitize_all_frontend_ui_files(tmp_path, 'non-auth UI must not expose generation metadata fields such as db/schemaName/tableName/packageName')
    assert len(changed) == 2
    assert 'db' not in (base / 'memberScheduleList.jsp').read_text(encoding='utf-8').lower()
    assert 'schemaname' not in (base / 'memberScheduleDetail.jsp').read_text(encoding='utf-8').lower()


def test_repair_startup_sql_schema_issue_dedupes_duplicate_alter_add_column(tmp_path: Path):
    schema = tmp_path / 'src/main/resources/schema.sql'
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text(
        'ALTER TABLE member_account ADD COLUMN role_cd VARCHAR(20);\n\n'
        'ALTER TABLE member_account ADD COLUMN role_cd VARCHAR(20);\n',
        encoding='utf-8',
    )
    changed = _repair_startup_sql_schema_issue(schema, {'details': {}}, tmp_path)
    body = schema.read_text(encoding='utf-8')
    assert changed is True
    assert body.lower().count('alter table member_account add column role_cd') == 1


def test_repair_startup_sql_schema_issue_sanitizes_data_sql_auth_leak_for_non_auth_table(tmp_path: Path):
    schema = tmp_path / 'src/main/resources/schema.sql'
    data = tmp_path / 'src/main/resources/data.sql'
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text(
        'CREATE TABLE IF NOT EXISTS member_schedule (\n'
        '  schedule_id VARCHAR(64) PRIMARY KEY,\n'
        '  use_yn VARCHAR(1),\n'
        '  status_cd VARCHAR(20),\n'
        '  reg_dt DATETIME,\n'
        '  upd_dt DATETIME\n'
        ');\n',
        encoding='utf-8',
    )
    data.write_text(
        "INSERT INTO member_schedule (schedule_id, password, use_yn, status_cd, reg_dt, upd_dt) SELECT 'admin', 'admin1234', 'Y', 'ACTIVE', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP WHERE NOT EXISTS (SELECT 1 FROM member_schedule WHERE schedule_id = 'admin');\n",
        encoding='utf-8',
    )
    changed = _repair_startup_sql_schema_issue(data, {'details': {'schema_path': 'src/main/resources/schema.sql'}}, tmp_path)
    body = data.read_text(encoding='utf-8').lower()
    assert changed is True
    assert 'password' not in body
    assert 'admin1234' not in body
    assert 'insert into member_schedule' not in body
