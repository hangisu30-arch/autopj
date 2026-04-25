from pathlib import Path

from app.io.execution_core_apply import _patch_generated_jsp_assets, _pick_main_route_from_schema_map


class _Schema:
    entity_var = 'schedule'
    feature_kind = 'CRUD'
    routes = {
        'list': '/schedule/list.do',
        'calendar': '/schedule/calendar.do',
        'detail': '/schedule/view.do',
    }


def test_pick_main_route_prefers_calendar_even_when_feature_kind_is_crud():
    picked = _pick_main_route_from_schema_map({'Schedule': _Schema()})
    assert picked == '/schedule/calendar.do'


def test_schedule_calendar_jsp_is_normalized_and_receives_assets(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<%@ page language="java" contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<html><head><title>scheduleCalendar</title><style>.calendar-grid{display:grid;}</style></head>'
        '<body><button onclick="prevMonth()">Previous Month</button><span>Event Title</span></body></html>',
        encoding='utf-8',
    )

    report = _patch_generated_jsp_assets(
        tmp_path,
        ['src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'],
        'Schedule',
        {'Schedule': _Schema()},
    )

    body = jsp.read_text(encoding='utf-8')
    assert report['index_jsp'].endswith('src/main/webapp/index.jsp')
    assert 'response.sendRedirect' in (tmp_path / report['index_jsp']).read_text(encoding='utf-8') and '/schedule/calendar.do' in (tmp_path / report['index_jsp']).read_text(encoding='utf-8')
    assert (tmp_path / report['static_index_html']).exists()
    assert 'common/leftNav.jsp' in body
    header_body = (tmp_path / report['header_jsp']).read_text(encoding='utf-8')
    assert '/css/common.css' in header_body
    assert '/css/schedule.css' in header_body
    assert '/js/schedule.js' in body
    assert 'data-autopj-schedule-page' in body
    assert 'onclick="prevMonth()"' not in body
    assert 'Event Title' not in body
    assert (tmp_path / report['schedule_css']).exists()
    assert (tmp_path / report['schedule_js']).exists()
    assert (tmp_path / report['leftnav_jsp']).exists()
