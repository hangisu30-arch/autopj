from app.ui.fallback_builder import build_builtin_fallback_content
from app.ui.generated_content_validator import validate_generated_content
from app.ui.ui_sanitize_common import sanitize_frontend_ui_text


def test_sanitize_frontend_ui_text_strips_sensitive_non_auth_markup_in_memory():
    path = "src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleList.jsp"
    raw = """<div class="safe">Title</div>
<label>Password</label><input type="text" name="password" value="${item.password}"/>
<tr><td>login_password</td><td>${item.loginPassword}</td></tr>"""
    cleaned = sanitize_frontend_ui_text(path, raw, 'non-auth UI must not expose auth-sensitive fields such as password/login_password')
    assert 'password' not in cleaned.lower()
    assert 'loginpassword' not in cleaned.lower()


def test_builtin_fallback_content_for_non_auth_jsp_is_sanitized_even_if_spec_mentions_password():
    path = 'src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleList.jsp'
    spec = '기존 로그인 테이블을 재활용한다\n컬럼: schedule_id, title, password, login_password, reg_dt'
    content = build_builtin_fallback_content(path, spec, project_name='demo')
    ok, reason = validate_generated_content(path, content, frontend_key='jsp')
    assert ok, reason
    assert 'name="password"' not in content.lower()
    assert 'name="loginpassword"' not in content.lower()


def test_auth_login_fallback_still_keeps_password_field():
    path = 'src/main/webapp/WEB-INF/views/login/loginForm.jsp'
    spec = '로그인 화면을 만든다\n컬럼: login_id, password'
    content = build_builtin_fallback_content(path, spec, project_name='demo')
    assert 'type="password"' in content.lower()
    ok, reason = validate_generated_content(path, content, frontend_key='jsp')
    assert ok, reason
