from pathlib import Path

from app.validation.project_auto_repair import (
    _repair_jsp_missing_route_reference,
    _rewrite_membership_controller_to_safe_routes,
    _rewrite_signup_jsp_to_safe_routes,
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_adminmember_missing_member_alias_routes_are_normalized_even_when_discovered_routes_are_empty(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java',
        'package egovframework.test.adminMember.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/adminMember")\n'
        'public class AdminMemberController {\n'
        '  @GetMapping("/list.do") public String list(){ return "adminMember/adminMemberList"; }\n'
        '  @GetMapping("/detail.do") public String detail(){ return "adminMember/adminMemberDetail"; }\n'
        '  @GetMapping("/form.do") public String form(){ return "adminMember/adminMemberForm"; }\n'
        '  @PostMapping("/save.do") public String save(){ return "redirect:/adminMember/list.do"; }\n'
        '  @PostMapping("/delete.do") public String delete(){ return "redirect:/adminMember/list.do"; }\n'
        '}\n',
    )
    samples = {
        'adminMemberList.jsp': '<a href="<c:url value=\'/member/detail.do\' />">상세</a><a href="<c:url value=\'/member/form.do\' />">수정</a><form action="<c:url value=\'/member/delete.do\' />"></form>',
        'adminMemberForm.jsp': '<form action="<c:url value=\'/member/save.do\' />"></form><a href="<c:url value=\'/member/list.do\' />">목록</a><form action="<c:url value=\'/member/delete.do\' />"></form>',
    }
    for name, body in samples.items():
        jsp = tmp_path / 'src/main/webapp/WEB-INF/views/adminMember' / name
        _write(jsp, body)
        issue = {'details': {'missing_routes': ['/member/detail.do', '/member/form.do', '/member/delete.do', '/member/save.do', '/member/list.do'], 'discovered_routes': []}}
        assert _repair_jsp_missing_route_reference(jsp, issue, tmp_path)
        rewritten = jsp.read_text(encoding='utf-8')
        assert '/adminMember/' in rewritten
        assert '/member/detail.do' not in rewritten
        assert '/member/form.do' not in rewritten
        assert '/member/save.do' not in rewritten
        assert '/member/delete.do' not in rewritten


def test_signup_rewrite_prefers_non_login_check_route_and_replaces_action_register_alias(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java',
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/member")\n'
        'public class MemberController {\n'
        '  @PostMapping("/save.do") public String save(){ return "redirect:/member/list.do"; }\n'
        '  @GetMapping("/checkLoginId.do") @ResponseBody public String check(){ return "true"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java',
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @GetMapping("/login.do") public String login(){ return "login/login"; }\n'
        '}\n',
    )
    _write(tmp_path / 'src/main/resources/schema.sql', 'CREATE TABLE tb_member (login_id VARCHAR(50), login_password VARCHAR(100), member_name VARCHAR(100));\n')
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/login/signup.jsp'
    _write(jsp, '<form action="<c:url value=\'/member/actionRegister.do\' />"></form><script>fetch("${pageContext.request.contextPath}/member/checkLoginId.do?loginId=")</script>')
    assert _rewrite_signup_jsp_to_safe_routes(jsp, tmp_path)
    body = jsp.read_text(encoding='utf-8')
    assert '/member/save.do' in body
    assert '/member/checkLoginId.do' in body
    assert '/member/actionRegister.do' not in body


def test_membership_safe_controller_uses_member_id_and_post_delete(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java'
    _write(controller, 'package egovframework.test.member.web;\npublic class MemberController {}\n')
    assert _rewrite_membership_controller_to_safe_routes(controller, 'member')
    body = controller.read_text(encoding='utf-8')
    assert '@PostMapping("/delete.do")' in body
    assert '@RequestParam(value = "memberId", required = false) String memberId' in body
    assert 'redirect:/member/list.do' in body
