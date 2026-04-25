from pathlib import Path

from app.io.execution_core_apply import _write_auth_database_initializer
from app.validation.post_generation_repair import _sanitize_frontend_ui_file
from app.ui.generated_content_validator import validate_generated_content


def test_login_database_initializer_uses_java11_safe_parse_logic(tmp_path: Path):
    out = _write_auth_database_initializer(tmp_path, 'egovframework.test')
    body = out.read_text(encoding='utf-8')
    assert 'parseAlterAddColumn' in body
    assert 'indexOfKeyword' in body
    assert 'Pattern.compile(' not in body
    assert 'text block' not in body.lower()


def test_jsp_metadata_sanitize_removes_generation_metadata_markers(tmp_path: Path):
    jsp = tmp_path / 'memberScheduleList.jsp'
    jsp.write_text(
        '<html>\n'
        '<!-- db schemaName tableName packageName -->\n'
        '<div>${db}</div>\n'
        '<script>const schemaName = "x";</script>\n'
        '<th>tableName</th>\n'
        '</html>\n',
        encoding='utf-8',
    )
    changed = _sanitize_frontend_ui_file(
        jsp,
        'non-auth UI must not expose generation metadata fields such as db/schemaName/tableName/packageName',
    )
    assert changed is True
    body = jsp.read_text(encoding='utf-8')
    ok, reason = validate_generated_content(
        'src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleList.jsp',
        body,
        frontend_key='jsp',
    )
    assert ok, reason
