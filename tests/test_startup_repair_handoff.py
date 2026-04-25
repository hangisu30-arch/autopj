from pathlib import Path

from app.ui.post_validation_logging import post_validation_diagnostic_lines
from app.ui.state import ProjectConfig
from app.validation.post_generation_repair import validate_and_repair_generated_files


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_post_generation_repair_handoffs_compile_success_to_startup_repair(tmp_path: Path, monkeypatch):
    login_rel = 'src/main/java/egovframework/test/login/web/LoginController.java'
    signup_rel = 'src/main/java/egovframework/test/signup/web/SignupController.java'
    _write(
        tmp_path / login_rel,
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.PostMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @PostMapping({"/actionLogin.do", "/process.do"})\n'
        '  public String actionLogin(){ return "login/login"; }\n'
        '}\n',
    )
    _write(
        tmp_path / signup_rel,
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
    )
    _write(tmp_path / 'pom.xml', '<project/>\n')
    _write(tmp_path / 'mvnw', '#!/bin/sh\n')
    _write(tmp_path / 'mvnw.cmd', '@echo off\n')

    cfg = ProjectConfig(project_name='demo', frontend_key='jsp', database_key='sqlite', backend_key='egov_spring')
    report = {'created': [login_rel, signup_rel], 'overwritten': [], 'errors': [], 'patched': {}}
    file_ops = [
        {'path': login_rel, 'purpose': 'controller', 'content': 'spec text'},
        {'path': signup_rel, 'purpose': 'controller', 'content': 'spec text'},
    ]

    calls = {'count': 0}

    def fake_runtime(project_root: Path, backend_key: str = '', compile_timeout_seconds: int = 300, startup_timeout_seconds: int = 120):
        calls['count'] += 1
        if calls['count'] == 1:
            return {
                'ok': False,
                'status': 'failed',
                'compile': {'status': 'ok', 'errors': []},
                'startup': {
                    'status': 'failed',
                    'errors': [{
                        'code': 'ambiguous_request_mapping',
                        'message': 'Spring request mapping conflict detected',
                        'snippet': 'Ambiguous mapping',
                        'path': signup_rel,
                        'route': '/login/actionLogin.do',
                        'routes': ['/login/actionLogin.do', '/login/process.do'],
                        'conflicting_path': login_rel,
                    }],
                },
                'endpoint_smoke': {'status': 'skipped', 'results': []},
            }
        return {
            'ok': True,
            'status': 'ok',
            'compile': {'status': 'ok', 'errors': []},
            'startup': {'status': 'ok', 'errors': []},
            'endpoint_smoke': {'status': 'ok', 'results': [{'route': '/login/login.do', 'status_code': 200, 'ok': True}]},
        }

    monkeypatch.setattr('app.validation.post_generation_repair.run_spring_boot_runtime_validation', fake_runtime)
    monkeypatch.setattr('app.validation.post_generation_repair._validate_paths', lambda root, rel_paths, frontend_key='': [])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_controller_jsp_consistency', lambda root: [])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_jsp_include_consistency', lambda root, rel_paths: [])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_jsp_asset_consistency', lambda root, rel_paths: [])
    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_content', lambda rel, body, frontend_key='': (True, ''))
    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_project', lambda *args, **kwargs: {'ok': True, 'static_issue_count': 0, 'static_issues': []})

    result = validate_and_repair_generated_files(
        project_root=tmp_path,
        cfg=cfg,
        report=report,
        file_ops=file_ops,
        regenerate_callback=None,
        use_execution_core=False,
        max_regen_attempts=0,
    )

    startup_rounds = result.get('startup_repair_rounds') or []
    assert startup_rounds
    assert startup_rounds[0]['before']['startup_status'] == 'failed'
    assert startup_rounds[0]['after']['startup_status'] == 'ok'
    signup_controller = next(tmp_path.rglob('SignupController.java'))
    body = signup_controller.read_text(encoding='utf-8')
    assert '@RequestMapping("/signup")' in body
    assert '@PostMapping("/save.do")' in body
    assert '@GetMapping("/form.do")' in body




def test_post_generation_repair_handoff_stops_after_unchanged_startup_round(tmp_path: Path, monkeypatch):
    signup_rel = 'src/main/java/egovframework/test/signup/web/SignupController.java'
    _write(
        tmp_path / signup_rel,
        '''package egovframework.test.signup.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;

@Controller
@RequestMapping("/login")
public class SignupController {
  @RequestMapping(value = {"/actionLogin.do", "/process.do"}, method = RequestMethod.POST)
  public String actionLogin(){ return "login/login"; }
}
''',
    )
    _write(tmp_path / 'pom.xml', '<project/>\n')
    _write(tmp_path / 'mvnw', '#!/bin/sh\n')
    _write(tmp_path / 'mvnw.cmd', '@echo off\n')

    cfg = ProjectConfig(project_name='demo', frontend_key='jsp', database_key='sqlite', backend_key='egov_spring')
    report = {'created': [signup_rel], 'overwritten': [], 'errors': [], 'patched': {}}
    file_ops = [{'path': signup_rel, 'purpose': 'controller', 'content': 'spec text'}]

    def fake_runtime(project_root: Path, backend_key: str = '', compile_timeout_seconds: int = 300, startup_timeout_seconds: int = 120):
        return {
            'ok': False,
            'status': 'failed',
            'compile': {'status': 'ok', 'errors': []},
            'startup': {
                'status': 'failed',
                'errors': [{
                    'code': 'ambiguous_request_mapping',
                    'message': 'Spring request mapping conflict detected',
                    'snippet': 'Ambiguous mapping',
                    'path': signup_rel,
                    'route': '/login/actionLogin.do',
                    'routes': ['/login/actionLogin.do', '/login/process.do'],
                }],
            },
            'endpoint_smoke': {'status': 'skipped', 'results': []},
        }

    monkeypatch.setattr('app.validation.post_generation_repair.run_spring_boot_runtime_validation', fake_runtime)
    monkeypatch.setattr('app.validation.post_generation_repair._validate_paths', lambda root, rel_paths, frontend_key='': [])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_controller_jsp_consistency', lambda root: [])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_jsp_include_consistency', lambda root, rel_paths: [])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_jsp_asset_consistency', lambda root, rel_paths: [])
    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_content', lambda rel, body, frontend_key='': (True, ''))
    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_project', lambda *args, **kwargs: {'ok': True, 'static_issue_count': 0, 'static_issues': []})

    result = validate_and_repair_generated_files(
        project_root=tmp_path,
        cfg=cfg,
        report=report,
        file_ops=file_ops,
        regenerate_callback=None,
        use_execution_core=False,
        max_regen_attempts=0,
    )

    startup_rounds = result.get('startup_repair_rounds') or []
    assert len(startup_rounds) == 1
    signup_controller = next(tmp_path.rglob('SignupController.java'))
    body = signup_controller.read_text(encoding='utf-8')
    assert '@RequestMapping("/signup")' in body
    assert '@PostMapping("/save.do")' in body


def test_post_validation_diagnostic_lines_include_startup_rounds():
    lines = post_validation_diagnostic_lines({
        'startup_repair_rounds': [{
            'round': 1,
            'targets': ['src/main/java/egovframework/test/signup/web/SignupController.java'],
            'changed': [{'path': 'src/main/java/egovframework/test/signup/web/SignupController.java'}],
            'skipped': [],
            'before': {'compile_status': 'ok', 'startup_status': 'failed', 'endpoint_smoke_status': 'skipped'},
            'after': {'compile_status': 'ok', 'startup_status': 'ok', 'endpoint_smoke_status': 'ok'},
        }],
    })
    assert any(line.startswith('[STARTUP-REPAIR] round=1') for line in lines)
    assert any(line.startswith('[STARTUP-RETRY-1] before compile=ok, startup=failed') for line in lines)
