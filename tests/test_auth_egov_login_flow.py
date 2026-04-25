from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH
from execution_core.generator import normalize_tasks


def test_auth_schema_uses_generic_login_routes_and_views():
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH)
    assert schema.routes['login'] == '/login/login.do'
    assert schema.routes['process'] == '/login/actionLogin.do'
    assert schema.routes['logout'] == '/login/actionLogout.do'
    assert schema.routes['main'] == '/login/actionMain.do'
    assert schema.views['login'] == 'login/login'
    assert schema.views['main'] == 'login/main'


def test_auth_tasks_include_egov_login_flow_files():
    plan = {'tasks': [{'path': 'java/controller/LoginController.java', 'purpose': 'login controller'}], 'db_ops': []}
    paths = [task['path'] for task in normalize_tasks(plan)]
    assert 'java/service/impl/LoginDAO.java' in paths
    assert 'java/config/AuthLoginInterceptor.java' in paths
    assert 'java/config/WebMvcConfig.java' in paths
    assert 'jsp/login/login.jsp' in paths
    assert 'jsp/login/main.jsp' in paths


def test_auth_builtin_controller_sets_egov_style_session_and_main_flow():
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH)
    body = builtin_file('java/controller/LoginController.java', 'egovframework.test', schema)
    assert '@RequestMapping("/login")' in body
    assert '@PostMapping({"/actionLogin.do", "/process.do"})' in body
    assert '@GetMapping("/actionMain.do")' in body
    assert 'session.setAttribute("loginVO", authUser);' in body
    assert 'session.setAttribute("accessUser", authUser.getLoginId());' in body
    assert 'return "redirect:/login/actionMain.do";' in body


def test_auth_builtin_interceptor_protects_do_routes_except_login_endpoints():
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH)
    interceptor = builtin_file('java/config/AuthLoginInterceptor.java', 'egovframework.test', schema)
    webmvc = builtin_file('java/config/WebMvcConfig.java', 'egovframework.test', schema)
    assert 'class AuthLoginInterceptor implements HandlerInterceptor' in interceptor
    assert 'response.sendRedirect(contextPath + "/login/login.do")' in interceptor
    assert '.addPathPatterns("/**/*.do")' in webmvc
    assert '"/login/actionLogin.do"' in webmvc
    assert '"/login/actionLogout.do"' in webmvc


def test_auth_login_and_main_jsp_are_generated_under_login_folder():
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH)
    login_jsp = builtin_file('jsp/login/login.jsp', 'egovframework.test', schema)
    main_jsp = builtin_file('jsp/login/main.jsp', 'egovframework.test', schema)
    assert 'action="<c:url value=\'/login/actionLogin.do\'/>"' in login_jsp
    assert '전자정부 스타일의 세션 인증 흐름' in login_jsp
    assert '<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>' in main_jsp
    assert 'href="<c:url value=\'/login/actionLogout.do\'/>"' in main_jsp
