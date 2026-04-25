from pathlib import Path

from app.validation.project_auto_repair import _repair_auth_nav_route_mismatch


def test_auth_nav_repair_uses_issue_route_contracts_without_domain_hardcoding(tmp_path: Path):
    root = tmp_path
    header = root / "src/main/webapp/WEB-INF/views/common/header.jsp"
    header.parent.mkdir(parents=True, exist_ok=True)
    header.write_text(
        '<nav><ul><li><a href="/adminMember/checkLoginId.do">로그인</a></li></ul></nav>',
        encoding="utf-8",
    )

    changed = _repair_auth_nav_route_mismatch(
        header,
        {"details": {"login_route": "/login/login.do", "signup_route": "/member/register.do"}},
        root,
    )

    body = header.read_text(encoding="utf-8")
    assert changed is True
    assert "/login/login.do" in body
    assert "/member/register.do" in body
    assert "로그인" in body
    assert "회원가입" in body


def test_auth_nav_repair_appends_labeled_signup_even_when_route_contract_changes(tmp_path: Path):
    root = tmp_path
    left_nav = root / "src/main/webapp/WEB-INF/views/common/leftNav.jsp"
    left_nav.parent.mkdir(parents=True, exist_ok=True)
    left_nav.write_text('<aside><a href="/login/login.do">로그인</a></aside>', encoding="utf-8")

    changed = _repair_auth_nav_route_mismatch(
        left_nav,
        {"details": {"login_route": "/login/login.do", "signup_route": "/member/register.do"}},
        root,
    )

    body = left_nav.read_text(encoding="utf-8")
    assert changed is True
    assert "/login/login.do" in body
    assert "/member/register.do" in body
    assert "회원가입" in body
