from pathlib import Path

from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair


class _Cfg:
    project_name = 'test'
    frontend_key = 'jsp'


def test_validator_detects_same_controller_duplicate_request_mapping(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/member")\n'
        'public class MemberController {\n'
        '  @GetMapping("/register.do")\n'
        '  public String registerForm(){ return "member/register"; }\n'
        '  @GetMapping("/register.do")\n'
        '  public String registerFormDuplicate(){ return "member/register"; }\n'
        '}\n',
        encoding='utf-8',
    )

    report = validate_generated_project(tmp_path, _Cfg(), include_runtime=False)
    issues = [item for item in report.get('static_issues') or [] if item.get('type') == 'ambiguous_request_mapping']
    assert issues
    assert any(item.get('details', {}).get('route') == '/member/register.do' for item in issues)


def test_auto_repair_rewrites_member_controller_out_of_login_namespace(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.PostMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/login")\n'
        'public class MemberController {\n'
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
                'path': 'src/main/java/egovframework/test/member/web/MemberController.java',
                'message': 'Spring request mapping conflict detected',
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
    body = controller.read_text(encoding='utf-8')
    assert '@RequestMapping("/member")' in body
    assert '@GetMapping({"/register.do", "/signup.do", "/join.do", "/form.do"})' in body or '@GetMapping({"/register.do", "/form.do"})' in body
    assert '@GetMapping("/checkLoginId.do")' in body
    assert '@PostMapping({"/actionRegister.do", "/save.do"})' in body
    assert '/login/actionLogin.do' not in body
    assert '/login/process.do' not in body
