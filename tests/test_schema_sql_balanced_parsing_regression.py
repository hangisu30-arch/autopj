from pathlib import Path
from app.validation.generated_project_validator import _parse_schema_sql_tables
from execution_core.builtin_crud import _table_field_specs_from_text


def test_schema_sql_parser_keeps_all_columns_and_comments(tmp_path: Path):
    root = tmp_path
    schema = root / 'src/main/resources/schema.sql'
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text(
        """
        DROP TABLE IF EXISTS login;
        CREATE TABLE IF NOT EXISTS login (
          login_id varchar(50) NOT NULL COMMENT '로그인ID',
          password varchar(200) NOT NULL COMMENT '비밀번호',
          use_yn varchar(1) NOT NULL COMMENT '사용여부',
          reg_dt datetime COMMENT '등록일시'
        );
        """,
        encoding='utf-8'
    )
    parsed = _parse_schema_sql_tables(root)
    assert parsed['login']['columns'] == ['login_id', 'password', 'use_yn', 'reg_dt']
    assert parsed['login']['comments']['login_id'] == '로그인ID'
    assert parsed['login']['comments']['password'] == '비밀번호'


def test_builtin_crud_create_table_parser_keeps_all_columns():
    text = """
    CREATE TABLE IF NOT EXISTS reservation (
      reservation_id varchar(50) NOT NULL COMMENT '예약ID',
      room_id varchar(50) NOT NULL COMMENT '회의실ID',
      start_datetime datetime NOT NULL COMMENT '시작일시',
      end_datetime datetime NOT NULL COMMENT '종료일시'
    );
    """
    specs = _table_field_specs_from_text(text)
    assert 'reservation' in specs
    cols = [col for _prop, col, _jt in specs['reservation']]
    assert cols == ['reservation_id', 'room_id', 'start_datetime', 'end_datetime']
