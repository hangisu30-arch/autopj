from app.ui.fallback_builder import build_builtin_fallback_content


def test_auth_helper_fallback_builder_keeps_login_owner_bundle_for_cert_login_impl():
    body = build_builtin_fallback_content(
        'src/main/java/egovframework/test/login/service/impl/CertLoginServiceImpl.java',
        '인증서 로그인 구현',
        project_name='test',
    )

    assert 'package egovframework.test.login.service.impl;' in body
    assert 'import egovframework.test.login.service.CertLoginService;' in body
    assert 'import egovframework.test.login.service.IntegratedAuthService;' in body
    assert 'import egovframework.test.login.service.vo.LoginVO;' in body
    assert 'login.certLogin.service.vo' not in body
    assert 'CertLoginDAO' not in body
