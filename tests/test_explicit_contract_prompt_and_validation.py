from pathlib import Path
from types import SimpleNamespace

from app.engine.analysis.schema_parser import SchemaParser
from app.ui.analysis_bridge import explicit_requirement_contract_to_prompt_text
from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import auto_repair_generated_project


REQ = '''
테이블명: TB_MEMBER
테이블 설명(comment): 회원 정보 관리 테이블
컬럼정의:
- member_id
  - type: varchar(40)
  - comment: 회원 고유 ID
  - constraint: primary key
- login_id
  - type: varchar(100)
  - comment: 로그인 아이디
  - constraint: unique not null
- member_name
  - type: varchar(100)
  - comment: 회원명
- reg_dt
  - type: datetime
  - comment: 등록 일시
'''


def test_schema_parser_uses_execution_core_explicit_contract_metadata():
    parser = SchemaParser()
    tables = parser.infer_from_requirements(REQ, ['member'])
    assert len(tables) == 1
    table = tables[0]
    assert table.table_name == 'tb_member'
    assert [field.column for field in table.fields] == ['member_id', 'login_id', 'member_name', 'reg_dt']
    assert table.primary_key is not None
    assert table.primary_key.column == 'member_id'
    field_map = {field.column: field for field in table.fields}
    assert field_map['login_id'].comment == '로그인 아이디'
    assert field_map['reg_dt'].db_type == 'DATETIME'


def test_explicit_requirement_contract_prompt_text_includes_authoritative_comments():
    prompt = explicit_requirement_contract_to_prompt_text(REQ)
    assert '[EXPLICIT SCHEMA CONTRACT - HIGHEST PRIORITY]' in prompt
    assert 'table=tb_member' in prompt
    assert 'table_comment=회원 정보 관리 테이블' in prompt
    assert 'column=login_id' in prompt
    assert 'comment=로그인 아이디' in prompt
    assert 'db_type=VARCHAR(100)' in prompt


def test_validator_and_auto_repair_enforce_explicit_schema_contract(tmp_path: Path):
    project_root = tmp_path / 'project'
    resources = project_root / 'src/main/resources'
    resources.mkdir(parents=True, exist_ok=True)
    (resources / 'schema.sql').write_text(
        """
CREATE TABLE TB_MEMBER (
    member_id VARCHAR(40) PRIMARY KEY COMMENT '회원 고유 ID',
    login_id VARCHAR(100) COMMENT '아이디'
);
""".strip() + "\n",
        encoding='utf-8',
    )

    cfg = SimpleNamespace(
        extra_requirements=REQ,
        frontend_key='jsp',
        database_key='mysql',
        database_type='mysql',
        effective_extra_requirements=lambda: REQ,
    )

    report = validate_generated_project(project_root, cfg, include_runtime=False)
    assert any(issue.get('type') == 'explicit_schema_contract_mismatch' for issue in report.get('static_issues') or [])

    repair = auto_repair_generated_project(project_root, report)
    changed_paths = {item.get('path') for item in repair.get('changed') or []}
    assert 'src/main/resources/schema.sql' in changed_paths or 'src/main/resources/db/schema.sql' in changed_paths

    fixed = (resources / 'schema.sql').read_text(encoding='utf-8')
    assert 'member_name' in fixed
    assert "COMMENT '로그인 아이디'" in fixed
    assert "COMMENT='회원 정보 관리 테이블'" in fixed

    report_after = validate_generated_project(project_root, cfg, include_runtime=False)
    assert not any(issue.get('type') == 'explicit_schema_contract_mismatch' for issue in report_after.get('static_issues') or [])
