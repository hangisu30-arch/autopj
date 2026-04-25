from pathlib import Path
from types import SimpleNamespace

from app.ui.fallback_builder import build_builtin_fallback_content
from app.ui.ui_sanitize_common import sanitize_frontend_ui_text
from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import (
    _repair_jsp_missing_route_reference,
    _repair_unexpected_calendar_artifact,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _cfg():
    return SimpleNamespace(frontend_key="jsp", backend_key="springboot", project_name="demo")


def test_fallback_builder_does_not_emit_member_calendar_jsp() -> None:
    built = build_builtin_fallback_content(
        "src/main/webapp/WEB-INF/views/member/memberCalendar.jsp",
        "로그인 + 회원가입 + 회원관리 시스템, calendar 없음",
        project_name="demo",
    )
    assert built == ""


def test_ui_sanitize_removes_repeat2_placeholder_refs() -> None:
    raw = "<div>${item.repeat2}</div>\n<div>${item.memberName}</div>\n"
    cleaned = sanitize_frontend_ui_text(
        "src/main/webapp/WEB-INF/views/member/memberDetail.jsp",
        raw,
        "jsp references undefined VO properties: repeat2",
    )
    assert "repeat2" not in cleaned
    assert "memberName" in cleaned


def test_validator_flags_forbidden_member_calendar_artifact(tmp_path: Path) -> None:
    _write(tmp_path / "src/main/webapp/WEB-INF/views/member/memberCalendar.jsp", "<html><body>bad</body></html>")
    report = validate_generated_project(tmp_path, _cfg(), include_runtime=False)
    messages = [item["message"] for item in report["static_issues"]]
    assert any("calendar artifact must not exist for member" in msg for msg in messages)


def test_repair_deletes_forbidden_calendar_on_route_issue(tmp_path: Path) -> None:
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/member/memberCalendar.jsp"
    _write(jsp, "<a href=\"<c:url value='/member/view.do'/>\">상세</a>")
    changed = _repair_jsp_missing_route_reference(
        jsp,
        {
            "details": {
                "missing_routes": ["/member/view.do"],
                "discovered_routes": ["/member/list.do", "/member/detail.do"],
            }
        },
        tmp_path,
    )
    assert changed is True
    assert not jsp.exists()


def test_repair_deletes_forbidden_calendar_direct_issue(tmp_path: Path) -> None:
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/views/viewsCalendar.jsp"
    _write(jsp, "<html><body>bad</body></html>")
    changed = _repair_unexpected_calendar_artifact(jsp, {"details": {"domain": "views"}}, tmp_path)
    assert changed is True
    assert not jsp.exists()
