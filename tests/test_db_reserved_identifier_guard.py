from pathlib import Path

from execution_core.builtin_crud import ddl, extract_explicit_requirement_schemas, schema_for
from app.ui.state import ProjectConfig
from app.validation.generated_project_validator import validate_generated_project


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_schema_for_sanitizes_reserved_table_and_column_names_for_mysql():
    schema = schema_for(
        'Schema',
        inferred_fields=[('schema', 'schema', 'String'), ('order', 'order', 'String'), ('group', 'group', 'String')],
        table='user',
        db_vendor='mysql',
    )

    assert schema.table == 'user_account'
    assert [col for _prop, col, _jt in schema.fields] == ['schema_name', 'sort_order', 'group_name']
    assert [prop for prop, _col, _jt in schema.fields] == ['schemaName', 'sortOrder', 'groupName']

    sql = ddl(schema)
    assert 'CREATE TABLE IF NOT EXISTS user_account' in sql
    assert 'schema_name VARCHAR(64)' in sql
    assert 'sort_order VARCHAR(255)' in sql
    assert 'group_name VARCHAR(255)' in sql
    assert 'CREATE TABLE IF NOT EXISTS user (' not in sql
    assert ' schema VARCHAR(255)' not in sql


def test_explicit_requirement_schema_sanitizes_reserved_identifiers_by_default_union_guard():
    req = """
    테이블명: user
    컬럼:
    - schema (스키마명, varchar(50), not null)
    - order (정렬순서, int)
    - desc (설명, varchar(200))
    """
    schemas = extract_explicit_requirement_schemas(req)
    schema = next(iter(schemas.values()))

    assert schema.table == 'user_account'
    assert [col for _prop, col, _jt in schema.fields] == ['schema_name', 'sort_order', 'description']
    assert schema.field_comments['schema_name'] == '스키마명'
    assert schema.field_comments['sort_order'] == '정렬순서'
    assert schema.field_comments['description'] == '설명'


def test_validator_reports_reserved_db_identifiers_in_schema_sql(tmp_path: Path):
    _write(
        tmp_path / 'src/main/resources/schema.sql',
        'CREATE TABLE IF NOT EXISTS user (schema VARCHAR(50), order VARCHAR(20));',
    )
    cfg = ProjectConfig(project_name='demo', frontend_key='jsp', backend_key='egov_spring', database_key='mysql')
    report = validate_generated_project(tmp_path, cfg=cfg, manifest=None, run_runtime=False)

    codes = {item['code'] for item in report['issues']}
    assert 'reserved_db_identifier' in codes
    messages = [item['details']['message'] for item in report['issues'] if item['code'] == 'reserved_db_identifier']
    assert any('table name: user' in msg for msg in messages)
    assert any('column name: schema' in msg for msg in messages)
    assert any('column name: order' in msg for msg in messages)
