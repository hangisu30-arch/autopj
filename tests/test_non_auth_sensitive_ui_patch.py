from pathlib import Path

from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH, FEATURE_KIND_CRUD
from app.validation.post_generation_repair import _sanitize_frontend_ui_file


def test_builtin_crud_excludes_password_from_non_auth_jsp_ui() -> None:
    schema = schema_for(
        'MemberSchedule',
        inferred_fields=[
            ('scheduleId', 'schedule_id', 'String'),
            ('title', 'title', 'String'),
            ('password', 'password', 'String'),
            ('useYn', 'use_yn', 'String'),
        ],
        table='member_schedule',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )
    list_jsp = builtin_file('jsp/MemberScheduleList.jsp', 'egovframework.test', schema)
    form_jsp = builtin_file('jsp/MemberScheduleForm.jsp', 'egovframework.test', schema)
    mapper_xml = builtin_file('mapper/MemberScheduleMapper.xml', 'egovframework.test', schema)

    assert list_jsp is not None and 'password' not in list_jsp.lower()
    assert form_jsp is not None and 'name="password"' not in form_jsp.lower()
    assert mapper_xml is not None and 'password' in mapper_xml.lower()



def test_builtin_crud_keeps_password_for_auth_login_ui() -> None:
    schema = schema_for(
        'Login',
        inferred_fields=[
            ('loginId', 'login_id', 'String'),
            ('password', 'password', 'String'),
        ],
        table='member_account',
        feature_kind=FEATURE_KIND_AUTH,
        strict_fields=True,
    )
    login_jsp = builtin_file('jsp/LoginForm.jsp', 'egovframework.test', schema)

    assert login_jsp is not None
    assert 'type="password"' in login_jsp.lower()
    assert 'name="password"' in login_jsp.lower()



def test_sanitize_frontend_ui_file_strips_sensitive_non_auth_but_keeps_auth_ui(tmp_path: Path) -> None:
    non_auth = tmp_path / 'src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleForm.jsp'
    non_auth.parent.mkdir(parents=True, exist_ok=True)
    non_auth.write_text(
        '<label>비밀번호</label>\n<input type="password" name="password" value="${item.password}" />\n<input type="text" name="title" />\n',
        encoding='utf-8',
    )
    auth_ui = tmp_path / 'src/main/webapp/WEB-INF/views/login/loginForm.jsp'
    auth_ui.parent.mkdir(parents=True, exist_ok=True)
    auth_ui.write_text(
        '<label>비밀번호</label>\n<input type="password" name="password" value="" />\n',
        encoding='utf-8',
    )

    changed_non_auth = _sanitize_frontend_ui_file(non_auth, 'non-auth UI must not expose auth-sensitive fields such as password/login_password')
    changed_auth = _sanitize_frontend_ui_file(auth_ui, 'non-auth UI must not expose auth-sensitive fields such as password/login_password')

    non_auth_body = non_auth.read_text(encoding='utf-8').lower()
    auth_body = auth_ui.read_text(encoding='utf-8').lower()

    assert changed_non_auth is True
    assert 'password' not in non_auth_body
    assert 'name="title"' in non_auth_body
    assert changed_auth is False
    assert 'type="password"' in auth_body
