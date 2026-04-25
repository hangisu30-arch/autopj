from pathlib import Path

from app.validation.project_auto_repair import _repair_jsp_missing_route_reference, _rewrite_signup_jsp_to_safe_routes


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_adminmember_jsp_prefers_adminmember_routes_over_member_routes(tmp_path: Path):
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
        '  @PostMapping("/delete.do") public String delete(){ return "redirect:/adminMember/list.do"; }\n'
        '}\n',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/adminMember/adminMemberList.jsp'
    _write(
        jsp,
        '<a href="<c:url value=\'/member/delete.do\'/>">삭제</a>'
        '<a href="<c:url value=\'/member/detail.do\'/>">상세</a>'
        '<a href="<c:url value=\'/member/form.do\'/>">수정</a>',
    )
    issue = {
        'details': {
            'missing_routes': ['/member/delete.do', '/member/detail.do', '/member/form.do'],
            'discovered_routes': [],
        }
    }
    assert _repair_jsp_missing_route_reference(jsp, issue, tmp_path)
    body = jsp.read_text(encoding='utf-8')
    assert '/adminMember/delete.do' in body
    assert '/adminMember/detail.do' in body
    assert '/adminMember/form.do' in body
    assert '/member/delete.do' not in body


def test_entry_index_view_with_member_crud_refs_becomes_redirect_page(tmp_path: Path):
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
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/index/indexList.jsp'
    _write(jsp, '<a href="<c:url value=\'/member/list.do\'/>">목록</a>')
    issue = {'details': {'missing_routes': ['/member/list.do'], 'discovered_routes': []}}
    assert _repair_jsp_missing_route_reference(jsp, issue, tmp_path)
    body = jsp.read_text(encoding='utf-8')
    assert '진입 전용 화면' in body
    assert '/login/login.do' in body
    assert '/member/list.do' not in body


def test_signup_rewrite_uses_real_member_save_and_check_routes(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java',
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/member")\n'
        'public class MemberController {\n'
        '  @PostMapping("/save.do") public String save(){ return "redirect:/login/login.do"; }\n'
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
    _write(
        tmp_path / 'src/main/resources/schema.sql',
        'CREATE TABLE tb_member (\n'
        '  login_id VARCHAR(50),\n'
        '  password VARCHAR(100),\n'
        '  member_name VARCHAR(100),\n'
        '  email VARCHAR(100)\n'
        ');\n',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/login/signup.jsp'
    _write(jsp, '<form action="<c:url value=\'/member/actionRegister.do\'/>"></form>')
    assert _rewrite_signup_jsp_to_safe_routes(jsp, tmp_path)
    body = jsp.read_text(encoding='utf-8')
    assert '/member/save.do' in body
    assert '/member/checkLoginId.do' in body
    assert '/member/actionRegister.do' not in body
