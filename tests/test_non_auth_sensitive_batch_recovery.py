from pathlib import Path

from app.ui.generated_content_validator import validate_generated_content
from app.ui.ui_sanitize_common import sanitize_frontend_ui_text



def test_non_auth_sensitive_ui_text_can_be_sanitized_to_a_valid_jsp_fragment() -> None:
    path = 'src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleForm.jsp'
    raw = (
        '<label>비밀번호</label>\n'
        '<input type="password" name="password" value="${item.password}" />\n'
        '<input type="text" name="title" value="${item.title}" />\n'
    )

    ok, reason = validate_generated_content(path, raw, frontend_key='jsp')
    assert not ok and 'auth-sensitive' in reason

    cleaned = sanitize_frontend_ui_text(path, raw, reason)
    ok2, reason2 = validate_generated_content(path, cleaned, frontend_key='jsp')
    assert ok2, reason2
    assert 'password' not in cleaned.lower()
    assert 'name="title"' in cleaned.lower()



def test_main_window_batch_flow_contains_frontend_sanitize_recovery_hooks() -> None:
    source = Path('app/ui/main_window.py').read_text(encoding='utf-8')

    assert 'def _sanitize_invalid_frontend_content' in source
    assert 'sanitized invalid frontend content' in source
    assert 'sanitized regenerated frontend content' in source
    assert 'sanitized fallback frontend content' in source
    assert 'sanitize_frontend_ui_text(path, body, reason or "")' in source
