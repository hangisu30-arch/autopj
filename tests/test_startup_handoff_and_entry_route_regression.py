from pathlib import Path

from app.ui.state import ProjectConfig
from app.validation.post_generation_repair import (
    _run_startup_repair_handoff,
    _startup_runtime_to_static_issues,
    _validate_jsp_asset_consistency,
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_validate_jsp_asset_consistency_accepts_any_discovered_entry_route(tmp_path: Path):
    _write(tmp_path / 'src/main/webapp/css/common.css', 'body {}')
    _write(
        tmp_path / 'src/main/webapp/index.jsp',
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n<% response.sendRedirect(request.getContextPath() + "/signup/list.do"); %>',
    )
    _write(
        tmp_path / 'src/main/resources/static/index.html',
        '<meta http-equiv="refresh" content="0;url=/signup/list.do" /><script>window.location.replace("/signup/list.do");</script>',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java',
        '''package egovframework.test.login.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
@Controller
@RequestMapping("/login")
public class LoginController {
  @GetMapping("/login.do")
  public String loginForm() { return "login/login"; }
}
''',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/signup/web/SignupController.java',
        '''package egovframework.test.signup.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
@Controller
@RequestMapping("/signup")
public class SignupController {
  @GetMapping("/list.do")
  public String list() { return "signup/signupList"; }
}
''',
    )
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupList.jsp', '<div></div>')
    issues = _validate_jsp_asset_consistency(tmp_path, ['src/main/webapp/WEB-INF/views/signup/signupList.jsp'])
    reasons = {item['reason'] for item in issues}
    assert 'index.jsp missing target route' not in reasons
    assert 'static index.html missing target route' not in reasons


def test_startup_runtime_to_static_issues_parses_ambiguous_mapping_log(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/signup/web/SignupController.java',
        'package egovframework.test.signup.web; public class SignupController {}',
    )
    runtime_validation = {
        'compile': {'status': 'ok'},
        'startup': {
            'status': 'failed',
            'log_tail': '''Caused by: java.lang.IllegalStateException: Ambiguous mapping. Cannot map 'signupController' method 
                egovframework.test.signup.web.SignupController#actionLogin(SignupVO, HttpSession, Model)
                to {POST [/login/actionLogin.do || /login/process.do]}: There is already 'loginController' bean method
                egovframework.test.login.web.LoginController#actionLogin(LoginVO, HttpSession, Model) mapped.''',
            'errors': [{'code': 'ambiguous_request_mapping', 'message': 'Spring request mapping conflict detected', 'snippet': 'Ambiguous mapping'}],
        },
    }
    issues = _startup_runtime_to_static_issues(tmp_path, runtime_validation)
    assert issues
    issue = issues[0]
    assert issue['type'] == 'ambiguous_request_mapping'
    assert issue['path'].endswith('signup/web/SignupController.java')
    assert issue['details']['route'] == '/login/actionLogin.do'


def test_run_startup_repair_handoff_rewrites_signup_login_route_conflict(tmp_path: Path, monkeypatch):
    signup = tmp_path / 'src/main/java/egovframework/test/signup/web/SignupController.java'
    _write(
        signup,
        '''package egovframework.test.signup.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
@Controller
@RequestMapping("/login")
public class SignupController {
  @GetMapping("/login.do")
  public String form() { return "login/login"; }
  @PostMapping({"/actionLogin.do", "/process.do"})
  public String actionLogin() { return "redirect:/login/actionMain.do"; }
}
''',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java',
        '''package egovframework.test.login.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
@Controller
@RequestMapping("/login")
public class LoginController {
  @PostMapping({"/actionLogin.do", "/process.do"})
  public String actionLogin() { return "redirect:/login/actionMain.do"; }
}
''',
    )
    _write(tmp_path / 'src/main/webapp/css/common.css', 'body {}')
    cfg = ProjectConfig(project_name='demo', frontend_key='jsp', database_key='sqlite', backend_key='egov_spring')
    runtime_validation = {
        'compile': {'status': 'ok'},
        'startup': {
            'status': 'failed',
            'log_tail': '''Caused by: java.lang.IllegalStateException: Ambiguous mapping. Cannot map 'signupController' method 
                egovframework.test.signup.web.SignupController#actionLogin(SignupVO, HttpSession, Model)
                to {POST [/login/actionLogin.do || /login/process.do]}: There is already 'loginController' bean method
                egovframework.test.login.web.LoginController#actionLogin(LoginVO, HttpSession, Model) mapped.''',
            'errors': [{'code': 'ambiguous_request_mapping', 'message': 'Spring request mapping conflict detected', 'snippet': 'Ambiguous mapping'}],
        },
        'endpoint_smoke': {'status': 'skipped'},
    }

    def fake_runtime(project_root: Path, backend_key: str = '', compile_timeout_seconds: int = 300, startup_timeout_seconds: int = 120):
        return {
            'status': 'ok',
            'compile': {'status': 'ok'},
            'startup': {'status': 'ok', 'errors': []},
            'endpoint_smoke': {'status': 'skipped'},
        }

    monkeypatch.setattr('app.validation.post_generation_repair.run_spring_boot_runtime_validation', fake_runtime)
    after_runtime, round_info = _run_startup_repair_handoff(tmp_path, cfg, [], [], runtime_validation, round_no=1)
    body = signup.read_text(encoding='utf-8')
    assert '@RequestMapping("/signup")' in body
    assert '@PostMapping("/save.do")' in body
    assert 'return "signup/signupForm";' in body
    assert after_runtime['startup']['status'] == 'ok'
    assert round_info and round_info['changed']
