from pathlib import Path
from types import SimpleNamespace

from app.adapters.jsp.jsp_prompt_builder import jsp_plan_to_prompt_text
from app.adapters.react.react_prompt_builder import react_plan_to_prompt_text
from app.adapters.vue.vue_prompt_builder import vue_plan_to_prompt_text
from app.io.execution_core_apply import (
    _build_header_jsp,
    _build_leftnav_jsp,
    _normalize_calendar_jsp,
    _rewrite_form_jsp_from_schema,
    _rewrite_list_jsp_from_schema,
)
from app.validation.generated_project_validator import validate_generated_project


def _reservation_schema():
    return SimpleNamespace(
        entity="Reservation",
        entity_var="reservation",
        id_prop="reservationId",
        id_column="reservation_id",
        fields=[
            ("reservationId", "reservation_id", "Long"),
            ("roomId", "room_id", "Long"),
            ("reserverName", "reserver_name", "String"),
            ("purpose", "purpose", "String"),
            ("startDatetime", "start_datetime", "java.util.Date"),
            ("endDatetime", "end_datetime", "java.util.Date"),
            ("statusCd", "status_cd", "String"),
            ("remark", "remark", "String"),
        ],
        routes={
            "list": "/reservation/list.do",
            "calendar": "/reservation/calendar.do",
            "detail": "/reservation/detail.do",
            "form": "/reservation/edit.do",
            "save": "/reservation/save.do",
            "delete": "/reservation/delete.do",
        },
    )


def test_form_rewrite_replaces_plain_text_placeholder_and_preserves_temporal_raw_value(tmp_path: Path):
    schema = _reservation_schema()
    form_path = tmp_path / "src/main/webapp/WEB-INF/views/reservation/reservationForm.jsp"
    form_path.parent.mkdir(parents=True, exist_ok=True)
    form_path.write_text("<html><body><h1>reservationForm</h1><p>plain placeholder</p></body></html>", encoding="utf-8")

    assert _rewrite_form_jsp_from_schema(tmp_path, str(form_path.relative_to(tmp_path)).replace("\\", "/"), schema)
    body = form_path.read_text(encoding="utf-8")
    assert 'common/header.jsp' in body
    assert 'class="autopj-form-card form-card"' in body
    assert 'data-autopj-raw-value="<c:out value=\'${item.startDatetime}\'/>"' in body
    assert 'data-autopj-temporal="datetime-local"' in body


def test_list_rewrite_uses_shared_layout_and_card_design(tmp_path: Path):
    schema = _reservation_schema()
    list_path = tmp_path / "src/main/webapp/WEB-INF/views/reservation/reservationList.jsp"
    list_path.parent.mkdir(parents=True, exist_ok=True)
    list_path.write_text("<html><body><ul><li>plain</li></ul></body></html>", encoding="utf-8")

    assert _rewrite_list_jsp_from_schema(tmp_path, str(list_path.relative_to(tmp_path)).replace("\\", "/"), schema)
    body = list_path.read_text(encoding="utf-8")
    assert 'common/header.jsp' in body
    assert 'common/leftNav.jsp' in body
    assert 'autopj-record-grid' in body
    assert "<c:url value='/reservation/detail.do'/>?reservationId=${row.reservationId}" in body


def test_calendar_normalization_rewrites_legacy_fullcalendar_page_with_working_links(tmp_path: Path):
    schema = _reservation_schema()
    cal_path = tmp_path / "src/main/webapp/WEB-INF/views/reservation/reservationCalendar.jsp"
    cal_path.parent.mkdir(parents=True, exist_ok=True)
    cal_path.write_text(
        '<html><head><script src="${pageContext.request.contextPath}/js/fullcalendar.min.js"></script></head>'
        '<body><script>$(document).ready(function(){ $("#calendar").fullCalendar({ eventClick:function(){}, dayClick:function(){} }); });</script></body></html>',
        encoding="utf-8",
    )

    assert _normalize_calendar_jsp(tmp_path, str(cal_path.relative_to(tmp_path)).replace("\\", "/"), schema=schema)
    body = cal_path.read_text(encoding="utf-8")
    assert 'data-autopj-schedule-page' in body
    assert '/reservation/detail.do?reservationId=${item.reservationId}' in body
    assert '/reservation/edit.do?reservationId=${item.reservationId}' in body
    assert 'fullcalendar.min.js' not in body


def test_navigation_builders_exclude_unresolved_generic_view_route():
    schema = _reservation_schema()
    nav_override = {
        'main_url': '/reservation/calendar.do',
        'top': [('홈', '/', 'home'), ('view 상세', '/view/{viewName}.do', 'detail'), ('reservation 캘린더', '/reservation/calendar.do', 'calendar')],
        'side': [('reservation 캘린더', '/reservation/calendar.do', 'calendar'), ('view 상세', '/view/{viewName}.do', 'detail')],
        'entity': 'reservation',
    }
    header = _build_header_jsp(schema_map={'Reservation': schema}, preferred_entity='Reservation', project_title='demo', nav_override=nav_override)
    leftnav = _build_leftnav_jsp(schema_map={'Reservation': schema}, preferred_entity='Reservation', nav_override=nav_override)
    assert '/view/{viewName}.do' not in header
    assert '/view/{viewName}.do' not in leftnav
    assert '/reservation/calendar.do' in header
    assert '/reservation/calendar.do' in leftnav


def test_validator_flags_unresolved_view_route_and_legacy_calendar(tmp_path: Path):
    view_root = tmp_path / 'src/main/webapp/WEB-INF/views'
    (view_root / 'common').mkdir(parents=True, exist_ok=True)
    (view_root / 'reservation').mkdir(parents=True, exist_ok=True)
    (view_root / 'common' / 'header.jsp').write_text('<a href="<c:url value=\'/view/{viewName}.do\' />">bad</a>', encoding='utf-8')
    (view_root / 'reservation' / 'reservationCalendar.jsp').write_text('<script src="${pageContext.request.contextPath}/js/fullcalendar.min.js"></script><script>eventClick:function(){}</script>', encoding='utf-8')
    report = validate_generated_project(tmp_path, SimpleNamespace(frontend_key='jsp'), run_runtime=False)
    codes = {item['code'] for item in report['issues']}
    assert 'jsp_unresolved_route' in codes
    assert 'legacy_calendar_jsp' in codes


def test_prompt_builders_require_shared_shell_and_working_calendar_routes():
    jsp_text = jsp_plan_to_prompt_text({"project_name": "demo", "base_package": "egovframework.demo", "frontend_mode": "jsp", "domains": []})
    react_text = react_plan_to_prompt_text({"project_name": "demo", "frontend_mode": "react", "domains": []})
    vue_text = vue_plan_to_prompt_text({"project_name": "demo", "frontend_mode": "vue", "domains": []})
    assert 'shared project layout' in jsp_text
    assert 'working detail/edit links' in jsp_text
    assert 'shared application shell' in react_text
    assert 'shared application shell' in vue_text
