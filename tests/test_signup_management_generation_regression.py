from pathlib import Path

from execution_core.builtin_crud import infer_schema_from_file_ops
from app.ui.fallback_builder import build_builtin_fallback_content
from app.validation.backend_compile_repair import _local_contract_repair
from app.validation.generated_project_validator import validate_generated_project


REQ = """
기존 eGovFramework Spring Boot + JSP + MyBatis 프로젝트에 회원가입 + 회원관리 시스템을 추가해줘.
테이블명: users
컬럼 목록:
- user_id
- login_id
- password
- user_name
- email
- phone
- role_cd
- use_yn
- reg_dt
- upd_dt
로그인ID 중복확인
이메일 validation
전화번호 validation
"""


class _Cfg:
    project_name = 'test'
    frontend_key = 'jsp'


def test_infer_schema_treats_signup_management_as_user_crud():
    file_ops = [
        {
            'path': 'src/main/java/egovframework/test/signup/service/impl/SignupServiceImpl.java',
            'content': REQ,
        },
        {
            'path': 'src/main/webapp/WEB-INF/views/signup/signupList.jsp',
            'content': '<form id="searchForm"></form>',
        },
    ]
    schema = infer_schema_from_file_ops(file_ops, entity='Signup')
    assert schema.entity == 'User'
    assert schema.table == 'users'
    assert schema.feature_kind == 'CRUD'


def test_fallback_builder_generates_crud_signup_bundle_for_signup_management_prompt():
    body = build_builtin_fallback_content(
        'src/main/java/egovframework/test/signup/service/impl/SignupServiceImpl.java',
        REQ,
        project_name='test',
    )
    assert 'class SignupServiceImpl implements SignupService' in body
    assert 'private final SignupMapper signupMapper;' in body
    assert 'authenticate(' not in body
    assert 'findByLoginId' not in body
    assert 'selectSignupList' in body


def test_local_contract_repair_materializes_signup_dao_for_auth_bundle(tmp_path: Path):
    project_root = tmp_path
    svc_impl = project_root / 'src/main/java/egovframework/test/signup/service/impl/SignupServiceImpl.java'
    svc_impl.parent.mkdir(parents=True, exist_ok=True)
    svc_impl.write_text(
        'package egovframework.test.signup.service.impl;\n\n'
        'import org.springframework.stereotype.Service;\n'
        'import egovframework.test.signup.service.SignupService;\n'
        'import egovframework.test.signup.service.vo.SignupVO;\n\n'
        '@Service("signupService")\n'
        'public class SignupServiceImpl implements SignupService {\n'
        '  private final SignupDAO signupDAO;\n'
        '  public SignupServiceImpl(SignupDAO signupDAO) { this.signupDAO = signupDAO; }\n'
        '  public SignupVO authenticate(SignupVO vo) throws Exception { return signupDAO.actionLogin(vo); }\n'
        '  public SignupVO findByLoginId(String loginId) throws Exception { return signupDAO.findByLoginId(loginId); }\n'
        '}\n',
        encoding='utf-8',
    )
    manifest = {
        'src/main/java/egovframework/test/signup/service/impl/SignupServiceImpl.java': {'spec': REQ + '\n로그인 기능도 구현해줘.'}
    }
    runtime_report = {
        'compile': {
            'errors': [
                {'code': 'cannot_find_symbol', 'path': 'src/main/java/egovframework/test/signup/service/impl/SignupServiceImpl.java'},
                {'code': 'cannot_find_symbol', 'path': 'src/main/java/egovframework/test/signup/service/impl/SignupServiceImpl.java'},
            ]
        }
    }
    changed = _local_contract_repair(project_root, _Cfg(), manifest, [
        'src/main/java/egovframework/test/signup/service/impl/SignupServiceImpl.java'
    ], runtime_report)
    assert changed
    dao_path = project_root / 'src/main/java/egovframework/test/signup/service/impl/SignupDAO.java'
    assert dao_path.exists()
    assert 'class SignupDAO' in dao_path.read_text(encoding='utf-8')


def test_validator_skips_login_list_search_field_requirement(tmp_path: Path):
    project_root = tmp_path
    jsp_path = project_root / 'src/main/webapp/WEB-INF/views/login/loginList.jsp'
    vo_path = project_root / 'src/main/java/egovframework/test/login/service/vo/LoginVO.java'
    jsp_path.parent.mkdir(parents=True, exist_ok=True)
    vo_path.parent.mkdir(parents=True, exist_ok=True)
    jsp_path.write_text('<form id="searchForm"><input type="text" name="loginId" /></form>', encoding='utf-8')
    vo_path.write_text(
        'package egovframework.test.login.service.vo;\n'
        'public class LoginVO {\n'
        '  private String loginId;\n'
        '  private String password;\n'
        '}\n',
        encoding='utf-8',
    )
    report = validate_generated_project(project_root, _Cfg(), include_runtime=False)
    assert not any(item.get('type') == 'search_fields_incomplete' for item in report.get('static_issues') or [])


def test_fallback_builder_never_generates_auth_login_routes_for_signup_controller_even_with_existing_login_text():
    spec = REQ + "\n기존 로그인은 그대로 유지하고 로그인 기능은 새로 만들지 마라.\n"
    body = build_builtin_fallback_content(
        'src/main/java/egovframework/test/signup/web/SignupController.java',
        spec,
        project_name='test',
    )
    assert '@RequestMapping("/signup")' in body
    assert '/login/actionLogin.do' not in body
    assert 'authenticate(' not in body
    assert 'return "login/login"' not in body
