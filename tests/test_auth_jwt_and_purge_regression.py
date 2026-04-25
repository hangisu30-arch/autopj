from pathlib import Path

from app.io.execution_core_apply import _augment_schema_map_with_auth, _purge_misplaced_auth_artifacts
from app.ui.state import ProjectConfig
from app.validation.generated_project_validator import _scan_expected_service_pairs
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH


def test_expected_service_pairs_ignores_jwt_login_controller(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/login/web/JwtLoginController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        '@Controller\n'
        'public class JwtLoginController {\n'
        '  @GetMapping("/login/jwtLogin.do") public String jwtLoginForm() { return "login/jwtLogin"; }\n'
        '}\n',
        encoding='utf-8',
    )

    issues = _scan_expected_service_pairs(tmp_path)
    assert not any('JwtLogin' in issue.get('message', '') for issue in issues)



def test_purge_misplaced_auth_artifacts_removes_stray_auth_module_files(tmp_path: Path):
    cfg = ProjectConfig(frontend_key='jsp', login_feature_enabled=True, auth_jwt_login=True)
    schema_map = _augment_schema_map_with_auth({'Auth': schema_for('Auth', feature_kind=FEATURE_KIND_AUTH)}, [], cfg)

    stray = tmp_path / 'src/main/java/egovframework/test/auth/service/impl/AuthServiceImpl.java'
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text('package egovframework.test.auth.service.impl; public class AuthServiceImpl {}\n', encoding='utf-8')

    keeper = tmp_path / 'src/main/java/egovframework/test/login/service/impl/LoginServiceImpl.java'
    keeper.parent.mkdir(parents=True, exist_ok=True)
    keeper.write_text('package egovframework.test.login.service.impl; public class LoginServiceImpl {}\n', encoding='utf-8')

    removed = _purge_misplaced_auth_artifacts(tmp_path, 'egovframework.test', schema_map)

    assert 'src/main/java/egovframework/test/auth/service/impl/AuthServiceImpl.java' in removed
    assert not stray.exists()
    assert keeper.exists()
