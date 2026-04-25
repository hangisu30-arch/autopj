from pathlib import Path

from app.io.execution_core_apply import _patch_generated_jsp_assets


class _ScheduleSchema:
    entity_var = "schedule"
    feature_kind = "CRUD"
    routes = {
        "calendar": "/schedule/calendar.do",
        "list": "/schedule/list.do",
        "edit": "/schedule/edit.do",
    }


def test_jsp_common_navigation_assets_include_mobile_support_and_common_js(tmp_path: Path):
    view = tmp_path / "src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp"
    view.parent.mkdir(parents=True, exist_ok=True)
    view.write_text(
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<html><head><meta charset="UTF-8"/></head><body><div>calendar</div></body></html>',
        encoding="utf-8",
    )

    report = _patch_generated_jsp_assets(
        tmp_path,
        ["src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp"],
        "Schedule",
        {"Schedule": _ScheduleSchema()},
    )

    header = (tmp_path / report["header_jsp"]).read_text(encoding="utf-8")
    leftnav = (tmp_path / report["leftnav_jsp"]).read_text(encoding="utf-8")
    common_css = (tmp_path / report["common_css"]).read_text(encoding="utf-8")
    common_js = (tmp_path / report["common_js"]).read_text(encoding="utf-8")
    patched = view.read_text(encoding="utf-8")

    assert "data-autopj-nav-toggle" in header
    assert "href=\"<c:url value='/schedule/calendar.do' />\"" in header
    assert "autopj-nav-overlay" in leftnav
    assert "autopj-leftnav__link is-active" in leftnav
    assert "@media (max-width: 1180px)" in common_css
    assert "body.autopj-nav-open .autopj-leftnav" in common_css
    assert "document.body" in common_js
    assert "/js/common.js" in patched


def test_index_redirect_prefers_main_route_with_js_fallback(tmp_path: Path):
    view = tmp_path / "src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp"
    view.parent.mkdir(parents=True, exist_ok=True)
    view.write_text('<html><body>ok</body></html>', encoding="utf-8")

    report = _patch_generated_jsp_assets(
        tmp_path,
        ["src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp"],
        "Schedule",
        {"Schedule": _ScheduleSchema()},
    )

    index_body = (tmp_path / report["index_jsp"]).read_text(encoding="utf-8")

    assert 'response.sendRedirect' in index_body and '/schedule/calendar.do' in index_body
