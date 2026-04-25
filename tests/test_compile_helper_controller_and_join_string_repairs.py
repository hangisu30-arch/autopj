from pathlib import Path
from types import SimpleNamespace

from app.validation.backend_compile_repair import _normalize_problematic_java_string_literals
from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def _cfg(**kwargs):
    base = dict(frontend_key='jsp', backend_key='springboot', project_name='demo', auth_cert_login=False, auth_jwt_login=False, auth_unified_auth=False)
    base.update(kwargs)
    return SimpleNamespace(**base)



def test_missing_view_on_auth_helper_controller_rewrites_controller_not_placeholder_views(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/web/CertLoginController.java',
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n'
        '@RequestMapping("/login")\n'
        'public class CertLoginController {\n'
        '  @GetMapping("/certLogin.do") public String form(){ return "login/loginForm"; }\n'
        '  @GetMapping("/detail.do") public String detail(){ return "login/loginDetail"; }\n'
        '  @GetMapping("/list.do") public String list(){ return "login/loginList"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/login/certLogin.jsp',
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n<html><body>cert</body></html>',
    )

    report = validate_generated_project(tmp_path, _cfg(auth_cert_login=True), include_runtime=False)
    missing = [i for i in report.get('static_issues', []) if (i.get('type') or i.get('code')) == 'missing_view']
    assert missing

    repaired = apply_generated_project_auto_repair(tmp_path, report)
    assert repaired['changed_count'] >= 1

    body = (tmp_path / 'src/main/java/egovframework/test/login/web/CertLoginController.java').read_text(encoding='utf-8')
    assert 'login/certLogin' in body
    assert 'login/loginForm' not in body
    assert 'login/loginDetail' not in body
    assert 'login/loginList' not in body
    assert not (tmp_path / 'src/main/webapp/WEB-INF/views/login/loginForm.jsp').exists()



def test_route_param_mismatch_repair_uses_explicit_jsp_paths(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/memberAdmin/web/MemberAdminController.java',
        'package egovframework.test.memberAdmin.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        'import org.springframework.web.bind.annotation.RequestParam;\n'
        '@Controller\n'
        '@RequestMapping("/memberAdmin")\n'
        'public class MemberAdminController {\n'
        '  @GetMapping("/detail.do") public String detail(@RequestParam("memberId") String memberId){ return "memberAdmin/memberAdminDetail"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/memberAdmin/memberAdminList.jsp',
        '<a href="<c:url value=\'/memberAdmin/detail.do\'/>?userId=${row.userId}">상세</a>',
    )

    report = validate_generated_project(tmp_path, _cfg(), include_runtime=False)
    mismatches = [i for i in report.get('issues', []) if (i.get('type') or i.get('code')) == 'route_param_mismatch']
    assert mismatches

    repaired = apply_generated_project_auto_repair(tmp_path, report)
    assert repaired['changed_count'] >= 1

    body = (tmp_path / 'src/main/webapp/WEB-INF/views/memberAdmin/memberAdminList.jsp').read_text(encoding='utf-8')
    assert '?memberId=' in body
    assert '?userId=' not in body



def test_normalize_problematic_java_string_literals_converts_multichar_single_quotes():
    body = '''
@Controller
@RequestMapping('/join')
public class JoinController {
    @GetMapping('/form.do')
    public String form(HttpSession session, Model model) {
        model.addAttribute('loginMessage', '관리자 승인 후 로그인할 수 있습니다.');
        session.getAttribute('loginVO');
        result.put('message', 'ok');
        return 'redirect:/join/form.do';
    }
}
'''
    fixed = _normalize_problematic_java_string_literals(body)

    assert '@RequestMapping("/join")' in fixed
    assert '@GetMapping("/form.do")' in fixed
    assert 'model.addAttribute("loginMessage",' in fixed
    assert 'session.getAttribute("loginVO")' in fixed
    assert '.put("message",' in fixed
    assert 'return "redirect:/join/form.do";' in fixed
