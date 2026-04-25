from pathlib import Path

from app.validation.project_auto_repair import _repair_jsp_missing_route_reference


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_member_route_missing_reference_rewrites_tbmember_controller_and_signup(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/tbmember/web/TbMemberController.java'
    _write(controller, 'package egovframework.test.tbmember.web;\npublic class TbMemberController {}\n')

    list_jsp = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    _write(
        list_jsp,
        '<a href="<c:url value=\'/member/detail.do\' />">상세</a>'
        '<a href="<c:url value=\'/member/form.do\' />">수정</a>'
        '<form action="<c:url value=\'/member/delete.do\' />"></form>',
    )
    issue = {'details': {'missing_routes': ['/member/detail.do', '/member/form.do', '/member/delete.do'], 'discovered_routes': []}}
    assert _repair_jsp_missing_route_reference(list_jsp, issue, tmp_path) is True
    controller_body = controller.read_text(encoding='utf-8')
    assert '@RequestMapping("/member")' in controller_body
    assert '@GetMapping({"/register.do", "/signup.do", "/form.do"})' in controller_body
    assert '@GetMapping({"/detail.do", "/view.do"})' in controller_body
    assert '@PostMapping({"/actionRegister.do", "/save.do"})' in controller_body
    assert '@PostMapping("/delete.do")' in controller_body

    signup_jsp = tmp_path / 'src/main/webapp/WEB-INF/views/member/signup.jsp'
    _write(signup_jsp, '<form action="<c:url value=\'/member/actionRegister.do\' />"></form><script>fetch("${pageContext.request.contextPath}/member/checkLoginId.do?loginId=")</script>')
    signup_issue = {'details': {'missing_routes': ['/member/actionRegister.do', '/member/checkLoginId.do', '/member/checkLoginId.do?loginId='], 'discovered_routes': []}}
    assert _repair_jsp_missing_route_reference(signup_jsp, signup_issue, tmp_path) is True
    signup_body = signup_jsp.read_text(encoding='utf-8')
    assert '/member/save.do' in signup_body
    assert '/member/checkLoginId.do' in signup_body
    assert '/member/actionRegister.do' not in signup_body
