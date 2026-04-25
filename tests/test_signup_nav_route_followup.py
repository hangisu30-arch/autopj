from pathlib import Path

from app.validation.project_auto_repair import _repair_auth_nav_route_mismatch, _repair_jsp_vo_property_mismatch


def test_auth_nav_route_mismatch_keeps_distinct_login_and_signup_routes(tmp_path: Path):
    project_root = tmp_path
    target = project_root / 'src/main/webapp/WEB-INF/views/common/header.jsp'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        """
<ul>
  <li><a href="<c:url value='/member/login.do' />">로그인</a></li>
  <li><a href="<c:url value='/member/signup.do' />">회원가입</a></li>
</ul>
""".strip(),
        encoding='utf-8',
    )
    issue = {
        'details': {
            'login_route': '/adminMember/checkLoginId.do',
            'signup_route': '/adminMember/register.do',
        }
    }
    assert _repair_auth_nav_route_mismatch(target, issue, project_root) is True
    body = target.read_text(encoding='utf-8')
    assert "/adminMember/checkLoginId.do" in body
    assert "/adminMember/register.do" in body
    assert body.count('/adminMember/checkLoginId.do') == 1
    assert body.count('/adminMember/register.do') == 1


def test_signup_jsp_vo_property_mismatch_rewrites_id_to_member_id(tmp_path: Path):
    project_root = tmp_path
    jsp = project_root / 'src/main/webapp/WEB-INF/views/member/signup.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        """
<form action="<c:url value='/member/save.do' />" method="post">
  <input type="hidden" name="memberId" value="${member.id}"/>
  <input type="text" name="loginId" value="${member.loginId}"/>
</form>
""".strip(),
        encoding='utf-8',
    )
    issue = {
        'details': {
            'missing_props': ['id'],
            'available_props': ['memberId', 'loginId', 'approvalStatus', 'useYn'],
            'mapper_props': ['memberId', 'loginId'],
            'missing_props_by_var': {'member': ['id']},
        }
    }
    assert _repair_jsp_vo_property_mismatch(jsp, issue, project_root) is True
    body = jsp.read_text(encoding='utf-8')
    assert '${member.memberId}' in body
    assert '${member.id}' not in body
