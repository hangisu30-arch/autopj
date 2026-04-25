from pathlib import Path

from app.io.execution_core_apply import _write_auth_database_initializer
from app.validation.post_generation_repair import _sanitize_frontend_ui_file
from app.ui.generated_content_validator import validate_generated_content


def test_login_initializer_uses_numeric_char_constants_and_no_regex_pattern(tmp_path: Path):
    out = _write_auth_database_initializer(tmp_path, "egovframework.test")
    body = out.read_text(encoding="utf-8")
    assert "private static final char CHAR_SINGLE_QUOTE = (char) 39;" in body
    assert "private static final char CHAR_DOUBLE_QUOTE = (char) 34;" in body
    assert "Pattern.compile(" not in body
    assert "if (ch == '\''" not in body


def test_sanitize_frontend_ui_file_removes_metadata_from_related_markup(tmp_path: Path):
    jsp = tmp_path / 'memberScheduleDetail.jsp'
    jsp.write_text(
        '<html>\n'
        '<div>${db}</div>\n'
        '<th>schemaName</th>\n'
        '<script>const tableName = "x"; const section = 1;</script>\n'
        '<p>packageName</p>\n'
        '</html>\n',
        encoding='utf-8',
    )
    assert _sanitize_frontend_ui_file(jsp, 'non-auth UI must not expose generation metadata fields such as db/schemaName/tableName/packageName')
    body = jsp.read_text(encoding='utf-8')
    ok, reason = validate_generated_content('src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleDetail.jsp', body, frontend_key='jsp')
    assert ok, reason
