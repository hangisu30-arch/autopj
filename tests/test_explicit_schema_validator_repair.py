
import json
from pathlib import Path

from app.validation.generated_project_validator import _scan_explicit_requirement_schema_contract
from app.validation.project_auto_repair import _repair_explicit_schema_contract

REQ = '''
테이블명: member
테이블 comment: 회원 정보 테이블
컬럼정의:
- member_id / 회원 고유 ID / VARCHAR(64) / PK / NOT NULL
- member_name / 회원명 / VARCHAR(100) / NOT NULL
- reg_dt / 등록 일시 / DATETIME
'''

def _seed_project(root: Path):
    (root / '.autopj_debug').mkdir(parents=True, exist_ok=True)
    (root / 'src/main/resources').mkdir(parents=True, exist_ok=True)
    (root / '.autopj_debug/analysis_result.json').write_text(json.dumps({'inputs': {'requirements_text': REQ}}, ensure_ascii=False), encoding='utf-8')
    (root / 'src/main/resources/schema.sql').write_text(
        "CREATE TABLE IF NOT EXISTS member (member_name VARCHAR(64) COMMENT 'member_name', reg_dt DATETIME COMMENT 'reg_dt') COMMENT='';",
        encoding='utf-8',
    )

def test_validator_detects_explicit_schema_contract_mismatch(tmp_path: Path):
    _seed_project(tmp_path)
    issues = _scan_explicit_requirement_schema_contract(tmp_path)
    assert any(issue.get('type') == 'explicit_schema_contract_mismatch' for issue in issues)

def test_repair_explicit_schema_contract_rewrites_exact_schema(tmp_path: Path):
    _seed_project(tmp_path)
    issue = {
        'details': {'table': 'member'},
        'path': 'src/main/resources/schema.sql',
    }
    changed = _repair_explicit_schema_contract(tmp_path / 'src/main/resources/schema.sql', issue, tmp_path)
    assert changed is True
    body = (tmp_path / 'src/main/resources/schema.sql').read_text(encoding='utf-8')
    assert "member_id VARCHAR(64) NOT NULL PRIMARY KEY COMMENT '회원 고유 ID'" in body
    assert "member_name VARCHAR(100) NOT NULL COMMENT '회원명'" in body
    assert "reg_dt DATETIME COMMENT '등록 일시'" in body
    assert "COMMENT='회원 정보 테이블'" in body
