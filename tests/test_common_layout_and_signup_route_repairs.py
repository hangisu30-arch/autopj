from pathlib import Path

from app.validation.generated_project_validator import _scan_malformed_jsp_structure, _scan_unresolved_jsp_routes
from app.validation.project_auto_repair import _repair_jsp_missing_route_reference, _repair_malformed_jsp_structure


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_common_layout_routes_are_repaired_and_css_partial_created(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java',
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @GetMapping("/login.do") public String form(){ return "login/login"; }\n'
        '  @GetMapping("/logout.do") public String logout(){ return "redirect:/login/login.do"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java',
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/member")\n'
        'public class MemberController {\n'
        '  @GetMapping("/list.do") public String list(){ return "member/memberList"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/common/layout.jsp',
        '<%@ include file="/WEB-INF/views/common/css.jsp" %>\n'
        '<a href="<c:url value=\'/menu\'/>">메뉴</a>\n'
        '<a href="<c:url value=\'/logout\'/>">로그아웃</a>\n',
    )

    issues = _scan_unresolved_jsp_routes(tmp_path)
    layout_issue = next(i for i in issues if i['path'].endswith('common/layout.jsp'))
    assert _repair_jsp_missing_route_reference(tmp_path / layout_issue['path'], layout_issue, tmp_path)

    body = (tmp_path / 'src/main/webapp/WEB-INF/views/common/layout.jsp').read_text(encoding='utf-8')
    assert '/member/list.do' in body
    assert '/login/logout.do' in body
    css_partial = tmp_path / 'src/main/webapp/WEB-INF/views/common/css.jsp'
    assert css_partial.exists()
    assert 'common.css' in css_partial.read_text(encoding='utf-8')


def test_signup_jsp_inside_login_folder_prefers_non_login_save_route(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java',
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @GetMapping("/login.do") public String form(){ return "login/login"; }\n'
        '  @PostMapping("/save.do") public String saveLogin(){ return "redirect:/login/login.do"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java',
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/member")\n'
        'public class MemberController {\n'
        '  @GetMapping("/form.do") public String form(){ return "member/memberForm"; }\n'
        '  @PostMapping("/save.do") public String save(){ return "redirect:/member/form.do"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/login/signup.jsp',
        '<form action="<c:url value=\'/login/save.do\'/>" method="post">\n'
        '  <input type="text" name="loginId"/>\n'
        '  <button type="submit">가입</button>\n'
        '</form>\n',
    )

    signup_rel = 'src/main/webapp/WEB-INF/views/login/signup.jsp'
    signup_issue = {
        'type': 'jsp_missing_route_reference',
        'path': signup_rel,
        'details': {
            'discovered_routes': sorted(['/login/login.do', '/login/save.do', '/member/form.do', '/member/save.do']),
            'missing_routes': ['/login/save.do'],
        },
    }
    assert _repair_jsp_missing_route_reference(tmp_path / signup_rel, signup_issue, tmp_path)

    body = (tmp_path / signup_rel).read_text(encoding='utf-8')
    assert '/member/save.do' in body
    assert '/login/save.do' not in body


def test_signup_form_alias_with_orphan_form_close_is_rewritten_to_safe_signup_form(tmp_path: Path):
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
    _write(
        tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java',
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/member")\n'
        'public class MemberController {\n'
        '  @GetMapping("/form.do") public String form(){ return "member/memberForm"; }\n'
        '  @PostMapping("/save.do") public String save(){ return "redirect:/login/login.do"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupForm.jsp',
        '<%@ include file="/WEB-INF/views/common/header.jsp" %>\n'
        '<div class="page-card">\n'
        '  <button type="submit">가입</button>\n'
        '</form>\n'
        '</div>\n',
    )

    issues = _scan_malformed_jsp_structure(tmp_path)
    issue = next(i for i in issues if i['path'].endswith('signup/signupForm.jsp'))
    assert _repair_malformed_jsp_structure(tmp_path / issue['path'], issue, tmp_path)

    body = (tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupForm.jsp').read_text(encoding='utf-8')
    assert '<form class="autopj-form-card form-card"' in body
    assert '</form>' in body
    assert body.count('<form') == 1
    assert '/member/save.do' in body
    assert 'loginPasswordConfirm' in body
