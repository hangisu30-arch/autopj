from pathlib import Path
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def test_main_window_source_sanitizes_regen_and_fallback_content() -> None:
    source = Path('app/ui/main_window.py').read_text(encoding='utf-8')
    assert '_sanitize_generated_frontend_content(path, one.get("content", ""), errc)' in source
    assert '_sanitize_generated_frontend_content(path, one.get("content", ""), errc2)' in source
    assert '_sanitize_generated_frontend_content(path, fallback_content, errc2)' in source


def test_in_memory_sanitizer_strips_sensitive_non_auth_content() -> None:
    try:
        from app.ui.main_window import _sanitize_generated_frontend_content
        from app.ui.generated_content_validator import validate_generated_content
    except ModuleNotFoundError:
        source = Path('app/ui/main_window.py').read_text(encoding='utf-8')
        assert 'def _sanitize_generated_frontend_content(' in source
        return

    path = 'src/main/webapp/WEB-INF/views/member/memberForm.jsp'
    raw = '<form><input type="password" name="loginPassword"/><input type="text" name="memberName"/></form>'
    ok, reason = validate_generated_content(path, raw, frontend_key='jsp')
    assert not ok and 'auth-sensitive' in reason

    cleaned = _sanitize_generated_frontend_content(path, raw, reason)
    ok2, reason2 = validate_generated_content(path, cleaned, frontend_key='jsp')
    assert ok2, reason2
    assert 'loginpassword' not in cleaned.lower()
    assert 'membername' in cleaned.lower()


def test_in_memory_sanitizer_keeps_auth_login_content() -> None:
    try:
        from app.ui.main_window import _sanitize_generated_frontend_content
    except ModuleNotFoundError:
        source = Path('app/ui/main_window.py').read_text(encoding='utf-8')
        assert 'def _sanitize_generated_frontend_content(' in source
        return

    path = 'src/main/webapp/WEB-INF/views/member/memberLogin.jsp'
    raw = '<form><input type="password" name="loginPassword"/><input type="text" name="loginId"/></form>'
    cleaned = _sanitize_generated_frontend_content(path, raw, 'non-auth UI must not expose auth-sensitive fields such as password/login_password')
    assert cleaned == raw
