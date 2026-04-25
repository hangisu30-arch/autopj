
from execution_core.builtin_crud import extract_explicit_requirement_schemas
from app.engine.analysis.schema_parser import SchemaParser

REQ = '''
테이블명:
- member

테이블 comment:
- 회원 정보 테이블

컬럼정의:
- member_id / 회원 고유 ID / VARCHAR(64) / PK / NOT NULL
- login_id / 로그인 아이디 / VARCHAR(100) / UNIQUE / NOT NULL
- member_name / 회원명 / VARCHAR(100) / NOT NULL
- reg_dt / 등록 일시 / DATETIME
'''

REQ2 = '''
table: tb_member
table comment: 회원 관리 테이블
columns definition:
member_id | 회원 고유 ID | varchar(64) | pk | not null
login_id | 로그인 아이디 | varchar(100) | unique | not null
use_yn | 사용 여부 | char(1) | default:'Y' | not null
'''

def test_extract_explicit_requirement_schemas_supports_slash_format():
    schemas = extract_explicit_requirement_schemas(REQ)
    schema = schemas['Member']
    assert schema.table == 'member'
    assert schema.table_comment == '회원 정보 테이블'
    assert [col for _prop, col, _jt in schema.fields] == ['member_id', 'login_id', 'member_name', 'reg_dt']
    assert schema.field_comments['member_id'] == '회원 고유 ID'
    assert schema.field_comments['login_id'] == '로그인 아이디'
    assert schema.field_comments['member_name'] == '회원명'
    assert schema.field_comments['reg_dt'] == '등록 일시'
    assert schema.field_db_types['member_id'] == 'VARCHAR(64)'
    assert schema.field_unique['login_id'] is True
    assert schema.field_nullable['member_id'] is False

def test_extract_explicit_requirement_schemas_supports_pipe_format():
    schemas = extract_explicit_requirement_schemas(REQ2)
    schema = next(iter(schemas.values()))
    assert schema.table == 'tb_member'
    assert schema.table_comment == '회원 관리 테이블'
    assert schema.field_comments['use_yn'] == '사용 여부'
    assert schema.field_db_types['use_yn'] == 'CHAR(1)'
    assert schema.field_defaults['use_yn'] == "'Y'"

def test_schema_parser_prefers_builtin_explicit_contracts():
    tables = SchemaParser().infer_from_requirements(REQ, ['member'])
    assert tables
    table = tables[0]
    assert table.table_name == 'member'
    assert [field.column for field in table.fields] == ['member_id', 'login_id', 'member_name', 'reg_dt']
    assert table.fields[0].comment == '회원 고유 ID'
