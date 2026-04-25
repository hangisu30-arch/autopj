from pathlib import Path
from app.validation.project_auto_repair import _repair_auth_nav_route_mismatch


def test_auth_nav_rewrites_existing_login_anchor_route(tmp_path: Path):
    root = tmp_path
    nav = root / "src/main/webapp/WEB-INF/views/common/header.jsp"
    nav.parent.mkdir(parents=True, exist_ok=True)
    nav.write_text("""
<ul>
  <li><a class="nav-link" href="<c:url value='/wrong/login.do' />">로그인</a></li>
  <li><a class="nav-link" href="<c:url value='/member/register.do' />">회원가입</a></li>
</ul>
""", encoding="utf-8")

    issue = {"details": {"login_route": "/login/login.do", "signup_route": "/member/register.do"}}
    assert _repair_auth_nav_route_mismatch(nav, issue, root) is True
    body = nav.read_text(encoding="utf-8")
    assert "/login/login.do" in body
    assert "/wrong/login.do" not in body
    assert body.count("로그인") == 1
