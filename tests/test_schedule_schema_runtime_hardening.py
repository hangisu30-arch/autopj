from pathlib import Path

from execution_core.builtin_crud import extract_explicit_requirement_schemas, builtin_file, schema_for
from app.io.execution_core_apply import _write_schema_sql_from_schemas


COMBINED_SINGLE_BLOCK = """
로그인과 일정 기능을 함께 만든다.
DB 규칙:
- 테이블명은 login 로 사용한다
- 최소 컬럼은 아래를 사용한다
  - login_id
  - password
DB 규칙:
- 테이블명은 schedule 로 사용한다
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
"""


def test_extract_explicit_requirement_schemas_handles_multiple_tables_in_one_block():
    schema_map = extract_explicit_requirement_schemas(COMBINED_SINGLE_BLOCK)
    assert 'Login' in schema_map
    assert 'Schedule' in schema_map
    assert schema_map['Login'].table == 'login'
    assert schema_map['Schedule'].table == 'schedule'
    assert [col for _prop, col, _jt in schema_map['Schedule'].fields][:5] == [
        'schedule_id', 'title', 'content', 'start_datetime', 'end_datetime'
    ]


def test_write_schema_sql_prunes_generic_existing_table_when_authoritative_schedule_exists(tmp_path: Path):
    resources = tmp_path / 'src/main/resources'
    resources.mkdir(parents=True, exist_ok=True)
    (resources / 'schema.sql').write_text(
        'CREATE TABLE IF NOT EXISTS table (id VARCHAR(64) PRIMARY KEY, title VARCHAR(255));\n\n'
        'CREATE TABLE IF NOT EXISTS login (login_id VARCHAR(64) PRIMARY KEY, password VARCHAR(255));\n',
        encoding='utf-8',
    )
    schedule_schema = schema_for(
        'Schedule',
        [
            ('scheduleId', 'schedule_id', 'String'),
            ('title', 'title', 'String'),
            ('content', 'content', 'String'),
            ('startDatetime', 'start_datetime', 'String'),
            ('endDatetime', 'end_datetime', 'String'),
        ],
        table='schedule',
        feature_kind='SCHEDULE',
        strict_fields=True,
    )
    schedule_schema.authority = 'explicit'
    login_schema = schema_for(
        'Login',
        [('loginId', 'login_id', 'String'), ('password', 'password', 'String')],
        table='login',
        feature_kind='AUTH',
        strict_fields=True,
    )
    login_schema.authority = 'explicit'

    path = _write_schema_sql_from_schemas(tmp_path, {'Schedule': schedule_schema, 'Login': login_schema})
    body = path.read_text(encoding='utf-8')

    assert 'CREATE TABLE IF NOT EXISTS schedule' in body
    assert 'CREATE TABLE IF NOT EXISTS login' in body
    assert 'CREATE TABLE IF NOT EXISTS table' not in body


def test_schedule_controller_maps_spanning_events_and_uses_title_below_calendar_day():
    schema = schema_for(
        'Schedule',
        [
            ('scheduleId', 'schedule_id', 'String'),
            ('title', 'title', 'String'),
            ('content', 'content', 'String'),
            ('startDatetime', 'start_datetime', 'String'),
            ('endDatetime', 'end_datetime', 'String'),
            ('allDayYn', 'all_day_yn', 'String'),
        ],
        table='schedule',
        feature_kind='SCHEDULE',
        strict_fields=True,
    )
    controller = builtin_file('java/controller/ScheduleController.java', 'egovframework.demo', schema)
    jsp = builtin_file('jsp/schedule/ScheduleCalendar.jsp', 'egovframework.demo', schema)
    mapper_xml = builtin_file('mapper/ScheduleMapper.xml', 'egovframework.demo', schema)

    assert 'LocalDate endDate = _extractDate(row.getEndDatetime());' in controller
    assert 'for (LocalDate cursor = startDate; !cursor.isAfter(endDate); cursor = cursor.plusDays(1))' in controller
    assert 'String text = String.valueOf(value).trim();' in controller
    assert '<span class="calendar-event-chip"><c:out value="${row.title}"/></span>' in jsp
    assert "DATE_FORMAT(start_datetime, '%Y-%m-%dT%H:%i') AS start_datetime" in mapper_xml
    assert "WHEN LENGTH(TRIM(REPLACE(#{startDatetime}, 'T', ' '))) = 16 THEN CONCAT(TRIM(REPLACE(#{startDatetime}, 'T', ' ')), ':00')" in mapper_xml
