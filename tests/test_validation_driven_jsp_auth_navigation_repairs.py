from pathlib import Path

from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair
from app.validation.post_generation_repair import _sanitize_frontend_ui_file


class _Cfg:
    frontend_key = 'jsp'
    database_key = 'mysql'


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_validator_detects_malformed_jsp_structure_and_auth_nav_mismatch(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java',
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @GetMapping("/login.do") public String loginForm(){ return "login/login"; }\n'
        '  @GetMapping("/integratedCallback.do") public String integrated(){ return "login/login"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/common/header.jsp',
        '<a class="autopj-header__link" href="<c:url value=\'/login/integratedCallback.do\' />">로그인</a>',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/common/leftNav.jsp',
        '<a class="autopj-leftnav__link" href="<c:url value=\'/login/integratedCallback.do\' />">로그인</a>',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/member/memberForm.jsp',
        '<html><head><div>broken</div></head><body></form></body></html>',
    )
    report = validate_generated_project(tmp_path, _Cfg(), include_runtime=False)
    issue_types = {item.get('type') for item in report.get('static_issues') or []}
    assert 'malformed_jsp_structure' in issue_types
    assert 'auth_nav_route_mismatch' in issue_types


def test_auto_repair_rebuilds_broken_crud_and_login_jsp_and_normalizes_nav(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java',
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @GetMapping("/login.do") public String loginForm(){ return "login/login"; }\n'
        '  @GetMapping("/integratedCallback.do") public String integrated(){ return "login/login"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java',
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/member")\n'
        'public class MemberController {\n'
        '  @GetMapping("/list.do") public String list(){ return "member/memberList"; }\n'
        '  @GetMapping("/form.do") public String form(){ return "member/memberForm"; }\n'
        '  @GetMapping("/detail.do") public String detail(){ return "member/memberDetail"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/member/service/vo/MemberVO.java',
        'package egovframework.test.member.service.vo;\n'
        'public class MemberVO {\n'
        '  private String memberId;\n'
        '  private String loginId;\n'
        '  private String memberName;\n'
        '  public String getMemberId(){ return memberId; }\n'
        '  public String getLoginId(){ return loginId; }\n'
        '  public String getMemberName(){ return memberName; }\n'
        '}\n',
    )
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/common/header.jsp', '<a href="<c:url value=\'/login/integratedCallback.do\' />">로그인</a>')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/common/leftNav.jsp', '<a href="<c:url value=\'/login/integratedCallback.do\' />">로그인</a>')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/member/memberForm.jsp', '<html><body></form></body></html>')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/login/login.jsp', '<html><body><button type="submit">로그인</button></form></body></html>')

    validation_report = {
        'issues': [
            {'type': 'auth_nav_route_mismatch', 'path': 'src/main/webapp/WEB-INF/views/common/header.jsp', 'repairable': True, 'details': {'login_route': '/login/login.do'}},
            {'type': 'auth_nav_route_mismatch', 'path': 'src/main/webapp/WEB-INF/views/common/leftNav.jsp', 'repairable': True, 'details': {'login_route': '/login/login.do'}},
            {'type': 'malformed_jsp_structure', 'path': 'src/main/webapp/WEB-INF/views/member/memberForm.jsp', 'repairable': True},
            {'type': 'malformed_jsp_structure', 'path': 'src/main/webapp/WEB-INF/views/login/login.jsp', 'repairable': True},
        ]
    }
    repaired = apply_generated_project_auto_repair(tmp_path, validation_report)
    assert repaired['changed_count'] == 4

    header = (tmp_path / 'src/main/webapp/WEB-INF/views/common/header.jsp').read_text(encoding='utf-8')
    leftnav = (tmp_path / 'src/main/webapp/WEB-INF/views/common/leftNav.jsp').read_text(encoding='utf-8')
    form = (tmp_path / 'src/main/webapp/WEB-INF/views/member/memberForm.jsp').read_text(encoding='utf-8')
    login = (tmp_path / 'src/main/webapp/WEB-INF/views/login/login.jsp').read_text(encoding='utf-8')

    assert '/login/login.do' in header
    assert '/login/integratedCallback.do' not in header
    assert '/login/login.do' in leftnav
    assert '<form' in form and 'name="memberId"' in form
    assert 'type="password"' in login and '/login/actionLogin.do' in login


def test_auth_ui_sanitize_preserves_password_fields(tmp_path: Path):
    login_jsp = tmp_path / 'src/main/webapp/WEB-INF/views/login/login.jsp'
    _write(login_jsp, '<form><input type="text" name="loginId"/><input type="password" name="loginPassword"/></form>')
    changed = _sanitize_frontend_ui_file(login_jsp, 'non-auth UI must not expose auth-sensitive fields such as password/login_password')
    body = login_jsp.read_text(encoding='utf-8')
    assert not changed
    assert 'type="password"' in body
    assert 'loginPassword' in body
