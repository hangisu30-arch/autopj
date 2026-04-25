from app.engine.analysis.schema_parser import SchemaParser
from execution_core.builtin_crud import ddl, infer_schema_from_plan, schema_for


def test_schema_parser_extracts_explicit_table_and_bullet_columns_from_requirements():
    text = '''
DB 규칙:
- 테이블명은 schedule 로 사용한다
- 일정 테이블이 없으면 신규 생성한다
- 최소 컬럼은 아래를 사용한다
  - schedule_id
  - title
  - content
  - start_datetime
  - end_datetime
  - all_day_yn
  - status_cd
  - priority_cd
  - location
  - writer_id
  - use_yn
  - reg_dt
  - upd_dt
'''
    tables = SchemaParser().infer_from_requirements(text, ['schedule'])
    assert len(tables) == 1
    table = tables[0]
    assert table.table_name == 'schedule'
    assert [field.column for field in table.fields] == [
        'schedule_id', 'title', 'content', 'start_datetime', 'end_datetime', 'all_day_yn',
        'status_cd', 'priority_cd', 'location', 'writer_id', 'use_yn', 'reg_dt', 'upd_dt'
    ]
    assert table.primary_key is not None
    assert table.primary_key.column == 'schedule_id'


def test_infer_schema_from_plan_preserves_explicit_user_columns_without_schedule_hardcoding():
    plan = {
        'tasks': [
            {'path': 'src/main/java/egovframework/demo/schedule/web/ScheduleController.java'},
        ],
        'requirements_text': '''
DB 규칙:
- 테이블명은 schedule 로 사용한다
- 컬럼은 아래를 사용한다
  - schedule_id
  - title
  - owner_empno
  - start_at
  - end_at
''',
    }
    schema = infer_schema_from_plan(plan)
    assert schema.table == 'schedule'
    assert [col for _prop, col, _jt in schema.fields] == [
        'schedule_id', 'title', 'owner_empno', 'start_at', 'end_at'
    ]
    sql = ddl(schema)
    assert 'owner_empno' in sql
    assert 'start_at' in sql
    assert 'end_at' in sql
    assert 'content' not in sql
    assert 'all_day_yn' not in sql
    assert 'priority_cd' not in sql


def test_schema_for_strict_fields_keeps_explicit_schedule_schema_as_is():
    schema = schema_for(
        'Schedule',
        [
            ('scheduleId', 'schedule_id', 'Long'),
            ('title', 'title', 'String'),
            ('ownerEmpno', 'owner_empno', 'String'),
            ('startAt', 'start_at', 'java.util.Date'),
            ('endAt', 'end_at', 'java.util.Date'),
        ],
        table='schedule',
        feature_kind='SCHEDULE',
        strict_fields=True,
    )
    assert [col for _prop, col, _jt in schema.fields] == [
        'schedule_id', 'title', 'owner_empno', 'start_at', 'end_at'
    ]
