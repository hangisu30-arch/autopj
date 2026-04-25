from pathlib import Path

from app.io.execution_core_apply import _write_auth_database_initializer
from app.validation.post_generation_repair import _sanitize_related_frontend_ui_files
from app.ui.generated_content_validator import validate_generated_content


def test_login_initializer_generation_is_java11_safe_and_quote_safe(tmp_path: Path):
    out = _write_auth_database_initializer(tmp_path, 'egovframework.test')
    body = out.read_text(encoding='utf-8')
    assert 'parseAlterAddColumn' in body
    assert 'Pattern.compile(' not in body
    assert '"""' not in body
    assert 'int next = i + 1 < sql.length() ? sql.charAt(i + 1) : 0;' in body


def test_related_ui_sanitize_removes_metadata_across_domain_folder(tmp_path: Path):
    base = tmp_path / 'src/main/webapp/WEB-INF/views/memberSchedule'
    nested = base / 'admin'
    nested.mkdir(parents=True, exist_ok=True)
    payload = '\n'.join([
        '<!-- schemaName should not leak -->',
        '<tr><th>db</th><td>${memberSchedule.db}</td></tr>',
        '<script>const tableName = "member_schedule";</script>',
        '<input type="hidden" name="packageName" value="egovframework.test"/>',
        '<div>safe</div>',
    ])
    for path in [base / 'memberScheduleList.jsp', base / 'memberScheduleDetail.jsp', nested / 'memberScheduleForm.jsp']:
        path.write_text(payload, encoding='utf-8')
    changed = _sanitize_related_frontend_ui_files(
        tmp_path,
        'src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleList.jsp',
        'non-auth UI must not expose generation metadata fields such as db/schemaName/tableName/packageName',
    )
    assert len(changed) == 3
    for rel in changed:
        body = (tmp_path / rel).read_text(encoding='utf-8')
        ok, reason = validate_generated_content(rel, body, frontend_key='jsp')
        assert ok, reason
        assert 'safe' in body
