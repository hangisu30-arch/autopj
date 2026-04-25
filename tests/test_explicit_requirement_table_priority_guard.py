from pathlib import Path

from execution_core.builtin_crud import extract_explicit_requirement_schemas
from app.io.execution_core_apply import _write_schema_sql_from_schemas


MULTI_REQ = '''로그인 기능과 일정 기능을 같이 추가한다.
DB 규칙:
- 테이블명은 login 으로 사용한다
- 최소 컬럼은 아래를 사용한다
  - login_id
  - password
이어서 일정 기능도 추가한다.
DB 규칙:
- 테이블명은 schedule 로 사용한다
- 최소 컬럼은 아래를 사용한다
  - schedule_id
  - title
  - start_datetime
  - end_datetime
'''


EXISTING_SCHEMA_SQL = '''
CREATE TABLE IF NOT EXISTS table (
  id VARCHAR(64) PRIMARY KEY,
  title VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS login (
  login_id VARCHAR(64) PRIMARY KEY,
  password VARCHAR(255)
);
'''


def test_extract_explicit_requirement_schemas_keeps_multiple_requested_tables_even_without_blank_lines():
    schemas = extract_explicit_requirement_schemas(MULTI_REQ)
    assert set(schemas.keys()) == {'Login', 'Schedule'}
    assert schemas['Login'].table == 'login'
    assert [col for _prop, col, _jt in schemas['Login'].fields] == ['login_id', 'password']
    assert schemas['Schedule'].table == 'schedule'
    assert [col for _prop, col, _jt in schemas['Schedule'].fields] == [
        'schedule_id', 'title', 'start_datetime', 'end_datetime'
    ]


def test_write_schema_sql_from_schemas_drops_stale_generic_table_when_explicit_contract_exists(tmp_path: Path):
    schema_dir = tmp_path / 'src/main/resources'
    schema_dir.mkdir(parents=True, exist_ok=True)
    (schema_dir / 'schema.sql').write_text(EXISTING_SCHEMA_SQL, encoding='utf-8')

    schema_map = extract_explicit_requirement_schemas(MULTI_REQ)
    path = _write_schema_sql_from_schemas(tmp_path, schema_map)

    body = path.read_text(encoding='utf-8')
    assert 'CREATE TABLE IF NOT EXISTS login' in body
    assert 'CREATE TABLE IF NOT EXISTS schedule' in body
    assert 'CREATE TABLE IF NOT EXISTS table' not in body
    assert 'schedule_id' in body
    assert 'start_datetime' in body
