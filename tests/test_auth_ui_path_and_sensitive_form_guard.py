from pathlib import Path

from app.ui.generated_content_validator import validate_generated_content
from app.ui.ui_sanitize_common import is_auth_ui_file_path
from app.validation.post_generation_repair import _sanitize_frontend_ui_file
from app.io.execution_core_apply import _rewrite_form_jsp_from_schema
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH, FEATURE_KIND_CRUD


def test_member_login_path_is_treated_as_auth_ui() -> None:
    body = '<form><input type="text" name="loginId"/><input type="password" name="loginPassword"/></form>'
    ok, reason = validate_generated_content('src/main/webapp/WEB-INF/views/member/memberLogin.jsp', body, frontend_key='jsp')
    assert ok, reason
    assert is_auth_ui_file_path('src/main/webapp/WEB-INF/views/member/memberLogin.jsp') is True


def test_sensitive_non_auth_form_is_sanitized_but_member_login_is_preserved(tmp_path: Path) -> None:
    member_form = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberForm.jsp'
    member_form.parent.mkdir(parents=True, exist_ok=True)
    member_form.write_text('<form><input type="password" name="loginPassword"/><input type="text" name="memberName"/></form>', encoding='utf-8')

    member_login = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberLogin.jsp'
    member_login.write_text('<form><input type="password" name="loginPassword"/><input type="text" name="loginId"/></form>', encoding='utf-8')

    changed_form = _sanitize_frontend_ui_file(member_form, 'non-auth UI must not expose auth-sensitive fields such as password/login_password')
    changed_login = _sanitize_frontend_ui_file(member_login, 'non-auth UI must not expose auth-sensitive fields such as password/login_password')

    assert changed_form is True
    assert 'loginPassword' not in member_form.read_text(encoding='utf-8')
    assert changed_login is False
    assert 'loginPassword' in member_login.read_text(encoding='utf-8')


def test_rewrite_form_jsp_from_schema_keeps_sensitive_fields_for_shared_account_form(tmp_path: Path) -> None:
    rel = 'src/main/webapp/WEB-INF/views/member/memberForm.jsp'
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<html><body>broken</body></html>', encoding='utf-8')
    schema = schema_for(
        'Member',
        inferred_fields=[
            ('memberId', 'member_id', 'String'),
            ('loginId', 'login_id', 'String'),
            ('loginPassword', 'login_password', 'String'),
            ('memberName', 'member_name', 'String'),
        ],
        table='tb_member',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )

    changed = _rewrite_form_jsp_from_schema(tmp_path, rel, schema)
    body = path.read_text(encoding='utf-8')
    assert changed is True
    assert 'name="loginPassword"' in body
    assert 'type="password"' in body
    assert 'memberName' in body


def test_rewrite_form_jsp_from_schema_keeps_sensitive_fields_for_auth_form(tmp_path: Path) -> None:
    rel = 'src/main/webapp/WEB-INF/views/login/loginForm.jsp'
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<html><body>broken</body></html>', encoding='utf-8')
    schema = schema_for(
        'Login',
        inferred_fields=[
            ('loginId', 'login_id', 'String'),
            ('loginPassword', 'login_password', 'String'),
        ],
        table='tb_member',
        feature_kind=FEATURE_KIND_AUTH,
        strict_fields=True,
    )

    changed = _rewrite_form_jsp_from_schema(tmp_path, rel, schema)
    body = path.read_text(encoding='utf-8')
    assert changed is True
    assert 'name="loginPassword"' in body
    assert 'type="password"' in body


def test_login_list_alias_is_treated_as_auth_ui_path() -> None:
    from app.ui.ui_sanitize_common import is_auth_ui_file_path
    from app.ui.generated_content_validator import validate_generated_content

    path = 'src/main/webapp/WEB-INF/views/login/loginList.jsp'
    body = '<form><input type="password" name="loginPassword" /></form>'
    assert is_auth_ui_file_path(path) is True
    ok, err = validate_generated_content(path, body, frontend_key='jsp')
    assert ok, err
