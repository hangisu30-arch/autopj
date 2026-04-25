from pathlib import Path
from types import SimpleNamespace

from app.engine.analysis import AnalysisContext, AnalysisEngine
from app.engine.analysis.schema_parser import SchemaParser
from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import _repair_jsp_dependency_missing, _repair_optional_param_guard_mismatch
from execution_core.builtin_crud import infer_schema_from_file_ops


def test_analysis_infers_richer_room_reservation_business_tables():
    requirements = """
    회의실 예약 관리 기능을 만든다.
    회의실 목록/등록/수정/삭제와 예약 목록/등록/수정/삭제, 예약 캘린더가 필요하다.
    JSP 기반 화면을 생성한다.
    """
    ctx = AnalysisContext.from_inputs(
        project_root='demo',
        project_name='testbiz',
        frontend_mode='jsp',
        database_type='mysql',
        requirements_text=requirements,
        schema_text='',
    )
    data = AnalysisEngine().run(ctx).to_dict()
    room = next(d for d in data['domains'] if d['name'] == 'room')
    reservation = next(d for d in data['domains'] if d['name'] == 'reservation')
    assert [f['column'] for f in room['fields']] == ['room_id', 'room_name', 'location', 'capacity', 'use_yn', 'reg_dt', 'upd_dt']
    assert [f['column'] for f in reservation['fields']] == [
        'reservation_id', 'room_id', 'reserver_name', 'purpose', 'start_datetime', 'end_datetime', 'status_cd', 'remark', 'reg_dt', 'upd_dt'
    ]


def test_schema_parser_supports_if_not_exists_and_ignores_css_noise():
    parser = SchemaParser()
    tables = parser.parse(
        """
        CREATE TABLE IF NOT EXISTS room (
          room_id BIGINT PRIMARY KEY,
          room_name VARCHAR(100),
          location VARCHAR(200)
        );
        grid-template-columns: 1fr 3fr;
        columns: 1fr, 3fr
        """
    )
    assert len(tables) == 1
    assert tables[0].table_name == 'room'
    assert [f.column for f in tables[0].fields] == ['room_id', 'room_name', 'location']


def test_builtin_schema_inference_rejects_css_identifiers():
    file_ops = [
        {
            'path': 'src/main/resources/schema.sql',
            'content': 'CREATE TABLE IF NOT EXISTS room (room_id BIGINT PRIMARY KEY, room_name VARCHAR(100), 1fr_3fr VARCHAR(10));',
        },
        {
            'path': 'src/main/webapp/WEB-INF/views/room/roomForm.jsp',
            'content': '<style>.x{grid-template-columns:1fr 3fr;}</style>\ncolumns: 1fr, 3fr',
        },
    ]
    schema = infer_schema_from_file_ops(file_ops, entity='Room')
    assert [col for _, col, _ in schema.fields] == ['room_id', 'room_name']


def test_validator_flags_css_identifier_and_missing_calendar_dependencies(tmp_path: Path):
    (tmp_path / 'src/main/java/demo/room').mkdir(parents=True)
    (tmp_path / 'src/main/resources').mkdir(parents=True)
    (tmp_path / 'src/main/webapp/WEB-INF/views/reservation').mkdir(parents=True)
    (tmp_path / 'src/main/java/demo/room/RoomVO.java').write_text(
        'package demo.room; public class RoomVO { private String bad; public String get1fr3fr(){ return bad; } }',
        encoding='utf-8',
    )
    (tmp_path / 'src/main/resources/schema.sql').write_text(
        'CREATE TABLE IF NOT EXISTS room (room_id BIGINT PRIMARY KEY, 1fr_3fr VARCHAR(20));',
        encoding='utf-8',
    )
    (tmp_path / 'src/main/webapp/WEB-INF/views/reservation/reservationCalendar.jsp').write_text(
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<div>${fn:length(list)}</div>\n'
        '<script>$(document).ready(function(){});</script>\n'
        '<script src="${pageContext.request.contextPath}/js/fullcalendar.min.js"></script>',
        encoding='utf-8',
    )
    report = validate_generated_project(tmp_path, SimpleNamespace(frontend_key='jsp'), run_runtime=False)
    codes = {item['code'] for item in report['issues']}
    assert 'illegal_identifier' in codes
    assert 'jsp_dependency_missing' in codes


def test_optional_param_guard_repair_for_string_id(tmp_path: Path):
    path = tmp_path / 'RoomController.java'
    path.write_text(
        'public class RoomController {\n'
        '  public String form(String roomId){\n'
        '    if (roomId != null && roomId.longValue() != 0L) { return roomId.longValue(); }\n'
        '    return "ok";\n'
        '  }\n'
        '}\n',
        encoding='utf-8',
    )
    issue = {
        'details': {
            'current_var_name': 'roomId',
            'current_type': 'String',
            'expected_guard': 'roomId != null && !roomId.isBlank()',
        }
    }
    assert _repair_optional_param_guard_mismatch(path, issue, None) is True
    body = path.read_text(encoding='utf-8')
    assert 'roomId.longValue()' not in body
    assert 'if (roomId != null && !roomId.isBlank())' in body


def test_jsp_dependency_repair_adds_fn_taglib(tmp_path: Path):
    path = tmp_path / 'reservationCalendar.jsp'
    path.write_text(
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n<div>${fn:length(list)}</div>',
        encoding='utf-8',
    )
    issue = {'details': {'kind': 'fn_taglib'}}
    assert _repair_jsp_dependency_missing(path, issue, tmp_path) is True
    body = path.read_text(encoding='utf-8')
    assert 'taglib prefix="fn"' in body
