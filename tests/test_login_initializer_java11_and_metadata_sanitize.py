from pathlib import Path

from app.io.execution_core_apply import _write_auth_database_initializer
from app.validation.post_generation_repair import _sanitize_frontend_ui_file


def test_login_initializer_is_java11_compatible(tmp_path: Path):
    path = _write_auth_database_initializer(tmp_path, 'egovframework.test')
    body = path.read_text(encoding='utf-8')
    assert '"""' not in body
    assert 'parseAlterAddColumn' in body
    assert 'int next = i + 1 < sql.length() ? sql.charAt(i + 1) : 0;' in body
    assert 'text blocks are not supported' not in body


def test_sanitize_frontend_ui_file_removes_metadata_lines_and_comments(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleForm.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '\n'.join([
            '<!-- schemaName should not leak -->',
            '<tr><th>db</th><td>${memberSchedule.db}</td></tr>',
            '<script>const tableName = "member_schedule";</script>',
            '<input type="hidden" name="packageName" value="egovframework.test"/>',
            '<div>safe</div>',
        ]),
        encoding='utf-8',
    )
    assert _sanitize_frontend_ui_file(jsp, 'non-auth UI must not expose generation metadata fields such as db/schemaName/tableName/packageName')
    body = jsp.read_text(encoding='utf-8')
    assert 'schemaName' not in body
    assert 'tableName' not in body
    assert 'packageName' not in body
    assert '<div>safe</div>' in body
