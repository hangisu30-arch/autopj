from pathlib import Path

from app.io.execution_core_apply import _augment_schema_map_with_auth, _ensure_auth_bundle_files, _schema_map_from_file_ops
from app.ui.state import ProjectConfig
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH


def test_login_controller_only_ops_are_upgraded_to_auth_schema(tmp_path: Path):
    file_ops = [
        {
            'path': 'src/main/java/egovframework/test/login/web/LoginController.java',
            'purpose': 'login controller',
            'content': 'package egovframework.test.login.web; public class LoginController {}',
        }
    ]
    cfg = ProjectConfig(frontend_key='jsp', login_feature_enabled=True, auth_unified_auth=True)

    schema_map = _augment_schema_map_with_auth(_schema_map_from_file_ops(file_ops), file_ops, cfg)

    assert 'Login' in schema_map
    schema = schema_map['Login']
    assert getattr(schema, 'feature_kind', '') == FEATURE_KIND_AUTH
    assert getattr(schema, 'unified_auth', False) is True

    changed = _ensure_auth_bundle_files(tmp_path, 'egovframework.test', schema_map, cfg)

    expected = [
        'src/main/java/egovframework/test/login/service/LoginService.java',
        'src/main/java/egovframework/test/login/service/impl/LoginServiceImpl.java',
        'src/main/java/egovframework/test/login/service/vo/LoginVO.java',
        'src/main/java/egovframework/test/login/service/impl/LoginDAO.java',
        'src/main/java/egovframework/test/login/web/LoginController.java',
        'src/main/webapp/WEB-INF/views/login/login.jsp',
        'src/main/webapp/WEB-INF/views/login/main.jsp',
        'src/main/webapp/WEB-INF/views/login/integrationGuide.jsp',
    ]
    for rel in expected:
        assert (tmp_path / rel).exists(), rel
    assert changed


def test_login_schema_augments_from_artifact_text_without_global_flags():
    file_ops = [
        {
            'path': 'src/main/java/egovframework/test/login/web/LoginController.java',
            'purpose': 'integrated auth login controller',
            'content': 'import egovframework.test.login.service.IntegratedAuthService; return "login/integrationGuide";',
        }
    ]
    cfg = ProjectConfig(frontend_key='jsp')

    schema_map = _augment_schema_map_with_auth(_schema_map_from_file_ops(file_ops), file_ops, cfg)

    schema = schema_map['Login']
    assert getattr(schema, 'feature_kind', '') == FEATURE_KIND_AUTH
    assert getattr(schema, 'unified_auth', False) is True


def test_auth_bundle_helper_services_use_login_vo_package(tmp_path: Path):
    file_ops = [
        {
            'path': 'src/main/java/egovframework/test/login/web/LoginController.java',
            'purpose': 'integrated auth and certificate login controller',
            'content': 'import egovframework.test.login.service.IntegratedAuthService; import egovframework.test.login.service.CertLoginService; return "login/integrationGuide";',
        },
        {
            'path': 'src/main/java/egovframework/test/integratedAuth/web/IntegratedAuthController.java',
            'purpose': 'helper auth controller mention that should collapse into login bundle',
            'content': 'public class IntegratedAuthController {}',
        },
    ]
    cfg = ProjectConfig(frontend_key='jsp', login_feature_enabled=True, auth_unified_auth=True, auth_cert_login=True)

    schema_map = _augment_schema_map_with_auth(_schema_map_from_file_ops(file_ops), file_ops, cfg)
    assert 'Login' in schema_map
    assert 'IntegratedAuth' not in schema_map
    _ensure_auth_bundle_files(tmp_path, 'egovframework.test', schema_map, cfg)

    integrated_service = (tmp_path / 'src/main/java/egovframework/test/login/service/IntegratedAuthService.java').read_text(encoding='utf-8')
    cert_service = (tmp_path / 'src/main/java/egovframework/test/login/service/CertLoginService.java').read_text(encoding='utf-8')

    assert 'import egovframework.test.login.service.vo.LoginVO;' in integrated_service
    assert 'import egovframework.test.login.service.vo.LoginVO;' in cert_service
    assert 'login.integratedAuth.service.vo' not in integrated_service
    assert 'login.certLogin.service.vo' not in cert_service



def test_auth_helper_paths_collapse_to_login_bundle_paths():
    from app.io.execution_core_apply import _canonicalize_auth_raw_path
    cfg = ProjectConfig(frontend_key='jsp', login_feature_enabled=True, auth_unified_auth=True, auth_cert_login=True, auth_jwt_login=True)
    schema_map = _augment_schema_map_with_auth({}, [], cfg)
    assert _canonicalize_auth_raw_path('src/main/java/egovframework/test/integratedAuth/web/IntegratedAuthController.java', schema_map) == ''
    assert _canonicalize_auth_raw_path('src/main/java/egovframework/test/login/certLogin/service/impl/CertLoginServiceImpl.java', schema_map) == 'java/service/impl/CertLoginServiceImpl.java'
    assert _canonicalize_auth_raw_path('src/main/java/egovframework/test/login/integratedAuth/service/IntegratedAuthService.java', schema_map) == 'java/service/IntegratedAuthService.java'


def test_auth_bundle_ensure_only_writes_single_owner_bundle(tmp_path: Path):
    cfg = ProjectConfig(frontend_key='jsp', login_feature_enabled=True, auth_unified_auth=True, auth_cert_login=True)
    file_ops = [
        {'path': 'src/main/java/egovframework/test/login/web/LoginController.java', 'purpose': 'login controller', 'content': 'public class LoginController {}'},
        {'path': 'src/main/java/egovframework/test/integratedAuth/web/IntegratedAuthController.java', 'purpose': 'helper controller', 'content': 'public class IntegratedAuthController {}'},
    ]
    schema_map = _augment_schema_map_with_auth(_schema_map_from_file_ops(file_ops), file_ops, cfg)
    changed = _ensure_auth_bundle_files(tmp_path, 'egovframework.test', schema_map, cfg)
    assert (tmp_path / 'src/main/java/egovframework/test/login/service/IntegratedAuthService.java').exists()
    assert not (tmp_path / 'src/main/java/egovframework/test/integratedauth/service/IntegratedAuthService.java').exists()
    assert changed



def test_auth_owner_stays_login_even_when_other_entity_is_marked_auth():
    from app.io.execution_core_apply import _auth_owner_entity
    user_auth_schema = schema_for('User', feature_kind=FEATURE_KIND_AUTH)
    cfg = ProjectConfig(frontend_key='jsp', login_feature_enabled=True, auth_unified_auth=True, auth_cert_login=True)
    schema_map = _augment_schema_map_with_auth({'User': user_auth_schema}, [], cfg)

    assert 'Login' in schema_map
    assert _auth_owner_entity(schema_map) == 'Login'
    assert getattr(schema_map['Login'], 'feature_kind', '') == FEATURE_KIND_AUTH
    assert getattr(schema_map['User'], 'feature_kind', '') != FEATURE_KIND_AUTH
