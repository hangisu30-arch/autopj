from pathlib import Path

from app.io.execution_core_apply import _patch_generated_jsp_assets, _rewrite_form_jsp_from_schema, _build_schedule_js


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


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


def test_patch_generated_jsp_assets_discovers_and_normalizes_existing_calendar_and_korean_nav(tmp_path: Path):
    room_list = tmp_path / "src/main/webapp/WEB-INF/views/room/roomList.jsp"
    reservation_calendar = tmp_path / "src/main/webapp/WEB-INF/views/reservation/reservationCalendar.jsp"
    _write(room_list, "<html><body>list</body></html>")
    _write(
        reservation_calendar,
        '''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<link rel="stylesheet" href="${pageContext.request.contextPath}/css/fullcalendar.min.css">
<script src="${pageContext.request.contextPath}/js/moment.min.js"></script>
<script src="${pageContext.request.contextPath}/js/fullcalendar.min.js"></script>
<div id="calendar"></div>
<script>$(document).ready(function(){ $('#calendar').fullCalendar({ eventClick:function(){}}); });</script>''',
    )

    report = _patch_generated_jsp_assets(
        tmp_path,
        [str(room_list.relative_to(tmp_path)).replace("\\", "/")],
        "Room",
        {"Room": _RoomSchema(), "Reservation": _ReservationSchema()},
    )

    body = reservation_calendar.read_text(encoding="utf-8")
    header = (tmp_path / report["header_jsp"]).read_text(encoding="utf-8")
    leftnav = (tmp_path / report["leftnav_jsp"]).read_text(encoding="utf-8")

    assert 'data-autopj-schedule-page' in body
    assert '/reservation/detail.do?reservationId=' in body
    assert '/reservation/form.do?reservationId=' in body
    assert '예약 달력' in header
    assert '공간 목록' in header
    assert '바로가기' in leftnav
    assert '등록/수정' in leftnav


def test_rewrite_form_jsp_uses_korean_titles_buttons_and_field_labels(tmp_path: Path):
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/reservation/reservationForm.jsp"
    _write(jsp, "<form></form>")

    assert _rewrite_form_jsp_from_schema(tmp_path, str(jsp.relative_to(tmp_path)).replace("\\", "/"), _ReservationSchema())
    body = jsp.read_text(encoding="utf-8")
    assert '예약 등록/수정' in body
    assert '>저장<' in body
    assert '>취소<' in body
    assert '공간 ID' in body
    assert '예약자명' in body
    assert '시작 일시' in body
    assert '종료 일시' in body


def test_schedule_js_supports_selected_date_panel_and_korean_defaults():
    js = _build_schedule_js()
    assert 'var selectedDate = new Date(monthCursor);' in js
    assert '선택한 날짜에 등록된 일정이 없습니다.' in js
    assert 'data-role="calendar-cell"' in js
    assert '외 ' in js and '건' in js
    assert '제목 없음' in js
