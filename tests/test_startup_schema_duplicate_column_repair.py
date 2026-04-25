from pathlib import Path

from app.validation.project_auto_repair import _repair_startup_sql_schema_issue


def test_repair_startup_sql_schema_issue_removes_alter_when_create_table_already_has_column(tmp_path: Path):
    schema = tmp_path / 'src/main/resources/schema.sql'
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text(
        """CREATE TABLE IF NOT EXISTS member_account (
    member_id VARCHAR(64) PRIMARY KEY,
    role_cd VARCHAR(20) DEFAULT 'USER' COMMENT '권한코드'
);

ALTER TABLE member_account ADD COLUMN role_cd VARCHAR(20) DEFAULT 'USER' COMMENT '권한코드';
""",
        encoding='utf-8',
    )

    changed = _repair_startup_sql_schema_issue(schema, {'details': {}}, tmp_path)
    body = schema.read_text(encoding='utf-8').lower()

    assert changed is True
    assert 'create table if not exists member_account' in body
    assert 'role_cd varchar(20)' in body
    assert 'alter table member_account add column role_cd' not in body


def test_repair_startup_sql_schema_issue_keeps_alter_for_missing_create_table_column(tmp_path: Path):
    schema = tmp_path / 'src/main/resources/schema.sql'
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text(
        """CREATE TABLE IF NOT EXISTS member_account (
    member_id VARCHAR(64) PRIMARY KEY
);

ALTER TABLE member_account ADD COLUMN role_cd VARCHAR(20) DEFAULT 'USER' COMMENT '권한코드';
""",
        encoding='utf-8',
    )

    changed = _repair_startup_sql_schema_issue(schema, {'details': {}}, tmp_path)
    body = schema.read_text(encoding='utf-8').lower()

    assert changed is False
    assert 'alter table member_account add column role_cd' in body
