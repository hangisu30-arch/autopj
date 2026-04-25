from pathlib import Path

from app.io.execution_core_apply import _rewrite_form_jsp_from_schema
from app.ui.generated_content_validator import validate_generated_content
from app.ui.ui_sanitize_common import sanitize_frontend_ui_text
from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.feature_rules import FEATURE_KIND_CRUD


def _account_schema():
    return schema_for(
        'User',
        inferred_fields=[
            ('userId', 'user_id', 'String'),
            ('loginId', 'login_id', 'String'),
            ('loginPassword', 'login_password', 'String'),
            ('userName', 'user_name', 'String'),
            ('email', 'email', 'String'),
            ('phone', 'phone', 'String'),
            ('roleCd', 'role_cd', 'String'),
            ('useYn', 'use_yn', 'String'),
        ],
        table='tb_user',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )


def test_builtin_user_form_keeps_password_input_for_account_management_crud() -> None:
    form_jsp = builtin_file('jsp/user/userForm.jsp', 'egovframework.test', _account_schema())
    assert form_jsp is not None
    assert 'name="loginPassword"' in form_jsp
    assert 'type="password"' in form_jsp
    assert 'name="loginId"' in form_jsp


def test_rewrite_form_jsp_from_schema_keeps_password_input_for_user_account_form(tmp_path: Path) -> None:
    rel = 'src/main/webapp/WEB-INF/views/user/userForm.jsp'
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<html><body>broken</body></html>', encoding='utf-8')

    changed = _rewrite_form_jsp_from_schema(tmp_path, rel, _account_schema())
    body = path.read_text(encoding='utf-8')

    assert changed is True
    assert 'name="loginPassword"' in body
    assert 'type="password"' in body
    assert 'name="loginId"' in body


def test_validator_allows_password_input_for_user_account_form() -> None:
    body = '<form><input type="text" name="loginId"/><input type="password" name="loginPassword"/><input type="text" name="userName"/></form>'
    ok, reason = validate_generated_content('src/main/webapp/WEB-INF/views/user/userForm.jsp', body, frontend_key='jsp')
    assert ok, reason


def test_sanitize_preserves_password_input_for_user_account_form() -> None:
    original = '<form><input type="text" name="loginId"/><input type="password" name="loginPassword"/><input type="text" name="userName"/></form>'
    cleaned = sanitize_frontend_ui_text('src/main/webapp/WEB-INF/views/user/userForm.jsp', original, 'non-auth UI must not expose auth-sensitive fields such as password/login_password')
    assert cleaned == original
