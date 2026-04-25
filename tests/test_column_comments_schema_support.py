from app.engine.analysis.schema_parser import SchemaParser
from execution_core.builtin_crud import ddl, extract_explicit_requirement_schemas, infer_schema_from_file_ops


def test_schema_parser_preserves_explicit_column_comments():
    parser = SchemaParser()
    tables = parser.infer_from_requirements(
        """
        테이블 이름: schedule
        최소 컬럼은 아래를 사용한다.
        - schedule_id (일정 ID)
        - title (일정 제목)
        - writer_id (작성자 ID)
        """,
        ["schedule"],
    )
    assert tables
    field_map = {field.column: field for field in tables[0].fields}
    assert field_map["schedule_id"].comment == "일정 ID"
    assert field_map["title"].comment == "일정 제목"
    assert field_map["writer_id"].comment == "작성자 ID"


def test_explicit_requirement_schema_adds_mysql_column_comments_to_ddl():
    schemas = extract_explicit_requirement_schemas(
        """
        테이블 이름: schedule
        최소 컬럼은 아래를 사용한다.
        - schedule_id (일정 ID)
        - title (일정 제목)
        - content (일정 내용)
        - start_datetime (시작 일시)
        """
    )
    schema = schemas["Schedule"]
    sql = ddl(schema)
    assert "schedule_id VARCHAR(64) NOT NULL PRIMARY KEY COMMENT '일정 ID'" in sql
    assert "title VARCHAR(255) COMMENT '일정 제목'" in sql
    assert "content TEXT COMMENT '일정 내용'" in sql
    assert "start_datetime DATETIME COMMENT '시작 일시'" in sql


def test_infer_schema_from_file_ops_uses_requirement_comments():
    file_ops = [
        {
            "path": "requirements.txt",
            "content": """
            테이블명: users
            컬럼명은 아래를 사용
            - login_id (로그인 아이디)
            - password (비밀번호)
            - created_at (생성 일시)
            """,
        }
    ]
    schema = infer_schema_from_file_ops(file_ops, entity="Users")
    assert schema.table == "users"
    assert schema.field_comments["login_id"] == "로그인 아이디"
    assert schema.field_comments["password"] == "비밀번호"
    assert schema.field_comments["created_at"] == "생성 일시"
