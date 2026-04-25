from pathlib import Path
from types import SimpleNamespace

from app.io.execution_core_apply import _augment_schema_map_with_auth, _friendly_nav_label, _route_key_from_url_or_view
from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import auto_repair_generated_project
from execution_core.builtin_crud import _extract_explicit_requirement_field_entries, _auth_options_from_sources, schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH


def test_explicit_field_extraction_ignores_non_contract_instruction_bullet_after_columns():
    text = '''
테이블명: tb_users
컬럼정의:
- id
- login_id
- password
- user_name
- ID 및 주요 요청 파라미터는 Long 보다 String 중심으로 처리하세요. 명확한 수치 계산이 필요한 경우가 아니면 String 을 우선 사용하세요.
'''
    entries = _extract_explicit_requirement_field_entries(text)
    cols = [entry['col'] for entry in entries]
    assert cols == ['id', 'login_id', 'password', 'user_name']
    assert next(entry for entry in entries if entry['col'] == 'id')['comment'] == ''


def test_auth_options_do_not_enable_jwt_when_requirement_explicitly_forbids_it():
    text = '로그인 기능은 필요하지만 jwt 로그인은 생성하지 말고 일반 로그인만 구현하세요.'
    unified_auth, cert_login, jwt_login = _auth_options_from_sources(text, FEATURE_KIND_AUTH)
    assert cert_login is False
    assert jwt_login is False
    assert unified_auth is False


def test_augment_schema_map_with_auth_ignores_stray_jwt_file_names_when_option_disabled():
    cfg = SimpleNamespace(
        login_feature_enabled=True,
        auth_unified_auth=False,
        auth_cert_login=False,
        auth_jwt_login=False,
        extra_requirements='일반 로그인과 회원가입만 필요합니다.',
    )
    schema_map = {'Login': schema_for('Login', table='tb_login', feature_kind=FEATURE_KIND_AUTH)}
    file_ops = [
        {'path': 'jsp/login/jwtLogin.jsp', 'purpose': 'existing stray file path only'},
        {'path': 'java/controller/JwtLoginController.java', 'purpose': 'existing stray file path only'},
    ]
    out = _augment_schema_map_with_auth(schema_map, file_ops, cfg)
    login_schema = out['Login']
    assert getattr(login_schema, 'jwt_login', False) is False
    assert getattr(login_schema, 'cert_login', False) is False
    assert getattr(login_schema, 'unified_auth', False) is False


def test_unexpected_jwt_helper_artifacts_are_validated_and_removed(tmp_path: Path):
    project_root = tmp_path / 'project'
    jwt_jsp = project_root / 'src/main/webapp/WEB-INF/views/login/jwtLogin.jsp'
    jwt_jsp.parent.mkdir(parents=True, exist_ok=True)
    jwt_jsp.write_text('<html><body>jwt</body></html>\n', encoding='utf-8')

    jwt_controller = project_root / 'src/main/java/egovframework/test/login/web/JwtLoginController.java'
    jwt_controller.parent.mkdir(parents=True, exist_ok=True)
    jwt_controller.write_text('package egovframework.test.login.web; public class JwtLoginController {}\n', encoding='utf-8')

    cfg = SimpleNamespace(
        frontend_key='jsp',
        database_key='mysql',
        database_type='mysql',
        auth_unified_auth=False,
        auth_cert_login=False,
        auth_jwt_login=False,
        extra_requirements='일반 로그인만 필요합니다.',
        effective_extra_requirements=lambda: '일반 로그인만 필요합니다.',
    )

    report = validate_generated_project(project_root, cfg, include_runtime=False)
    types = [issue.get('type') for issue in report.get('static_issues') or []]
    assert 'unexpected_auth_helper_artifact' in types

    repair = auto_repair_generated_project(project_root, report)
    changed = {(item.get('path'), item.get('type')) for item in repair.get('changed') or []}
    assert ('src/main/webapp/WEB-INF/views/login/jwtLogin.jsp', 'unexpected_auth_helper_artifact') in changed
    assert not jwt_jsp.exists()
    assert not jwt_controller.exists()


def test_signup_route_key_and_label_are_user_friendly():
    assert _route_key_from_url_or_view('/member/signup.do', 'member/signup', 'signupForm') == 'signup'
    assert _friendly_nav_label('member', 'signup') == '회원가입'


def test_validator_flags_missing_signup_nav_and_missing_search_ui(tmp_path: Path):
    project_root = tmp_path / 'project'
    views = project_root / 'src/main/webapp/WEB-INF/views'
    common = views / 'common'
    member = views / 'member'
    common.mkdir(parents=True, exist_ok=True)
    member.mkdir(parents=True, exist_ok=True)

    (common / 'leftNav.jsp').write_text('<ul><li><a href="<c:url value=\'/login/login.do\' />">로그인</a></li></ul>\n', encoding='utf-8')
    (member / 'memberList.jsp').write_text('<table><tr><td>list</td></tr></table>\n', encoding='utf-8')
    (member / 'signup.jsp').write_text('<form><input name="loginId" /><input type="password" name="password" /></form>\n', encoding='utf-8')

    controller = project_root / 'src/main/java/egovframework/test/member/web/MemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/member")\n'
        'public class MemberController {\n'
        '  @GetMapping("/signup.do") public String signup(){ return "member/signup"; }\n'
        '}\n',
        encoding='utf-8',
    )

    vo = project_root / 'src/main/java/egovframework/test/member/service/vo/MemberVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        'package egovframework.test.member.service.vo;\n'
        'public class MemberVO {\n'
        '  private String memberId;\n'
        '  private String memberName;\n'
        '}\n',
        encoding='utf-8',
    )

    cfg = SimpleNamespace(
        frontend_key='jsp',
        database_key='mysql',
        database_type='mysql',
        auth_unified_auth=False,
        auth_cert_login=False,
        auth_jwt_login=False,
        extra_requirements='회원가입과 회원목록이 필요합니다.',
        effective_extra_requirements=lambda: '회원가입과 회원목록이 필요합니다.',
    )

    report = validate_generated_project(project_root, cfg, include_runtime=False)
    messages = [issue.get('message') or '' for issue in report.get('static_issues') or []]
    types = [issue.get('type') for issue in report.get('static_issues') or []]
    assert 'auth_nav_route_mismatch' in types
    assert 'search_ui_missing' in types
    assert any('signup entry' in msg for msg in messages)
    assert any('missing concrete search conditions' in msg for msg in messages)
