from execution_core.builtin_crud import builtin_file, infer_schema_from_plan, schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH
from execution_core.generator import normalize_tasks


def test_auth_schema_defaults_to_unified_auth_process():
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH)
    assert schema.unified_auth is True
    assert schema.cert_login is False


def test_cert_login_is_enabled_when_requirements_request_certificate_login():
    plan = {
        'requirements_text': '로그인을 만들어줘. 사용자 통합인증 프로세스를 포함하고 인증서 로그인도 추가해줘.',
        'tasks': [{'path': 'java/controller/LoginController.java', 'purpose': 'login controller'}],
        'db_ops': [],
    }
    schema = infer_schema_from_plan(plan)
    assert schema.unified_auth is True
    assert schema.cert_login is True


def test_auth_tasks_include_integration_and_certificate_artifacts_when_requested():
    plan = {
        'requirements_text': '통합인증 기반 로그인과 인증서 로그인까지 만들어줘.',
        'tasks': [{'path': 'java/controller/LoginController.java', 'purpose': 'integrated auth login controller'}],
        'db_ops': [],
    }
    paths = [task['path'] for task in normalize_tasks(plan)]
    assert 'java/service/IntegratedAuthService.java' in paths
    assert 'jsp/login/integrationGuide.jsp' in paths
    assert 'java/service/CertLoginService.java' in paths
    assert 'java/controller/CertLoginController.java' in paths
    assert 'jsp/login/certLogin.jsp' in paths


def test_auth_login_controller_contains_integrated_callback_flow():
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH, unified_auth=True, cert_login=True)
    body = builtin_file('java/controller/LoginController.java', 'egovframework.test', schema)
    assert 'IntegratedAuthService integratedAuthService' in body
    assert '@GetMapping("/integrationGuide.do")' in body
    assert '@GetMapping("/integratedCallback.do")' in body
    assert 'applyAuthenticatedSession(session, authUser);' in body


def test_auth_login_jsp_shows_unified_and_certificate_actions():
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH, unified_auth=True, cert_login=True)
    jsp = builtin_file('jsp/login/login.jsp', 'egovframework.test', schema)
    assert '통합인증 로그인' in jsp
    assert '인증서 로그인' in jsp
    cert_jsp = builtin_file('jsp/login/certLogin.jsp', 'egovframework.test', schema)
    assert '/login/actionCertLogin.do' in cert_jsp
    guide_jsp = builtin_file('jsp/login/integrationGuide.jsp', 'egovframework.test', schema)
    assert '/login/integratedCallback.do?loginId=admin' in guide_jsp


def test_auth_interceptor_and_webmvc_allow_auxiliary_auth_routes():
    from execution_core.builtin_crud import builtin_file, schema_for
    from execution_core.feature_rules import FEATURE_KIND_AUTH

    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH, unified_auth=True, cert_login=True, jwt_login=True)
    interceptor = builtin_file('java/config/AuthLoginInterceptor.java', 'egovframework.test', schema)
    webmvc = builtin_file('java/config/WebMvcConfig.java', 'egovframework.test', schema)

    assert '/login/integrationGuide.do' in interceptor
    assert '/login/certLogin.do' in interceptor
    assert '/login/actionCertLogin.do' in interceptor
    assert 'integrationGuide' in webmvc
    assert 'certLogin' in webmvc
    assert 'jwtLogin' in webmvc
