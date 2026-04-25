from pathlib import Path

from app.validation.project_auto_repair import _read_text, _repair_jsp_missing_route_reference


def test_read_text_returns_empty_string_for_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "src/main/webapp/WEB-INF/views/adminMember/adminMemberCalendar.jsp"
    assert _read_text(missing) == ""


def test_missing_route_repair_returns_cleanly_after_calendar_delete(tmp_path: Path) -> None:
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/adminMember/adminMemberCalendar.jsp"
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text("<a href=\"/adminMember/view.do\">x</a>", encoding="utf-8")

    changed = _repair_jsp_missing_route_reference(
        jsp,
        {
            "details": {
                "missing_routes": ["/adminMember/view.do"],
                "discovered_routes": ["/adminMember/list.do", "/adminMember/detail.do"],
            }
        },
        tmp_path,
    )

    assert changed is True
    assert not jsp.exists()
