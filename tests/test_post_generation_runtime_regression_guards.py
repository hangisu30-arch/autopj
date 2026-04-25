from pathlib import Path
from types import SimpleNamespace

from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair
from app.validation.backend_compile_repair import _contract_bundle_targets


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _cfg():
    return SimpleNamespace(frontend_key="jsp", backend_key="springboot")


def test_legacy_calendar_jsp_is_auto_repaired_via_generated_project_auto_repair(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/reservation/reservationCalendar.jsp'
    _write(
        jsp,
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>'
        '<script src="${pageContext.request.contextPath}/js/fullcalendar.min.js"></script>'
        '<script>$(document).ready(function(){ $("#calendar").fullCalendar({ eventClick:function(){} }); });</script>'
    )
    report = validate_generated_project(tmp_path, _cfg(), include_runtime=False)
    assert any(i["type"] == "legacy_calendar_jsp" for i in report["static_issues"])
    repair = apply_generated_project_auto_repair(tmp_path, report)
    assert repair["changed_count"] >= 1
    body = jsp.read_text(encoding='utf-8')
    assert 'fullcalendar.min.js' not in body
    assert 'items="${calendarCells}"' in body


def test_contract_bundle_targets_include_same_domain_jsps(tmp_path: Path):
    _write(tmp_path / 'src/main/java/egovframework/demo/room/web/RoomController.java', 'package x; public class RoomController {}')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/room/roomList.jsp', 'list')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/room/roomForm.jsp', 'form')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/room/roomDetail.jsp', 'detail')
    bundle = _contract_bundle_targets(tmp_path, 'src/main/java/egovframework/demo/room/web/RoomController.java')
    assert 'src/main/webapp/WEB-INF/views/room/roomList.jsp' in bundle
    assert 'src/main/webapp/WEB-INF/views/room/roomForm.jsp' in bundle
    assert 'src/main/webapp/WEB-INF/views/room/roomDetail.jsp' in bundle
