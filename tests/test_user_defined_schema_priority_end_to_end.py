from pathlib import Path

from execution_core.builtin_crud import extract_explicit_requirement_schemas, ddl
from app.io.execution_core_apply import _schema_map_from_file_ops, _write_schema_sql_from_schemas


REQ = '''
1. 사용자 테이블 설계
- 테이블명: tb_users
- 컬럼 명:
  - user_id (사용자 PK, bigint, Primary Key, Auto Increment)
  - login_id (로그인 ID, varchar(100), not null, unique)
  - password (비밀번호, varchar(200), not null)
  - user_name (사용자명, varchar(100), not null)
  - email (이메일, varchar(200), nullable)
  - role_cd (권한코드, varchar(20), not null)
  - created_at (생성일시, datetime, not null)

2. 일정 테이블 설계
- 테이블명: tb_schedule
- 컬럼 명:
  - schedule_id (일정 PK, varchar(50), Primary Key)
  - title (제목, varchar(200), not null)
  - content (내용, text, nullable)
  - start_datetime (시작일시, datetime, not null)
  - end_datetime (종료일시, datetime, nullable)
'''


def test_explicit_user_schema_preserves_table_columns_types_and_comments():
    schemas = extract_explicit_requirement_schemas(REQ)
    login = schemas['Login']

    assert login.table == 'tb_users'
    assert [col for _prop, col, _jt in login.fields] == [
        'user_id', 'login_id', 'password', 'user_name', 'email', 'role_cd', 'created_at'
    ]
    assert login.id_column == 'user_id'
    assert login.field_db_types['user_id'] == 'BIGINT'
    assert login.field_db_types['login_id'] == 'VARCHAR(100)'
    assert login.field_db_types['password'] == 'VARCHAR(200)'
    assert login.field_db_types['created_at'] == 'DATETIME'
    assert login.field_auto_increment['user_id'] is True
    assert login.field_unique['login_id'] is True
    assert login.field_nullable['login_id'] is False
    assert login.field_nullable['email'] is True
    assert login.field_comments['user_id'] == '사용자 PK'
    assert login.field_comments['login_id'] == '로그인 ID'

    sql = ddl(login)
    assert "CREATE TABLE IF NOT EXISTS tb_users" in sql
    assert "user_id BIGINT AUTO_INCREMENT NOT NULL PRIMARY KEY COMMENT '사용자 PK'" in sql
    assert "login_id VARCHAR(100) UNIQUE NOT NULL COMMENT '로그인 ID'" in sql
    assert "password VARCHAR(200) NOT NULL COMMENT '비밀번호'" in sql
    assert "created_at DATETIME NOT NULL COMMENT '생성일시'" in sql


def test_extra_requirements_override_misleading_generated_artifacts_and_write_exact_schema_sql(tmp_path: Path):
    file_ops = [
        {
            'path': 'src/main/java/egovframework/test/user/service/vo/UserVO.java',
            'content': 'public class UserVO { private String id; private String name; private String email; }',
        },
        {
            'path': 'src/main/resources/egovframework/mapper/user/UserMapper.xml',
            'content': '<mapper><insert id="x">INSERT INTO users (id, name, email) VALUES (#{id}, #{name}, #{email})</insert></mapper>',
        },
    ]

    schema_map = _schema_map_from_file_ops(file_ops, REQ)
    login = schema_map['Login']
    schedule = schema_map['Schedule']

    assert login.authority == 'explicit'
    assert login.table == 'tb_users'
    assert [col for _prop, col, _jt in login.fields] == [
        'user_id', 'login_id', 'password', 'user_name', 'email', 'role_cd', 'created_at'
    ]
    assert schedule.table == 'tb_schedule'
    assert [col for _prop, col, _jt in schedule.fields] == [
        'schedule_id', 'title', 'content', 'start_datetime', 'end_datetime'
    ]

    written = _write_schema_sql_from_schemas(tmp_path, schema_map)
    body = written.read_text(encoding='utf-8')
    assert body.count('CREATE TABLE IF NOT EXISTS tb_users') == 1
    assert body.count('CREATE TABLE IF NOT EXISTS tb_schedule') == 1
    assert 'CREATE TABLE IF NOT EXISTS users' not in body
    assert "user_id BIGINT AUTO_INCREMENT NOT NULL PRIMARY KEY COMMENT '사용자 PK'" in body
    assert "login_id VARCHAR(100) UNIQUE NOT NULL COMMENT '로그인 ID'" in body
    assert "schedule_id VARCHAR(50) NOT NULL PRIMARY KEY COMMENT '일정 PK'" in body
    assert "content TEXT COMMENT '내용'" in body
