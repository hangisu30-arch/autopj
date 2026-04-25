from pathlib import Path

from app.validation.project_auto_repair import apply_generated_project_auto_repair


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_auth_nav_route_mismatch_appends_exact_login_and_signup_routes(tmp_path: Path):
    _write(
        tmp_path / "src/main/webapp/WEB-INF/views/common/header.jsp",
        "<div class=\"autopj-header\"><nav class=\"autopj-header__nav\"><a class=\"autopj-header__link\" href=\"<c:url value='/login/login.do' />\">로그인</a></nav></div>",
    )
    _write(
        tmp_path / "src/main/webapp/WEB-INF/views/common/leftNav.jsp",
        "<aside><ul class=\"autopj-leftnav__menu\"><li><a class=\"autopj-leftnav__link\" href=\"<c:url value='/login/login.do' />\"><span>로그인</span></a></li></ul></aside>",
    )

    report = {
        "issues": [
            {
                "type": "auth_nav_route_mismatch",
                "path": "src/main/webapp/WEB-INF/views/common/header.jsp",
                "repairable": True,
                "details": {"login_route": "/adminMember/checkLoginId.do", "signup_route": "/adminMember/register.do"},
            },
            {
                "type": "auth_nav_route_mismatch",
                "path": "src/main/webapp/WEB-INF/views/common/leftNav.jsp",
                "repairable": True,
                "details": {"login_route": "/adminMember/checkLoginId.do", "signup_route": "/adminMember/register.do"},
            },
        ]
    }

    result = apply_generated_project_auto_repair(tmp_path, report)
    assert result.get("changed")

    header = (tmp_path / "src/main/webapp/WEB-INF/views/common/header.jsp").read_text(encoding="utf-8")
    leftnav = (tmp_path / "src/main/webapp/WEB-INF/views/common/leftNav.jsp").read_text(encoding="utf-8")

    assert "/adminMember/checkLoginId.do" in header
    assert "/adminMember/register.do" in header
    assert "/adminMember/checkLoginId.do" in leftnav
    assert "/adminMember/register.do" in leftnav
