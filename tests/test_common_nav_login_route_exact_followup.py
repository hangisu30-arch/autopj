from pathlib import Path

from app.validation.project_auto_repair import apply_generated_project_auto_repair


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_auth_nav_rewrites_admin_member_login_link_to_login_controller(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java',
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @GetMapping("/login.do") public String form(){ return "login/login"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/common/header.jsp',
        '<a href="<c:url value=\'/adminMember/checkLoginId.do\' />">로그인</a>',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/common/leftNav.jsp',
        '<a href="<c:url value=\'/adminMember/checkLoginId.do\' />">로그인</a>',
    )

    report = {
        'issues': [
            {'type': 'auth_nav_route_mismatch', 'path': 'src/main/webapp/WEB-INF/views/common/header.jsp', 'repairable': True, 'details': {'login_route': '/login/login.do'}},
            {'type': 'auth_nav_route_mismatch', 'path': 'src/main/webapp/WEB-INF/views/common/leftNav.jsp', 'repairable': True, 'details': {'login_route': '/login/login.do'}},
        ]
    }
    repaired = apply_generated_project_auto_repair(tmp_path, report)
    assert repaired['changed_count'] == 2
    header = (tmp_path / 'src/main/webapp/WEB-INF/views/common/header.jsp').read_text(encoding='utf-8')
    leftnav = (tmp_path / 'src/main/webapp/WEB-INF/views/common/leftNav.jsp').read_text(encoding='utf-8')
    assert '/login/login.do' in header
    assert '/adminMember/checkLoginId.do' not in header
    assert '/login/login.do' in leftnav
    assert '/adminMember/checkLoginId.do' not in leftnav
