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


def test_jsp_navigation_shell_builds_top_and_left_menu(tmp_path: Path):
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

    assert "/schedule/calendar.do" in header
    assert "autopj-header__nav" in header
    assert "/schedule/list.do" in leftnav
    assert "/schedule/edit.do" in leftnav
    assert "autopj-leftnav" in leftnav
    assert "--autopj-sidebar-width" in common_css
