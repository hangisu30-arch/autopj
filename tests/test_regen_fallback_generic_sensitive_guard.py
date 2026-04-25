from app.ui.fallback_builder import build_builtin_fallback_content
from app.ui.generated_content_validator import validate_generated_content
from app.ui.ui_sanitize_common import repair_invalid_generated_content


def test_repair_invalid_generated_content_recovers_non_auth_ui_generically():
    path = 'src/main/webapp/WEB-INF/views/orders/ordersList.jsp'
    raw = '''<table><tr><th>login_password</th></tr><tr><td>${item.loginPassword}</td></tr></table>'''
    fixed, changed, ok, err = repair_invalid_generated_content(
        path,
        raw,
        'non-auth UI must not expose auth-sensitive fields such as password/login_password',
        frontend_key='jsp',
    )
    assert changed is True
    assert ok is True, err
    assert 'loginpassword' not in fixed.lower()


def test_repair_invalid_generated_content_does_not_strip_auth_login_ui():
    path = 'src/main/webapp/WEB-INF/views/account/accountLogin.jsp'
    raw = '<form><input type="password" name="loginPassword"/></form>'
    fixed, changed, ok, err = repair_invalid_generated_content(
        path,
        raw,
        'non-auth UI must not expose auth-sensitive fields such as password/login_password',
        frontend_key='jsp',
    )
    assert changed is False
    assert ok is False
    assert fixed == raw


def test_builtin_fallback_content_self_heals_non_auth_sensitive_list_view():
    path = 'src/main/webapp/WEB-INF/views/orders/ordersList.jsp'
    spec = '주문 목록 화면\n컬럼: order_id, title, login_password, password_hash, reg_dt'
    content = build_builtin_fallback_content(path, spec, project_name='demo')
    ok, reason = validate_generated_content(path, content, frontend_key='jsp')
    assert ok, reason
    assert 'login_password' not in content.lower()
    assert 'password_hash' not in content.lower()
