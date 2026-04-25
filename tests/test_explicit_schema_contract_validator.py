from pathlib import Path

from app.ui.state import ProjectConfig
from app.validation.generated_project_validator import _scan_explicit_schema_contract
from app.validation.project_auto_repair import auto_repair_generated_project


REQ = '''
테이블명:
- tb_member

테이블 설명(comment):
- 회원 정보 관리 테이블

컬럼은 최소 아래와 같이 생성하라.
1. member_id
- 타입: VARCHAR(50)
- 제약: PRIMARY KEY
- comment: 회원 고유 ID

2. login_id
- 타입: VARCHAR(100)
- 제약: NOT NULL, UNIQUE
- comment: 로그인 아이디
'''


def test_explicit_schema_contract_scan_detects_comment_and_type_drift(tmp_path: Path):
    resources = tmp_path / 'src/main/resources'
    resources.mkdir(parents=True)
    (resources / 'schema.sql').write_text(
        """
        CREATE TABLE IF NOT EXISTS tb_member (
            member_id VARCHAR(64) NOT NULL PRIMARY KEY COMMENT '아이디',
            login_id VARCHAR(255) NOT NULL COMMENT '아이디'
        ) COMMENT='틀린 코멘트';
        """,
        encoding='utf-8',
    )
    cfg = ProjectConfig(extra_requirements=REQ).normalize()
    issues = _scan_explicit_schema_contract(tmp_path, cfg)
    assert issues
    assert any(item['type'] == 'explicit_schema_contract_mismatch' for item in issues)


def test_explicit_schema_contract_auto_repair_rewrites_schema_sql(tmp_path: Path):
    resources = tmp_path / 'src/main/resources'
    resources.mkdir(parents=True)
    schema_path = resources / 'schema.sql'
    schema_path.write_text(
        """
        CREATE TABLE IF NOT EXISTS tb_member (
            member_id VARCHAR(64) NOT NULL PRIMARY KEY COMMENT '아이디',
            login_id VARCHAR(255) NOT NULL COMMENT '아이디'
        ) COMMENT='틀린 코멘트';
        """,
        encoding='utf-8',
    )
    cfg = ProjectConfig(extra_requirements=REQ).normalize()
    issues = _scan_explicit_schema_contract(tmp_path, cfg)
    report = {'static_issues': issues}
    repaired = auto_repair_generated_project(tmp_path, report)
    assert repaired['changed_count'] >= 1
    text = schema_path.read_text(encoding='utf-8')
    assert "member_id VARCHAR(50) NOT NULL PRIMARY KEY COMMENT '회원 고유 ID'" in text
    assert "login_id VARCHAR(100) UNIQUE NOT NULL COMMENT '로그인 아이디'" in text
    assert "COMMENT='회원 정보 관리 테이블'" in text
