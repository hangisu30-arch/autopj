from pathlib import Path

from execution_core.builtin_crud import builtin_file, ddl, schema_for
from app.validation.project_auto_repair import _repair_delete_ui, _repair_route_param_mismatch


def test_mapper_xml_uses_same_table_and_columns_as_ddl_for_explicit_schema():
    schema = schema_for(
        'Schedule',
        [
            ('scheduleId', 'schedule_id', 'String'),
            ('title', 'title', 'String'),
            ('content', 'content', 'String'),
            ('startDatetime', 'start_datetime', 'String'),
            ('endDatetime', 'end_datetime', 'String'),
            ('useYn', 'use_yn', 'String'),
        ],
        table='schedule',
        strict_fields=True,
    )

    mapper_xml = builtin_file(
        'mapper/schedule/ScheduleMapper.xml',
        'egovframework.demo',
        schema,
    )
    schema_sql = ddl(schema)

    assert 'CREATE TABLE IF NOT EXISTS schedule' in schema_sql
    for column in ('schedule_id', 'title', 'content', 'start_datetime', 'end_datetime', 'use_yn'):
        assert column in schema_sql
        assert column in mapper_xml

    assert 'FROM schedule' in mapper_xml
    assert 'INSERT INTO schedule' in mapper_xml
    assert 'UPDATE schedule' in mapper_xml
    assert 'DELETE FROM schedule' in mapper_xml
    assert "DATE_FORMAT(start_datetime, '%Y-%m-%d %H:%i:%s') AS start_datetime" in mapper_xml
    assert "STR_TO_DATE(REPLACE(#{startDatetime}, 'T', ' '), '%Y-%m-%d %H:%i:%s')" in mapper_xml


def test_repair_delete_ui_uses_post_form_action_with_controller_route(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/demo/room/web/RoomController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.demo.room.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.PostMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/room")\n'
        'public class RoomController {\n@PostMapping("/delete.do") public String delete(){ return "redirect:/room/list.do"; }\n}',
        encoding='utf-8',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/room/roomForm.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<html><body><form action="<c:url value=\'/room/save.do\'/>" method="post"></form></body></html>', encoding='utf-8')

    changed = _repair_delete_ui(jsp, {'details': {'id_prop': 'roomId'}}, tmp_path)
    body = jsp.read_text(encoding='utf-8')

    assert changed is True
    assert "<form action=\"<c:url value='/room/delete.do'/>\" method=\"post\"" in body
    assert 'name="roomId"' in body
    assert 'location.href=' not in body


def test_route_param_mismatch_repair_updates_href_and_onclick_query_params(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/room/roomList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<html><body>'
        '<a href="<c:url value=\'/room/detail.do\'/>?id=${row.roomId}">상세</a>'
        '<button type="button" onclick="location.href=\'/room/detail.do?id=${row.roomId}\'">이동</button>'
        '</body></html>',
        encoding='utf-8',
    )

    issue = {'details': {'domain': 'room', 'route_params': {'/room/detail.do': 'roomId'}}}
    changed = _repair_route_param_mismatch(jsp, issue, tmp_path)
    body = jsp.read_text(encoding='utf-8')

    assert changed is True
    assert "detail.do'/>?roomId=" in body
    assert '/room/detail.do?roomId=' in body
