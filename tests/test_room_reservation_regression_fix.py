from pathlib import Path
from types import SimpleNamespace

from execution_core.builtin_crud import builtin_file, infer_schema_from_file_ops
from app.io.execution_core_apply import _patch_generated_jsp_assets
from app.io.react_builtin_repair import ensure_react_frontend_crud
from app.io.vue_builtin_repair import ensure_vue_frontend_crud
from app.ui.prompt_templates import build_gemini_json_fileops_prompt
from app.ui.state import ProjectConfig


class _RoomSchema:
    entity = "Room"
    entity_var = "room"
    feature_kind = "CRUD"
    routes = {
        "list": "/room/list.do",
        "form": "/room/form.do",
    }


class _ReservationSchema:
    entity = "Reservation"
    entity_var = "reservation"
    feature_kind = "SCHEDULE"
    routes = {
        "calendar": "/reservation/calendar.do",
        "detail": "/reservation/view.do",
        "form": "/reservation/edit.do",
        "save": "/reservation/save.do",
        "delete": "/reservation/remove.do",
    }
    views = {
        "calendar": "reservation/reservationCalendar",
        "detail": "reservation/reservationDetail",
        "form": "reservation/reservationForm",
    }
    id_prop = "reservationId"
    id_column = "reservation_id"
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


class _VueRoomSchema:
    entity_var = "room"
    id_prop = "roomId"
    id_column = "room_id"
    fields = [("roomId", "room_id", "Long"), ("roomName", "room_name", "String")]


class _VueReservationSchema:
    entity_var = "reservation"
    id_prop = "reservationId"
    id_column = "reservation_id"
    fields = [("reservationId", "reservation_id", "Long"), ("startDatetime", "start_datetime", "java.util.Date")]


def test_sparse_reservation_schema_is_enriched_to_business_columns():
    file_ops = [
        {
            "path": "src/main/resources/schema.sql",
            "content": "CREATE TABLE IF NOT EXISTS reservation (reservation_id BIGINT PRIMARY KEY AUTO_INCREMENT, room_id BIGINT);",
        },
        {
            "path": "src/main/java/demo/reservation/service/vo/ReservationVO.java",
            "content": "private Long reservationId; private Long roomId;",
        },
    ]
    schema = infer_schema_from_file_ops(file_ops, entity="Reservation")
    assert schema.feature_kind == "SCHEDULE"
    assert [col for _, col, _ in schema.fields] == [
        "reservation_id",
        "room_id",
        "reserver_name",
        "purpose",
        "start_datetime",
        "end_datetime",
        "status_cd",
        "remark",
        "reg_dt",
        "upd_dt",
    ]


def test_jsp_assets_keep_room_and_reservation_navigation_and_normalize_calendar(tmp_path: Path):
    reservation_view = tmp_path / "src/main/webapp/WEB-INF/views/reservation/reservationCalendar.jsp"
    reservation_view.parent.mkdir(parents=True, exist_ok=True)
    reservation_view.write_text(
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<div class="calendar-container">${rooms}${daysInMonth}${reserved[1][0]}</div>',
        encoding="utf-8",
    )
    room_view = tmp_path / "src/main/webapp/WEB-INF/views/room/roomList.jsp"
    room_view.parent.mkdir(parents=True, exist_ok=True)
    room_view.write_text('<html><body>room</body></html>', encoding="utf-8")
    controller_root = tmp_path / "src/main/java/demo"
    (controller_root / "room").mkdir(parents=True, exist_ok=True)
    (controller_root / "reservation").mkdir(parents=True, exist_ok=True)
    (controller_root / "room/RoomController.java").write_text(
        'package demo.room;\n@Controller\n@RequestMapping("/room")\npublic class RoomController {\n'
        '  @GetMapping("/list.do") public String list(){ return "room/roomList"; }\n'
        '  @GetMapping("/form.do") public String form(){ return "room/roomForm"; }\n'
        '}\n',
        encoding="utf-8",
    )
    (controller_root / "reservation/ReservationController.java").write_text(
        'package demo.reservation;\n@Controller\n@RequestMapping("/reservation")\npublic class ReservationController {\n'
        '  @GetMapping("/calendar.do") public String calendar(){ return "reservation/reservationCalendar"; }\n'
        '  @GetMapping("/edit.do") public String edit(){ return "reservation/reservationForm"; }\n'
        '}\n',
        encoding="utf-8",
    )

    report = _patch_generated_jsp_assets(
        tmp_path,
        [
            "src/main/webapp/WEB-INF/views/reservation/reservationCalendar.jsp",
            "src/main/webapp/WEB-INF/views/room/roomList.jsp",
        ],
        "Reservation",
        {"Room": _RoomSchema(), "Reservation": _ReservationSchema()},
    )

    header = (tmp_path / report["header_jsp"]).read_text(encoding="utf-8")
    leftnav = (tmp_path / report["leftnav_jsp"]).read_text(encoding="utf-8")
    normalized = reservation_view.read_text(encoding="utf-8")

    assert "/room/list.do" in header
    assert "/reservation/calendar.do" in header
    assert "/room/list.do" in leftnav
    assert "/reservation/calendar.do" in leftnav
    assert "calendarCells" in normalized
    assert "daysInMonth" not in normalized
    assert "${rooms}" not in normalized


def test_vue_frontend_nav_includes_multiple_domains(tmp_path: Path):
    report = ensure_vue_frontend_crud(
        tmp_path,
        {"Room": _VueRoomSchema(), "Reservation": _VueReservationSchema()},
    )
    assert "frontend/vue/src/App.vue" in report
    app_vue = (tmp_path / "frontend/vue/src/App.vue").read_text(encoding="utf-8")
    routes_js = (tmp_path / "frontend/vue/src/constants/routes.js").read_text(encoding="utf-8")
    router_js = (tmp_path / "frontend/vue/src/router/index.js").read_text(encoding="utf-8")
    assert "/room/list" in app_vue
    assert "/reservation/list" in app_vue
    assert "ROOM_LIST" in routes_js
    assert "RESERVATION_LIST" in routes_js
    assert "ReservationList" in router_js


def test_prompt_requires_multi_domain_nav_and_calendar_refresh_rule():
    cfg = ProjectConfig(project_name="demo", frontend_key="jsp", frontend_label="jsp")
    prompt = build_gemini_json_fileops_prompt(cfg)
    assert "여러 업무 도메인(room/reservation 등)" in prompt
    assert "캘린더 이벤트에 즉시 반영" in prompt


def test_reservation_schedule_controller_and_calendar_jsp_share_business_fields():
    schema = infer_schema_from_file_ops([
        {
            "path": "src/main/resources/schema.sql",
            "content": "CREATE TABLE IF NOT EXISTS reservation (reservation_id BIGINT PRIMARY KEY AUTO_INCREMENT, room_id BIGINT);",
        }
    ], entity="Reservation")
    controller = builtin_file("java/controller/ReservationController.java", "egovframework.demo.reservation", schema)
    calendar_jsp = builtin_file("jsp/reservationCalendar.jsp", "egovframework.demo.reservation", schema)
    cols = [col for _, col, _ in schema.fields]
    assert "start_datetime" in cols and "end_datetime" in cols
    assert "calendarCells" in controller
    assert "selectedDateSchedules" in controller
    assert "calendarCells" in calendar_jsp
    assert "selectedDateSchedules" in calendar_jsp


def test_react_frontend_routes_include_multiple_domains(tmp_path: Path):
    report = ensure_react_frontend_crud(
        tmp_path,
        {"Room": _VueRoomSchema(), "Reservation": _VueReservationSchema()},
    )
    assert "frontend/react/src/routes/index.jsx" in report
    routes = (tmp_path / "frontend/react/src/routes/index.jsx").read_text(encoding="utf-8")
    main_page = (tmp_path / "frontend/react/src/pages/main/MainPage.jsx").read_text(encoding="utf-8")
    assert "ROOM_LIST" in routes
    assert "RESERVATION_LIST" in routes
    assert "Room 관리" in main_page
    assert "Reservation 관리" in main_page
