from pathlib import Path

from app.ui.generated_content_validator import validate_generated_content
from app.ui.ui_sanitize_common import sanitize_frontend_ui_text
from app.validation.generated_project_validator import _is_jsp_validation_partial
from app.validation.post_generation_repair import _sanitize_jsp_partial_includes


def test_layout_header_is_treated_as_validation_partial_and_sanitized(tmp_path: Path):
    rel = 'src/main/webapp/WEB-INF/views/layout/header.jsp'
    jsp = tmp_path / rel
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<%@ include file="/WEB-INF/views/common/header.jsp" %>\n'
        '<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>\n'
        '<a href="<c:url value="/main.do"/>">메인</a>\n',
        encoding='utf-8',
    )

    assert _is_jsp_validation_partial(rel) is True
    changed = _sanitize_jsp_partial_includes(tmp_path)
    assert rel in changed
    cleaned = jsp.read_text(encoding='utf-8')
    assert 'include file=' not in cleaned
    assert 'layout partial placeholder' in cleaned


def test_sensitive_pw_variants_are_removed_from_non_auth_member_list():
    path = 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    raw = '''<table>
<tr><td>memberPw</td><td>${row.memberPw}</td></tr>
<tr><td>accountPw</td><td>${row.accountPw}</td></tr>
<tr><td>adminPw</td><td>${row.adminPw}</td></tr>
</table>'''
    cleaned = sanitize_frontend_ui_text(path, raw, 'non-auth UI must not expose auth-sensitive fields such as password/login_password')
    low = cleaned.lower()
    assert 'memberpw' not in low
    assert 'accountpw' not in low
    assert 'adminpw' not in low
    ok, reason = validate_generated_content(path, cleaned, frontend_key='jsp')
    assert ok, reason
