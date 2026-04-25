from pathlib import Path

from app.engine.analysis.analysis_result import DomainAnalysis, FieldInfo
from app.engine.analysis.ir_builder import IRBuilder
from app.io.execution_core_apply import _rewrite_form_jsp_from_schema, _write_schema_sql_from_schemas
from execution_core.builtin_crud import extract_explicit_requirement_schemas, schema_for


def test_write_schema_sql_from_schemas_prefers_only_explicit_contract_tables(tmp_path: Path):
    resources = tmp_path / 'src/main/resources'
    resources.mkdir(parents=True, exist_ok=True)
    (resources / 'schema.sql').write_text(
        'CREATE TABLE IF NOT EXISTS users (id BIGINT PRIMARY KEY, name VARCHAR(100));\n',
        encoding='utf-8',
    )
    requirements = """
    테이블명: tb_member
    테이블 코멘트: 회원 기본 정보
    컬럼정의:
    - member_id (회원ID, varchar(40), primary key, not null)
    - member_name (회원명, varchar(100), not null)
    - use_yn (사용여부, varchar(1), not null)
    - reg_dt (등록일시, datetime, not null)
    """
    schemas = extract_explicit_requirement_schemas(requirements)
    path = _write_schema_sql_from_schemas(tmp_path, schemas)
    body = path.read_text(encoding='utf-8')
    assert 'CREATE TABLE IF NOT EXISTS tb_member' in body
    assert 'CREATE TABLE IF NOT EXISTS users' not in body
    assert "COMMENT='회원 기본 정보'" in body
    assert "member_id VARCHAR(40) NOT NULL PRIMARY KEY COMMENT '회원ID'" in body
    assert "member_name VARCHAR(100) NOT NULL COMMENT '회원명'" in body
    assert "use_yn VARCHAR(1) NOT NULL COMMENT '사용여부'" in body
    assert "reg_dt DATETIME NOT NULL COMMENT '등록일시'" in body


def test_rewrite_form_jsp_from_schema_keeps_all_columns_and_comment_labels(tmp_path: Path):
    rel = 'src/main/webapp/WEB-INF/views/member/memberForm.jsp'
    jsp = tmp_path / rel
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<html><body><form></form></body></html>', encoding='utf-8')
    schema = schema_for(
        'Member',
        inferred_fields=[
            ('memberId', 'member_id', 'String'),
            ('memberName', 'member_name', 'String'),
            ('useYn', 'use_yn', 'String'),
            ('regDt', 'reg_dt', 'String'),
            ('updDt', 'upd_dt', 'String'),
        ],
        table='tb_member',
        strict_fields=True,
        field_comments={
            'member_id': '회원ID',
            'member_name': '회원명',
            'use_yn': '사용여부',
            'reg_dt': '등록일시',
            'upd_dt': '수정일시',
        },
    )
    changed = _rewrite_form_jsp_from_schema(tmp_path, rel, schema)
    body = jsp.read_text(encoding='utf-8')
    assert changed is True
    assert 'name="memberId"' in body
    assert 'name="memberName"' in body
    assert 'name="useYn"' in body
    assert 'name="regDt"' in body
    assert 'name="updDt"' in body
    assert '회원ID' in body
    assert '회원명' in body
    assert '사용여부' in body
    assert '등록일시' in body
    assert '수정일시' in body


def test_ir_builder_marks_audit_and_system_fields_visible_in_form_and_search():
    domain = DomainAnalysis(
        name='member',
        entity_name='Member',
        feature_kind='crud',
        fields=[
            FieldInfo(name='memberId', column='member_id', java_type='String', pk=True),
            FieldInfo(name='memberName', column='member_name', java_type='String', display=True),
            FieldInfo(name='useYn', column='use_yn', java_type='String'),
            FieldInfo(name='regDt', column='reg_dt', java_type='String'),
        ],
    )
    IRBuilder().apply(domain, 'jsp', '')
    field_map = {field['name']: field for field in domain.ir['dataModel']['fields']}
    assert field_map['memberId']['visibleInForm'] is True
    assert field_map['useYn']['visibleInForm'] is True
    assert field_map['useYn']['searchable'] is True
    assert field_map['regDt']['visibleInForm'] is True
    assert field_map['regDt']['searchable'] is True
