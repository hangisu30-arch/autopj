from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH
from execution_core.generator import normalize_tasks


def test_jwt_login_requested_adds_jwt_artifacts_to_auth_tasks():
    plan = {
        'requirements_text': '통합인증 기반 로그인에 JWT 로그인도 추가해줘.',
        'tasks': [{'path': 'java/controller/LoginController.java', 'purpose': 'login controller'}],
        'db_ops': [],
    }
    paths = [task['path'] for task in normalize_tasks(plan)]
    assert 'java/config/JwtTokenProvider.java' in paths
    assert 'java/controller/JwtLoginController.java' in paths
    assert 'jsp/login/jwtLogin.jsp' in paths


def test_jwt_login_bundle_is_rendered_in_login_and_jwt_views():
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH, unified_auth=True, jwt_login=True)
    login_jsp = builtin_file('jsp/login/login.jsp', 'egovframework.test', schema)
    jwt_jsp = builtin_file('jsp/login/jwtLogin.jsp', 'egovframework.test', schema)
    jwt_controller = builtin_file('java/controller/JwtLoginController.java', 'egovframework.test', schema)
    jwt_provider = builtin_file('java/config/JwtTokenProvider.java', 'egovframework.test', schema)
    interceptor = builtin_file('java/config/AuthLoginInterceptor.java', 'egovframework.test', schema)

    assert 'JWT 로그인' in login_jsp
    assert '/login/actionJwtLogin.do' in jwt_jsp
    assert '@PostMapping("/actionJwtLogin.do")' in jwt_controller
    assert 'class JwtTokenProvider' in jwt_provider
    assert 'path.startsWith("/login/jwtLogin.do")' in interceptor
    assert 'path.startsWith("/login/actionJwtLogin.do")' in interceptor
