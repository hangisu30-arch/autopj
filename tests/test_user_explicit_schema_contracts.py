from pathlib import Path

from execution_core.builtin_crud import extract_explicit_requirement_schemas
from app.engine.analysis.schema_parser import SchemaParser
from app.io.execution_core_apply import _schema_map_from_file_ops, _write_schema_sql_from_schemas


USER_STYLE_REQ = '''
1. 데이터베이스 테이블 설계
아래 구조로 유저 테이블을 생성하고 연동해 주세요.
- 테이블 이름: `users`
- 컬럼 명:
  - `id` (Primary Key, Auto Increment)
  - `login_id` (사용자 아이디, String, Unique)
  - `password` (비밀번호, String)
  - `created_at` (생성일자, Datetime)

2. 일정 관리 테이블 설계
- 테이블명은 `schedule` 로 사용한다
- 최소 컬럼은 아래를 사용한다
  - `schedule_id`
  - `title`
  - `content`
  - `start_datetime`
  - `end_datetime`
  - `all_day_yn`
  - `status_cd`
  - `priority_cd`
  - `location`
  - `writer_id`
  - `use_yn`
  - `reg_dt`
  - `upd_dt`
'''


def test_extract_explicit_requirement_schemas_supports_backticks_and_bullet_annotations():
    schemas = extract_explicit_requirement_schemas(USER_STYLE_REQ)

    assert 'Login' in schemas
    assert 'Schedule' in schemas

    login = schemas['Login']
    assert login.authority == 'explicit'
    assert login.table == 'users'
    assert [col for _prop, col, _jt in login.fields] == ['id', 'login_id', 'password', 'created_at']

    schedule = schemas['Schedule']
    assert schedule.authority == 'explicit'
    assert schedule.table == 'schedule'
    assert [col for _prop, col, _jt in schedule.fields] == [
        'schedule_id', 'title', 'content', 'start_datetime', 'end_datetime',
        'all_day_yn', 'status_cd', 'priority_cd', 'location', 'writer_id',
        'use_yn', 'reg_dt', 'upd_dt'
    ]


def test_schema_parser_infer_from_requirements_supports_user_style_contract():
    tables = SchemaParser().infer_from_requirements(USER_STYLE_REQ, ['users'], auth_intent=True)
    assert len(tables) == 1
    table = tables[0]
    assert table.table_name == 'users'
    assert [field.column for field in table.fields] == ['id', 'login_id', 'password', 'created_at']
    assert table.primary_key is not None
    assert table.primary_key.column == 'id'



def test_schema_map_and_schema_sql_drop_generic_table_when_explicit_contract_exists(tmp_path: Path):
    schema_path = tmp_path / 'src/main/resources/schema.sql'
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(
        'CREATE TABLE IF NOT EXISTS table (id VARCHAR(64) PRIMARY KEY, name VARCHAR(255));\n',
        encoding='utf-8',
    )

    schema_map = _schema_map_from_file_ops([], USER_STYLE_REQ)
    login = schema_map['Login']
    schedule = schema_map['Schedule']
    assert login.table == 'users'
    assert schedule.table == 'schedule'

    written = _write_schema_sql_from_schemas(tmp_path, schema_map)
    body = written.read_text(encoding='utf-8')
    assert 'CREATE TABLE IF NOT EXISTS users' in body
    assert 'CREATE TABLE IF NOT EXISTS schedule' in body
    assert 'CREATE TABLE IF NOT EXISTS table' not in body
    for column in ('id', 'login_id', 'password', 'created_at'):
        assert column in body
    for column in ('schedule_id', 'title', 'content', 'start_datetime', 'end_datetime', 'all_day_yn', 'status_cd', 'priority_cd', 'location', 'writer_id', 'use_yn', 'reg_dt', 'upd_dt'):
        assert column in body
