from pathlib import Path

from app.validation.project_auto_repair import _repair_jsp_missing_route_reference, _rewrite_signup_jsp_to_safe_routes


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_adminmember_list_prefers_adminmember_routes_over_member_routes(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/adminMember/adminMemberList.jsp'
    _write(
        jsp,
        '<a href="<c:url value="/member/detail.do"/>">상세</a>'
        '<a href="<c:url value="/member/form.do"/>">등록</a>'
        '<a href="<c:url value="/member/delete.do"/>">삭제</a>',
    )
    changed = _repair_jsp_missing_route_reference(
        jsp,
        issue={
            'details': {
                'missing_routes': ['/member/delete.do', '/member/detail.do', '/member/form.do'],
                'discovered_routes': [
                    '/member/list.do',
                    '/member/detail.do',
                    '/adminMember/list.do',
                    '/adminMember/detail.do',
                    '/adminMember/form.do',
                    '/adminMember/delete.do',
                ],
            }
        },
        project_root=tmp_path,
    )

    assert changed is True
    body = jsp.read_text(encoding='utf-8')
    assert '/adminMember/detail.do' in body
    assert '/adminMember/form.do' in body
    assert '/adminMember/delete.do' in body
    assert '/member/detail.do' not in body
    assert '/member/form.do' not in body
    assert '/member/delete.do' not in body


def test_index_view_with_member_route_mismatch_rewrites_to_entry_redirect(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java',
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @GetMapping("/login.do") public String form(){ return "login/login"; }\n'
        '}\n',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/index/indexForm.jsp'
    _write(jsp, '<a href="<c:url value="/member/list.do"/>">목록</a>')

    changed = _repair_jsp_missing_route_reference(
        jsp,
        issue={
            'details': {
                'missing_routes': ['/member/list.do'],
                'discovered_routes': ['/login/login.do'],
            }
        },
        project_root=tmp_path,
    )
    assert changed is True
    body = jsp.read_text(encoding='utf-8')
    assert '진입 전용 화면' in body
    assert '/login/login.do' in body
    assert '/member/list.do' not in body


def test_login_folder_signup_prefers_member_routes_for_save_and_id_check(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java',
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/member")\n'
        'public class MemberController {\n'
        '  @GetMapping("/checkLoginId.do") public String check(){ return null; }\n'
        '  @PostMapping("/save.do") public String save(){ return "redirect:/login/login.do"; }\n'
        '}\n',
    )
    signup = tmp_path / 'src/main/webapp/WEB-INF/views/login/signup.jsp'
    _write(signup, '<html><body>broken</body></html>')

    assert _rewrite_signup_jsp_to_safe_routes(signup, tmp_path) is True
    body = signup.read_text(encoding='utf-8')
    assert '/member/save.do' in body
    assert '/member/checkLoginId.do' in body
    assert '/login/save.do' not in body
