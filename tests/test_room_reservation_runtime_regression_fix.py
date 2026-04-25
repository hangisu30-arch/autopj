from pathlib import Path
from types import SimpleNamespace

from app.io.execution_core_apply import (
    _patch_generated_jsp_assets,
    _schema_map_from_file_ops,
    _rewrite_list_jsp_from_schema,
    _rewrite_form_jsp_from_schema,
    _normalize_calendar_jsp,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class _RoomSchema:
    entity = "Room"
    entity_var = "room"
    feature_kind = "CRUD"
    id_prop = "roomId"
    fields = [
        ("roomId", "room_id", "Long"),
        ("roomName", "room_name", "String"),
        ("location", "location", "String"),
        ("capacity", "capacity", "Integer"),
        ("useYn", "use_yn", "String"),
    ]
    routes = {
        "list": "/room/list.do",
        "detail": "/room/detail.do",
        "form": "/room/form.do",
        "save": "/room/save.do",
        "delete": "/room/delete.do",
    }


class _ReservationSchema:
    entity = "Reservation"
    entity_var = "reservation"
    feature_kind = "SCHEDULE"
    id_prop = "reservationId"
    fields = [
        ("reservationId", "reservation_id", "Long"),
        ("roomId", "room_id", "Long"),
        ("reserverName", "reserver_name", "String"),
        ("purpose", "purpose", "String"),
        ("startDatetime", "start_datetime", "java.util.Date"),
        ("endDatetime", "end_datetime", "java.util.Date"),
        ("statusCd", "status_cd", "String"),
        ("remark", "remark", "String"),
    ]
    routes = {
        "calendar": "/reservation/calendar.do",
        "detail": "/reservation/detail.do",
        "form": "/reservation/form.do",
        "save": "/reservation/save.do",
        "delete": "/reservation/delete.do",
    }


def test_multi_entity_navigation_keeps_room_and_reservation_and_skips_generic_view(tmp_path: Path):
    _write(
        tmp_path / "src/main/java/egovframework/demo/room/web/RoomController.java",
        '''package egovframework.demo.room.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.*;
import org.springframework.ui.Model;
@Controller @RequestMapping("/room")
public class RoomController {
  @GetMapping("/list.do") public String list(Model model) { return "room/roomList"; }
  @GetMapping("/form.do") public String form(@RequestParam(value="roomId", required=false) Long roomId, Model model) { return "room/roomForm"; }
}
''',
    )
    _write(
        tmp_path / "src/main/java/egovframework/demo/reservation/web/ReservationController.java",
        '''package egovframework.demo.reservation.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.*;
import org.springframework.ui.Model;
@Controller @RequestMapping("/reservation")
public class ReservationController {
  @GetMapping("/calendar.do") public String calendar(Model model) { return "reservation/reservationCalendar"; }
  @GetMapping("/form.do") public String form(@RequestParam(value="reservationId", required=false) Long reservationId, Model model) { return "reservation/reservationForm"; }
  @GetMapping("/detail.do") public String detail(@RequestParam("reservationId") Long reservationId, Model model) { return "reservation/reservationDetail"; }
}
''',
    )
    _write(
        tmp_path / "src/main/java/egovframework/demo/web/ViewController.java",
        '''package egovframework.demo.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.*;
@Controller
public class ViewController {
  @GetMapping("/view/{viewName}.do") public String view(@PathVariable String viewName) { return viewName; }
}
''',
    )
    view = tmp_path / "src/main/webapp/WEB-INF/views/reservation/reservationCalendar.jsp"
    _write(view, "<html><head></head><body>calendar</body></html>")

    report = _patch_generated_jsp_assets(
        tmp_path,
        [str(view.relative_to(tmp_path)).replace("\\", "/")],
        "Room",
        {"Room": _RoomSchema(), "Reservation": _ReservationSchema()},
    )

    header = (tmp_path / report["header_jsp"]).read_text(encoding="utf-8")
    leftnav = (tmp_path / report["leftnav_jsp"]).read_text(encoding="utf-8")
    assert "/room/list.do" in header
    assert "/reservation/calendar.do" in header
    assert "/reservation/calendar.do" in leftnav
    assert "/room/form.do" in leftnav
    assert "/view/{viewName}.do" not in header
    assert "/view/{viewName}.do" not in leftnav


def test_schema_map_upgrades_weak_room_and_reservation_business_columns(tmp_path: Path):
    file_ops = [
        {
            "path": "src/main/java/egovframework/demo/room/service/vo/RoomVO.java",
            "content": "package x; public class RoomVO { private String roomId; private java.util.Date startDatetime; private java.util.Date endDatetime; private String roomName; private String get1fr3fr; }",
        },
        {
            "path": "src/main/resources/egovframework/mapper/room/RoomMapper.xml",
            "content": "<mapper namespace=\"egovframework.demo.room.service.mapper.RoomMapper\">SELECT room_id, start_datetime, end_datetime, room_name, 1fr_3fr FROM room</mapper>",
        },
        {
            "path": "src/main/java/egovframework/demo/reservation/service/vo/ReservationVO.java",
            "content": "package x; public class ReservationVO { private String roomId; private java.util.Date startDatetime; private java.util.Date endDatetime; private String roomName; }",
        },
        {
            "path": "src/main/resources/egovframework/mapper/reservation/ReservationMapper.xml",
            "content": "<mapper namespace=\"egovframework.demo.reservation.service.mapper.ReservationMapper\">SELECT room_id, start_datetime, end_datetime, room_name FROM reservation</mapper>",
        },
    ]

    schema_map = _schema_map_from_file_ops(file_ops)
    room_fields = {prop for prop, _col, _jt in schema_map["Room"].fields}
    reservation_fields = {prop for prop, _col, _jt in schema_map["Reservation"].fields}

    assert {"roomId", "roomName", "location", "capacity", "useYn"}.issubset(room_fields)
    assert "startDatetime" not in room_fields
    assert "get1fr3fr" not in room_fields
    assert {"reservationId", "roomId", "reserverName", "purpose", "startDatetime", "endDatetime", "statusCd"}.issubset(reservation_fields)
    assert "roomName" not in reservation_fields


def test_list_rewrite_builds_designed_shell(tmp_path: Path):
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/room/roomList.jsp"
    _write(jsp, "list")

    assert _rewrite_list_jsp_from_schema(tmp_path, str(jsp.relative_to(tmp_path)).replace("\\", "/"), _RoomSchema())
    body = jsp.read_text(encoding="utf-8")
    assert 'common/header.jsp' in body
    assert 'common/leftNav.jsp' in body
    assert 'page-shell' in body
    assert 'table-wrap' in body
    assert '<ul>' not in body
    assert 'Room Name' in body
    assert 'Location' in body


def test_form_rewrite_keeps_temporal_raw_value_attribute(tmp_path: Path):
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/reservation/reservationForm.jsp"
    _write(jsp, "<form></form>")

    assert _rewrite_form_jsp_from_schema(tmp_path, str(jsp.relative_to(tmp_path)).replace("\\", "/"), _ReservationSchema())
    body = jsp.read_text(encoding="utf-8")
    assert 'name="startDatetime"' in body
    assert 'type="datetime-local"' in body
    assert 'data-autopj-raw-value=' in body


def test_legacy_reservation_calendar_is_normalized_to_common_schedule_shell(tmp_path: Path):
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/reservation/reservationCalendar.jsp"
    _write(
        jsp,
        '''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<link rel="stylesheet" href="${pageContext.request.contextPath}/css/fullcalendar.min.css">
<script src="${pageContext.request.contextPath}/js/moment.min.js"></script>
<script src="${pageContext.request.contextPath}/js/fullcalendar.min.js"></script>
<div id="calendar"></div>
<script>$(document).ready(function(){ $('#calendar').fullCalendar({ eventClick:function(){}}); });</script>''',
    )

    assert _normalize_calendar_jsp(tmp_path, str(jsp.relative_to(tmp_path)).replace("\\", "/"), _ReservationSchema())
    body = jsp.read_text(encoding="utf-8")
    assert 'data-autopj-schedule-page' in body
    assert '/reservation/detail.do?reservationId=' in body
    assert '/reservation/form.do?reservationId=' in body
    assert '/js/schedule.js' in body
