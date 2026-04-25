from pathlib import Path

from execution_core.builtin_crud import infer_schema_from_file_ops
from app.ui.fallback_builder import build_builtin_fallback_content
from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair
from app.validation.runtime_smoke import parse_backend_log_errors


REQ = """
기존 eGovFramework Spring Boot + JSP + MyBatis 프로젝트에 회원가입 + 회원관리 시스템을 추가해줘.
기존 로그인 기능은 그대로 유지해야 해.
로그인 기능은 새로 만들지 말고 회원가입/회원관리만 추가해줘.
테이블명: users
컬럼 목록:
- user_id
- login_id
- password
- user_name
- email
- phone
- role_cd
- use_yn
- reg_dt
- upd_dt
로그인ID 중복확인
이메일 validation
전화번호 validation
"""


class _Cfg:
    project_name = 'test'
    frontend_key = 'jsp'


def test_infer_schema_keeps_signup_management_as_crud_when_existing_login_is_preserved():
    file_ops = [
        {
            'path': 'src/main/java/egovframework/test/signup/web/SignupController.java',
            'content': REQ,
        },
    ]
    schema = infer_schema_from_file_ops(file_ops, entity='Signup')
    assert schema.entity == 'User'
    assert schema.feature_kind == 'CRUD'


def test_fallback_builder_keeps_signup_controller_out_of_login_namespace_when_existing_login_is_preserved():
    body = build_builtin_fallback_content(
        'src/main/java/egovframework/test/signup/service/impl/SignupServiceImpl.java',
        REQ,
        project_name='test',
    )
    assert 'authenticate(' not in body
    assert 'findByLoginId' not in body
    assert 'selectSignupList' in body or 'selectUserList' in body


def test_validator_detects_ambiguous_request_mapping_between_signup_and_login_controllers(tmp_path: Path):
    login = tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java'
    signup = tmp_path / 'src/main/java/egovframework/test/signup/web/SignupController.java'
    login.parent.mkdir(parents=True, exist_ok=True)
    signup.parent.mkdir(parents=True, exist_ok=True)
    login.write_text(
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.PostMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @PostMapping({"/actionLogin.do", "/process.do"})\n'
        '  public String actionLogin(){ return "login/login"; }\n'
        '}\n',
        encoding='utf-8',
    )
    signup.write_text(
        'package egovframework.test.signup.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.PostMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/login")\n'
        'public class SignupController {\n'
        '  @PostMapping({"/actionLogin.do", "/process.do"})\n'
        '  public String actionLogin(){ return "login/login"; }\n'
        '}\n',
        encoding='utf-8',
    )

    report = validate_generated_project(tmp_path, _Cfg(), include_runtime=False)
    issues = [item for item in report.get('static_issues') or [] if item.get('type') == 'ambiguous_request_mapping']
    assert issues
    assert any(item.get('details', {}).get('route') == '/login/actionLogin.do' for item in issues)


def test_auto_repair_rehomes_signup_controller_out_of_login_namespace(tmp_path: Path):
    login = tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java'
    signup = tmp_path / 'src/main/java/egovframework/test/signup/web/SignupController.java'
    login.parent.mkdir(parents=True, exist_ok=True)
    signup.parent.mkdir(parents=True, exist_ok=True)
    login.write_text(
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.PostMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @PostMapping({"/actionLogin.do", "/process.do"})\n'
        '  public String actionLogin(){ return "login/login"; }\n'
        '}\n',
        encoding='utf-8',
    )
    signup.write_text(
        'package egovframework.test.signup.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.PostMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/login")\n'
        'public class SignupController {\n'
        '  @GetMapping("/login.do")\n'
        '  public String loginForm(){ return "login/login"; }\n'
        '  @PostMapping({"/actionLogin.do", "/process.do"})\n'
        '  public String actionLogin(){ return "login/login"; }\n'
        '}\n',
        encoding='utf-8',
    )
    validation_report = {
        'issues': [
            {
                'code': 'ambiguous_request_mapping',
                'path': 'src/main/java/egovframework/test/signup/web/SignupController.java',
                'repairable': True,
                'details': {
                    'route': '/login/actionLogin.do',
                    'conflicting_path': 'src/main/java/egovframework/test/login/web/LoginController.java',
                },
            }
        ]
    }
    repaired = apply_generated_project_auto_repair(tmp_path, validation_report)
    assert repaired['changed_count'] == 1
    body = signup.read_text(encoding='utf-8')
    assert '@RequestMapping("/signup")' in body
    assert '@PostMapping("/save.do")' in body
    assert '@GetMapping("/form.do")' in body


def test_parse_backend_log_errors_detects_ambiguous_request_mapping():
    log_text = """
    Error starting ApplicationContext.
    Application run failed
    Caused by: java.lang.IllegalStateException: Ambiguous mapping. Cannot map 'signupController' method
    egovframework.test.signup.web.SignupController#actionLogin(SignupVO, HttpSession, Model)
    to {POST [/login/actionLogin.do || /login/process.do]}: There is already 'loginController' bean method
    egovframework.test.login.web.LoginController#actionLogin(LoginVO, HttpSession, Model)
    """
    errors = parse_backend_log_errors(log_text)
    codes = {item['code'] for item in errors}
    assert 'ambiguous_request_mapping' in codes
    assert 'application_run_failed' in codes
    ambiguous = next(item for item in errors if item['code'] == 'ambiguous_request_mapping')
    assert ambiguous.get('path') == 'src/main/java/egovframework/test/signup/web/SignupController.java'
    assert ambiguous.get('conflicting_path') == 'src/main/java/egovframework/test/login/web/LoginController.java'
    assert ambiguous.get('route') == '/login/actionLogin.do'


def test_auto_repair_rehomes_signup_controller_with_absolute_login_routes(tmp_path: Path):
    signup = tmp_path / 'src/main/java/egovframework/test/signup/web/SignupController.java'
    signup.parent.mkdir(parents=True, exist_ok=True)
    signup.write_text(
        'package egovframework.test.signup.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.PostMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping(value = "/login")\n'
        'public class SignupController {\n'
        '  @PostMapping({"/login/actionLogin.do", "/login/process.do"})\n'
        '  public String actionLogin(){ return "login/login"; }\n'
        '}\n',
        encoding='utf-8',
    )
    validation_report = {
        'issues': [
            {
                'code': 'ambiguous_request_mapping',
                'path': 'src/main/java/egovframework/test/signup/web/SignupController.java',
                'repairable': True,
                'details': {
                    'route': '/login/actionLogin.do',
                    'routes': ['/login/actionLogin.do', '/login/process.do'],
                    'conflicting_path': 'src/main/java/egovframework/test/login/web/LoginController.java',
                },
            }
        ]
    }
    repaired = apply_generated_project_auto_repair(tmp_path, validation_report)
    assert repaired['changed_count'] == 1
    body = signup.read_text(encoding='utf-8')
    assert '@RequestMapping("/signup")' in body or '@RequestMapping(value = "/signup")' in body
    assert '@PostMapping("/save.do")' in body
    assert '/login/actionLogin.do' not in body
    assert '/login/process.do' not in body


def test_auto_repair_rehomes_signup_controller_with_absolute_requestmapping_routes(tmp_path: Path):
    signup = tmp_path / 'src/main/java/egovframework/test/signup/web/SignupController.java'
    signup.parent.mkdir(parents=True, exist_ok=True)
    signup.write_text(
        '''package egovframework.test.signup.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;

@Controller
@RequestMapping(path = "/login")
public class SignupController {
  @RequestMapping(value = {"/login/actionLogin.do", "/login/process.do"}, method = RequestMethod.POST)
  public String actionLogin(){ return "login/login"; }
}
''',
        encoding='utf-8',
    )
    validation_report = {
        'issues': [
            {
                'code': 'ambiguous_request_mapping',
                'path': 'src/main/java/egovframework/test/signup/web/SignupController.java',
                'repairable': True,
                'details': {
                    'route': '/login/actionLogin.do',
                    'routes': ['/login/actionLogin.do', '/login/process.do'],
                },
            }
        ]
    }
    repaired = apply_generated_project_auto_repair(tmp_path, validation_report)
    assert repaired['changed_count'] == 1
    body = signup.read_text(encoding='utf-8')
    assert '@RequestMapping(path = "/signup")' in body or '@RequestMapping("/signup")' in body
    assert '@PostMapping("/save.do")' in body
    assert '/login/actionLogin.do' not in body
    assert '/login/process.do' not in body

def test_auto_repair_rehomes_signup_controller_when_route_details_are_missing(tmp_path: Path):
    signup = tmp_path / 'src/main/java/egovframework/test/signup/web/SignupController.java'
    signup.parent.mkdir(parents=True, exist_ok=True)
    signup.write_text(
        'package egovframework.test.signup.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.PostMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/login")\n'
        'public class SignupController {\n'
        '  @PostMapping({"/actionLogin.do", "/process.do"})\n'
        '  public String actionLogin(){ return "login/login"; }\n'
        '}\n',
        encoding='utf-8',
    )
    validation_report = {
        'issues': [
            {
                'code': 'ambiguous_request_mapping',
                'path': 'src/main/java/egovframework/test/signup/web/SignupController.java',
                'repairable': True,
                'details': {
                    'message': 'Spring request mapping conflict detected',
                },
            }
        ]
    }
    repaired = apply_generated_project_auto_repair(tmp_path, validation_report)
    assert repaired['changed_count'] == 1
    body = signup.read_text(encoding='utf-8')
    assert '@RequestMapping("/signup")' in body
    assert '@PostMapping("/save.do")' in body
    assert '/actionLogin.do' not in body
    assert 'login/login' not in body


def test_auto_repair_rehomes_signup_controller_with_mixed_class_requestmapping_values(tmp_path: Path):
    signup = tmp_path / 'src/main/java/egovframework/test/signup/web/SignupController.java'
    signup.parent.mkdir(parents=True, exist_ok=True)
    signup.write_text(
        """package egovframework.test.signup.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;

@Controller
@RequestMapping(value = {"/login", "/join"})
public class SignupController {
  @RequestMapping(path = {"/actionLogin.do", "/process.do"}, method = RequestMethod.POST)
  public String actionLogin(){ return "login/login"; }
}
""",
        encoding='utf-8',
    )
    validation_report = {
        'issues': [
            {
                'code': 'ambiguous_request_mapping',
                'path': 'src/main/java/egovframework/test/signup/web/SignupController.java',
                'repairable': True,
                'details': {
                    'message': 'Spring request mapping conflict detected',
                },
            }
        ]
    }
    repaired = apply_generated_project_auto_repair(tmp_path, validation_report)
    assert repaired['changed_count'] == 1
    body = signup.read_text(encoding='utf-8')
    assert '@RequestMapping("/signup")' in body
    assert '/login' not in body
    assert 'login/login' not in body


def test_auto_repair_rehomes_signup_controller_with_absolute_login_routes_and_missing_details(tmp_path: Path):
    signup = tmp_path / 'src/main/java/egovframework/test/signup/web/SignupController.java'
    signup.parent.mkdir(parents=True, exist_ok=True)
    signup.write_text(
        """package egovframework.test.signup.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;

@Controller
@RequestMapping(path = {"/login", "/register"})
public class SignupController {
  @RequestMapping(value = {"/login/actionLogin.do", "/login/process.do"}, method = RequestMethod.POST)
  public String actionLogin(){ return "login/login"; }
}
""",
        encoding='utf-8',
    )
    validation_report = {
        'issues': [
            {
                'code': 'ambiguous_request_mapping',
                'path': 'src/main/java/egovframework/test/signup/web/SignupController.java',
                'repairable': True,
                'details': {
                    'message': 'Spring request mapping conflict detected',
                },
            }
        ]
    }
    repaired = apply_generated_project_auto_repair(tmp_path, validation_report)
    assert repaired['changed_count'] == 1
    body = signup.read_text(encoding='utf-8')
    assert '@RequestMapping("/signup")' in body
    assert '@PostMapping("/save.do")' in body
    assert '/login/actionLogin.do' not in body
    assert '/login/process.do' not in body
    assert 'login/login' not in body


def test_auto_repair_rewrites_signup_controller_to_minimal_safe_routes_when_login_conflict_persists(tmp_path: Path):
    signup = tmp_path / 'src/main/java/egovframework/test/signup/web/SignupController.java'
    signup.parent.mkdir(parents=True, exist_ok=True)
    signup.write_text(
        """package egovframework.test.signup.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping(LOGIN_BASE)
public class SignupController {
  public String actionLogin(){ return "login/login"; }
}
""",
        encoding='utf-8',
    )
    validation_report = {
        'issues': [
            {
                'code': 'ambiguous_request_mapping',
                'path': 'src/main/java/egovframework/test/signup/web/SignupController.java',
                'repairable': True,
                'details': {
                    'message': 'Spring request mapping conflict detected',
                },
            }
        ]
    }
    repaired = apply_generated_project_auto_repair(tmp_path, validation_report)
    assert repaired['changed_count'] == 1
    body = signup.read_text(encoding='utf-8')
    assert '@RequestMapping("/signup")' in body
    assert '@PostMapping("/save.do")' in body
    assert 'login/login' not in body
    assert 'actionLogin(' not in body
