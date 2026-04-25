from execution_core.builtin_crud import infer_schema_from_plan, ddl, builtin_file
from app.ui.fallback_builder import build_builtin_fallback_content
from app.engine.analysis.schema_parser import SchemaParser

REQ = """DB 규칙:
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
"""


def _plan():
    return {"requirements_text": REQ, "tasks": []}


def test_schedule_schema_uses_explicit_table_and_string_backend_types():
    schema = infer_schema_from_plan(_plan())
    assert schema.entity == "Schedule"
    assert schema.entity_var == "schedule"
    assert schema.table == "schedule"
    assert schema.id_prop == "scheduleId"
    assert schema.id_column == "schedule_id"
    field_map = {prop: (col, jt) for prop, col, jt in schema.fields}
    assert field_map["scheduleId"] == ("schedule_id", "String")
    assert field_map["startDatetime"] == ("start_datetime", "String")
    assert field_map["endDatetime"] == ("end_datetime", "String")

    sql = ddl(schema)
    assert "CREATE TABLE IF NOT EXISTS schedule" in sql
    assert "schedule_id VARCHAR(64) NOT NULL PRIMARY KEY" in sql
    assert "start_datetime DATETIME" in sql
    assert "end_datetime DATETIME" in sql


def test_schedule_mapper_xml_matches_table_and_columns_and_formats_datetime():
    schema = infer_schema_from_plan(_plan())
    xml = builtin_file("mapper/ScheduleMapper.xml", "egovframework.test", schema)
    assert xml is not None
    assert "FROM schedule" in xml
    assert "INSERT INTO schedule (schedule_id, title, content, start_datetime, end_datetime" in xml
    assert "UPDATE schedule" in xml
    assert "WHERE schedule_id = #{scheduleId}" in xml
    assert "DATE_FORMAT(start_datetime, '%Y-%m-%d %H:%i:%s') AS start_datetime" in xml
    assert "DATE_FORMAT(end_datetime, '%Y-%m-%d %H:%i:%s') AS end_datetime" in xml
    assert "STR_TO_DATE(REPLACE(#{startDatetime}, 'T', ' '), '%Y-%m-%d %H:%i:%s')" in xml
    assert "STR_TO_DATE(REPLACE(#{endDatetime}, 'T', ' '), '%Y-%m-%d %H:%i:%s')" in xml
    assert "FROM id" not in xml
    assert "INSERT INTO id" not in xml


def test_schedule_calendar_routes_do_not_fall_back_to_item():
    schema = infer_schema_from_plan(_plan())
    jsp = builtin_file("jsp/schedule/ScheduleCalendar.jsp", "egovframework.test", schema)
    assert jsp is not None
    assert jsp.count("/schedule/edit.do") >= 2
    assert "/item/edit.do" not in jsp
    assert "Schedule 달력" in jsp


def test_schedule_form_has_required_validation_markup():
    schema = infer_schema_from_plan(_plan())
    jsp = builtin_file("jsp/schedule/ScheduleForm.jsp", "egovframework.test", schema)
    assert jsp is not None
    assert "onsubmit=\"return window.autopjValidateRequired ? window.autopjValidateRequired(this) : true;\"" in jsp
    assert 'name="scheduleId"' in jsp and 'required="required"' in jsp
    assert 'name="title"' in jsp and 'required="required"' in jsp
    assert 'name="startDatetime"' in jsp and 'required="required"' in jsp
    assert 'name="endDatetime"' in jsp and 'required="required"' in jsp


def test_fallback_builder_uses_schedule_entity_from_explicit_table_name():
    jsp = build_builtin_fallback_content(
        "src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp",
        REQ,
        project_name="test",
    )
    assert "/schedule/edit.do" in jsp
    assert "/item/edit.do" not in jsp


def test_schema_parser_prefers_string_for_id_and_datetime_backend_types():
    parser = SchemaParser()
    tables = parser.infer_from_requirements(REQ, ["schedule"])
    assert len(tables) == 1
    table = tables[0]
    assert table.table_name == "schedule"
    field_map = {field.column: field.java_type for field in table.fields}
    assert field_map["schedule_id"] == "String"
    assert field_map["start_datetime"] == "String"
    assert field_map["end_datetime"] == "String"


def test_schedule_backend_signatures_align_with_schema_contract():
    schema = infer_schema_from_plan(_plan())
    controller = builtin_file('java/controller/ScheduleController.java', 'egovframework.test', schema)
    service = builtin_file('java/service/ScheduleService.java', 'egovframework.test', schema)
    mapper = builtin_file('java/service/mapper/ScheduleMapper.java', 'egovframework.test', schema)
    assert controller is not None and '@RequestParam("scheduleId") String scheduleId' in controller
    assert service is not None and 'ScheduleVO selectSchedule(String scheduleId)' in service
    assert mapper is not None and 'ScheduleVO selectSchedule(@Param("scheduleId") String scheduleId)' in mapper


def test_common_jsp_alias_is_normalized_to_header_and_leftnav(tmp_path):
    from app.validation.post_generation_repair import _normalize_jsp_layout_includes
    view = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'
    view.parent.mkdir(parents=True, exist_ok=True)
    view.write_text('<%@ include file="/WEB-INF/views/common.jsp" %>\n<div>ok</div>', encoding='utf-8')
    changed = _normalize_jsp_layout_includes(tmp_path, ['src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'])
    assert changed
    body = view.read_text(encoding='utf-8')
    assert '/WEB-INF/views/common/header.jsp' in body
    assert '/WEB-INF/views/common/leftNav.jsp' in body
    assert '/WEB-INF/views/common.jsp' not in body
