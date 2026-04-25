from pathlib import Path

from app.io.execution_core_apply import _canonicalize_auth_raw_path
from app.ui.fallback_builder import build_builtin_fallback_content
from app.validation.backend_compile_repair import enforce_generated_project_invariants, regenerate_compile_failure_targets
from app.validation.generated_project_validator import validate_generated_project
from app.ui.state import ProjectConfig
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_canonicalize_auth_raw_path_maps_authentic_interceptor_alias_and_drops_mapper():
    schema_map = {'Login': schema_for('Login', feature_kind=FEATURE_KIND_AUTH, unified_auth=True)}
    assert _canonicalize_auth_raw_path('src/main/java/egovframework/test/generic/AuthenticInterceptor.java', schema_map) == 'java/config/AuthLoginInterceptor.java'
    assert _canonicalize_auth_raw_path('src/main/resources/egovframework/mapper/generic/AuthenticInterceptorMapper.xml', schema_map) == ''


def test_fallback_builder_materializes_auth_login_interceptor_bundle():
    body = build_builtin_fallback_content('src/main/java/egovframework/test/login/config/AuthLoginInterceptor.java', '통합인증 로그인 인터셉터', project_name='test')
    assert 'class AuthLoginInterceptor implements HandlerInterceptor' in body
    assert '/login/login.do' in body


def test_enforce_generated_project_invariants_removes_authentic_interceptor_artifacts(tmp_path):
    _write(tmp_path / 'src/main/java/egovframework/test/generic/AuthenticInterceptor.java', 'package egovframework.test.generic; public class AuthenticInterceptor {}')
    _write(tmp_path / 'src/main/resources/egovframework/mapper/generic/AuthenticInterceptorMapper.xml', '<mapper namespace="x"></mapper>')
    report = enforce_generated_project_invariants(tmp_path)
    assert not (tmp_path / 'src/main/java/egovframework/test/generic/AuthenticInterceptor.java').exists()
    assert not (tmp_path / 'src/main/resources/egovframework/mapper/generic/AuthenticInterceptorMapper.xml').exists()
    reasons = {(item.get('path'), item.get('reason')) for item in report['changed']}
    assert ('src/main/java/egovframework/test/generic/AuthenticInterceptor.java', 'invalid infra artifact removed') in reasons


def test_validator_ignores_authentic_interceptor_mapper_namespace_false_positive(tmp_path):
    _write(tmp_path / 'src/main/java/egovframework/test/login/config/AuthLoginInterceptor.java', 'package egovframework.test.login.config; public class AuthLoginInterceptor {}')
    _write(tmp_path / 'src/main/resources/egovframework/mapper/generic/AuthenticInterceptorMapper.xml', '<mapper namespace="egovframework.test.generic.authenticInterceptor.service.mapper.AuthenticInterceptorMapper"></mapper>')
    report = validate_generated_project(tmp_path, ProjectConfig(project_name='test', frontend_key='jsp'), include_runtime=False)
    messages = [item.get('message', '') for item in report.get('issues', [])]
    assert not any('AuthenticInterceptorMapper' in msg for msg in messages)


def test_local_contract_repair_triggers_import_refresh_even_without_regen(monkeypatch, tmp_path):
    controller = tmp_path / 'src/main/java/egovframework/test/user/web/UserController.java'
    _write(controller,
        'package egovframework.test.user.web;\n\n'
        'import egovframework.test.user.service.UserService;\n'
        'public class UserController {\n'
        '  private final UserService userService;\n'
        '  public UserController(UserService userService) { this.userService = userService; }\n'
        '}\n'
    )
    called = []
    import app.validation.backend_compile_repair as mod
    def fake_fix(root):
        called.append(str(root))
        return []
    monkeypatch.setattr(mod, 'fix_project_java_imports', fake_fix)
    runtime_report = {'compile': {'errors': [{'code': 'cannot_find_symbol', 'path': 'src/main/java/egovframework/test/user/web/UserController.java'}]}}
    manifest = {'src/main/java/egovframework/test/user/web/UserController.java': {'spec': '테이블 이름: users\n컬럼 목록:\n- user_id\n- login_id\n- password'}}
    cfg = ProjectConfig(project_name='test', frontend_key='jsp')
    result = regenerate_compile_failure_targets(tmp_path, cfg, manifest, runtime_report, regenerate_callback=None, apply_callback=lambda *args, **kwargs: {}, use_execution_core=False, frontend_key='jsp')
    assert result['changed']
    assert called



def test_auth_interceptor_aliases_are_canonicalized_and_filtered():
    schema_map = {'Login': object()}
    assert _canonicalize_auth_raw_path('src/main/java/egovframework/test/interceptor/AuthInterceptor.java', schema_map) == 'java/config/AuthLoginInterceptor.java'
    assert _canonicalize_auth_raw_path('src/main/resources/egovframework/mapper/interceptor/AuthInterceptorMapper.xml', schema_map) == ''
    assert _canonicalize_auth_raw_path('src/main/java/egovframework/test/interceptor/service/AuthInterceptorService.java', schema_map) == ''


def test_illegal_auth_interceptor_crud_artifacts_are_removed(tmp_path):
    _write(tmp_path / 'src/main/java/egovframework/test/interceptor/AuthInterceptor.java', 'package egovframework.test.interceptor; public class AuthInterceptor {}')
    _write(tmp_path / 'src/main/java/egovframework/test/interceptor/service/AuthInterceptorService.java', 'package egovframework.test.interceptor.service; public interface AuthInterceptorService {}')
    _write(tmp_path / 'src/main/java/egovframework/test/interceptor/service/impl/AuthInterceptorServiceImpl.java', 'package egovframework.test.interceptor.service.impl; public class AuthInterceptorServiceImpl {}')
    _write(tmp_path / 'src/main/resources/egovframework/mapper/interceptor/AuthInterceptorMapper.xml', '<mapper namespace="x"></mapper>')

    report = enforce_generated_project_invariants(tmp_path)

    assert not (tmp_path / 'src/main/java/egovframework/test/interceptor/AuthInterceptor.java').exists()
    assert not (tmp_path / 'src/main/java/egovframework/test/interceptor/service/AuthInterceptorService.java').exists()
    assert not (tmp_path / 'src/main/java/egovframework/test/interceptor/service/impl/AuthInterceptorServiceImpl.java').exists()
    assert not (tmp_path / 'src/main/resources/egovframework/mapper/interceptor/AuthInterceptorMapper.xml').exists()
    reasons = {(item.get('path'), item.get('reason')) for item in report.get('changed') or []}
    assert ('src/main/java/egovframework/test/interceptor/AuthInterceptor.java', 'invalid infra artifact removed') in reasons
    assert ('src/main/java/egovframework/test/interceptor/service/AuthInterceptorService.java', 'invalid infra artifact removed') in reasons

