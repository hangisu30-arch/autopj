from execution_core.builtin_crud import ddl, schema_for, builtin_file
from app.ui.fallback_builder import build_builtin_fallback_content


def test_schema_prefers_string_ids_and_string_temporal_fields():
    schema = schema_for(
        'Schedule',
        [
            ('scheduleId', 'schedule_id', 'String'),
            ('title', 'title', 'String'),
            ('startDatetime', 'start_datetime', 'String'),
            ('endDatetime', 'end_datetime', 'String'),
            ('writerId', 'writer_id', 'String'),
        ],
        table='schedule',
        feature_kind='SCHEDULE',
        strict_fields=True,
    )
    type_map = {col: jt for _prop, col, jt in schema.fields}
    assert type_map['schedule_id'] == 'String'
    assert type_map['start_datetime'] == 'String'
    assert type_map['end_datetime'] == 'String'


def test_ddl_uses_varchar_for_ids_and_datetime_for_temporal_columns():
    schema = schema_for(
        'Schedule',
        [
            ('scheduleId', 'schedule_id', 'String'),
            ('title', 'title', 'String'),
            ('startDatetime', 'start_datetime', 'String'),
            ('endDatetime', 'end_datetime', 'String'),
            ('allDayYn', 'all_day_yn', 'String'),
        ],
        table='schedule',
        feature_kind='SCHEDULE',
        strict_fields=True,
    )
    sql = ddl(schema)
    assert 'schedule_id VARCHAR(64) NOT NULL PRIMARY KEY' in sql
    assert 'start_datetime DATETIME' in sql
    assert 'end_datetime DATETIME' in sql
    assert 'all_day_yn VARCHAR(1)' in sql


def test_mapper_xml_formats_datetime_columns_and_converts_string_inputs_in_query():
    schema = schema_for(
        'Schedule',
        [
            ('scheduleId', 'schedule_id', 'String'),
            ('title', 'title', 'String'),
            ('startDatetime', 'start_datetime', 'String'),
            ('endDatetime', 'end_datetime', 'String'),
            ('useYn', 'use_yn', 'String'),
        ],
        table='schedule',
        feature_kind='CRUD',
        strict_fields=True,
    )
    xml = builtin_file('mapper/ScheduleMapper.xml', 'egovframework.demo', schema)
    assert "DATE_FORMAT(start_datetime, '%Y-%m-%dT%H:%i') AS start_datetime" in xml
    assert "DATE_FORMAT(end_datetime, '%Y-%m-%dT%H:%i') AS end_datetime" in xml
    assert "STR_TO_DATE(#{startDatetime}" not in xml  # guarded through CASE/REPLACE helper
    assert "REPLACE(#{startDatetime}, 'T', ' ')" in xml
    assert "REPLACE(#{endDatetime}, 'T', ' ')" in xml
    assert 'INSERT INTO schedule' in xml
    assert 'UPDATE schedule' in xml


def test_schedule_controller_and_vo_use_string_types():
    schema = schema_for(
        'Schedule',
        [
            ('scheduleId', 'schedule_id', 'String'),
            ('title', 'title', 'String'),
            ('startDatetime', 'start_datetime', 'String'),
            ('endDatetime', 'end_datetime', 'String'),
        ],
        table='schedule',
        feature_kind='SCHEDULE',
        strict_fields=True,
    )
    vo = builtin_file('java/service/vo/ScheduleVO.java', 'egovframework.demo', schema)
    controller = builtin_file('java/controller/ScheduleController.java', 'egovframework.demo', schema)
    assert 'private String scheduleId;' in vo
    assert 'private String startDatetime;' in vo
    assert '@DateTimeFormat' not in vo
    assert '@RequestParam("scheduleId") String scheduleId' in controller
    assert "String text = String.valueOf(value).trim();" in controller


def test_fallback_builder_respects_string_id_and_string_datetime_preferences():
    spec = '''
DB 규칙:
- 테이블명은 schedule 로 사용한다
- 최소 컬럼은 아래를 사용한다
  - schedule_id
  - title
  - start_datetime
  - end_datetime
  - use_yn
'''
    body = build_builtin_fallback_content(
        'src/main/java/egovframework/demo/schedule/service/vo/ScheduleVO.java',
        spec,
        project_name='demo',
    )
    assert 'private String scheduleId;' in body
    assert 'private String startDatetime;' in body
    assert 'private String endDatetime;' in body
