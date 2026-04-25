from pathlib import Path

from app.validation.backend_compile_repair import _expected_contract_bundle_targets, _is_illegal_infra_artifact
from app.ui.ui_sanitize_common import sanitize_frontend_ui_text
from app.validation.project_auto_repair import _repair_calendar_ssr_missing


def test_infra_canonical_java_does_not_expand_to_crud_bundle():
    rel = 'src/main/java/egovframework/test/config/WebMvcConfig.java'
    targets = _expected_contract_bundle_targets(rel)
    assert targets == [rel, 'src/main/java/egovframework/test/config/AuthLoginInterceptor.java']

    rel2 = 'src/main/java/egovframework/test/config/LoginDatabaseInitializer.java'
    targets2 = _expected_contract_bundle_targets(rel2)
    assert targets2 == [rel2]


def test_illegal_infra_artifact_includes_dao_variants():
    assert _is_illegal_infra_artifact('src/main/java/egovframework/test/config/service/impl/LoginDatabaseInitializerDAO.java')
    assert _is_illegal_infra_artifact('src/main/java/egovframework/test/config/service/impl/WebMvcConfigDAO.java')


def test_ui_sanitize_removes_repeat2_and_pw_variants():
    body = '''<table>
<tr><th>repeat2</th><th>memberPw</th></tr>
<tr><td>${item.repeat2}</td><td>${item.memberPw}</td></tr>
</table>'''
    out = sanitize_frontend_ui_text('src/main/webapp/WEB-INF/views/member/memberList.jsp', body, 'jsp references undefined VO properties: repeat2 and non-auth UI must not expose auth-sensitive fields such as password/login_password')
    assert 'repeat2' not in out
    assert 'memberPw' not in out


def test_forbidden_calendar_is_deleted_for_auth_and_member_domains(tmp_path: Path):
    member = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberCalendar.jsp'
    member.parent.mkdir(parents=True, exist_ok=True)
    member.write_text('<div class="calendar-grid"></div>', encoding='utf-8')
    assert _repair_calendar_ssr_missing(member, {'details': {'domain': 'member'}}, tmp_path)
    assert not member.exists()

    infra = tmp_path / 'src/main/webapp/WEB-INF/views/loginDatabaseInitializer/loginDatabaseInitializerCalendar.jsp'
    infra.parent.mkdir(parents=True, exist_ok=True)
    infra.write_text('<div class="calendar-grid"></div>', encoding='utf-8')
    assert _repair_calendar_ssr_missing(infra, {'details': {'domain': 'loginDatabaseInitializer'}}, tmp_path)
    assert not infra.exists()
