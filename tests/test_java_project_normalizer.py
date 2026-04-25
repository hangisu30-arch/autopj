from pathlib import Path

from app.validation.java_project_normalizer import normalize_generated_project
from app.io.execution_core_apply import _augment_schema_map_with_auth
from app.ui.state import ProjectConfig
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_normalize_generated_project_repairs_cert_login_type_names(tmp_path: Path) -> None:
    root = tmp_path
    _write(
        root / 'src/main/java/egovframework/test/login/service/vo/LoginVO.java',
        'package egovframework.test.login.service.vo;\n\npublic class LoginVO {}\n',
    )
    _write(
        root / 'src/main/java/egovframework/test/login/service/LoginService.java',
        'package egovframework.test.login.service;\n\npublic interface LoginService {\n    LoginVO authenticate(String loginId, String password) throws Exception;\n}\n',
    )
    _write(
        root / 'src/main/java/egovframework/test/login/service/IntegratedAuthService.java',
        'package egovframework.test.login.service;\n\npublic interface IntegratedAuthService {}\n',
    )
    _write(
        root / 'src/main/java/egovframework/test/login/service/CertLoginService.java',
        'package egovframework.test.login.service;\n\nimport egovframework.test.login.service.vo.LoginVO;\n\npublic interface LoginService {\n    LoginVO authenticateCertificate(String loginId, String userName, String certSubjectDn, String certSerialNo) throws Exception;\n}\n',
    )
    _write(
        root / 'src/main/java/egovframework/test/login/service/impl/CertLoginServiceImpl.java',
        'package egovframework.test.login.service.impl;\n\nimport egovframework.test.login.service.LoginService;\nimport egovframework.test.login.service.IntegratedAuthService;\n\npublic class LoginServiceImpl implements LoginService {\n    private final IntegratedAuthService integratedAuthService;\n\n    public LoginServiceImpl(IntegratedAuthService integratedAuthService) {\n        this.integratedAuthService = integratedAuthService;\n    }\n}\n',
    )

    report = normalize_generated_project(root)

    cert_service = (root / 'src/main/java/egovframework/test/login/service/CertLoginService.java').read_text(encoding='utf-8')
    cert_impl = (root / 'src/main/java/egovframework/test/login/service/impl/CertLoginServiceImpl.java').read_text(encoding='utf-8')

    assert 'public interface CertLoginService' in cert_service
    assert 'public class CertLoginServiceImpl implements CertLoginService' in cert_impl
    assert 'public class LoginServiceImpl' not in cert_impl
    assert any(rel.endswith('CertLoginService.java') for rel in report['changed'])
    assert any(rel.endswith('CertLoginServiceImpl.java') for rel in report['changed'])


def test_augment_schema_map_with_auth_enables_integrated_bundle_for_cert_login() -> None:
    schema_map = {
        'Login': schema_for('Login', feature_kind=FEATURE_KIND_AUTH, unified_auth=False, cert_login=False, jwt_login=False),
    }
    cfg = ProjectConfig(login_feature_enabled=True, auth_cert_login=True)

    updated = _augment_schema_map_with_auth(schema_map, [{'path': 'java/service/CertLoginService.java', 'content': 'cert login'}], cfg)
    schema = updated['Login']

    assert getattr(schema, 'cert_login', False) is True
    assert getattr(schema, 'unified_auth', False) is True


def test_normalize_generated_project_rebuilds_broken_cert_login_impl_against_login_bundle(tmp_path: Path) -> None:
    root = tmp_path
    _write(
        root / 'src/main/java/egovframework/test/login/service/vo/LoginVO.java',
        '''package egovframework.test.login.service.vo;

public class LoginVO {}
''',
    )
    _write(
        root / 'src/main/java/egovframework/test/login/service/IntegratedAuthService.java',
        '''package egovframework.test.login.service;

import egovframework.test.login.service.vo.LoginVO;

public interface IntegratedAuthService {
    LoginVO resolveIntegratedUser(String loginId, String userName) throws Exception;
}
''',
    )
    _write(
        root / 'src/main/java/egovframework/test/login/service/CertLoginService.java',
        '''package egovframework.test.login.service;

import egovframework.test.login.service.vo.LoginVO;

public interface CertLoginService {
    LoginVO authenticateCertificate(String loginId, String userName, String certSubjectDn, String certSerialNo) throws Exception;
}
''',
    )
    _write(
        root / 'src/main/java/egovframework/test/login/service/impl/CertLoginServiceImpl.java',
        '''package egovframework.test.login.service.impl;

import egovframework.test.login.certLogin.service.vo.CertLoginVO;
import egovframework.test.login.service.CertLoginService;

public class CertLoginServiceImpl implements CertLoginService {
    private final CertLoginDAO certLoginDAO;

    public CertLoginServiceImpl(CertLoginDAO certLoginDAO) {
        this.certLoginDAO = certLoginDAO;
    }

    @Override
    public CertLoginVO authenticateCertificate(String loginId, String userName, String certSubjectDn, String certSerialNo) throws Exception {
        return null;
    }
}
''',
    )

    report = normalize_generated_project(root)
    cert_impl = (root / 'src/main/java/egovframework/test/login/service/impl/CertLoginServiceImpl.java').read_text(encoding='utf-8')

    assert 'import egovframework.test.login.service.vo.LoginVO;' in cert_impl
    assert 'import egovframework.test.login.service.IntegratedAuthService;' in cert_impl
    assert 'login.certLogin.service.vo' not in cert_impl
    assert 'CertLoginDAO' not in cert_impl
    assert 'return integratedAuthService.resolveIntegratedUser(loginId, userName);' in cert_impl
    assert any(rel.endswith('CertLoginServiceImpl.java') for rel in report['changed'])
