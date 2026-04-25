from pathlib import Path

from app.validation.generated_project_validator import _scan_malformed_jsp_structure
from app.validation.project_auto_repair import _repair_malformed_jsp_structure


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_repair_appends_missing_closing_form_before_body_end(tmp_path: Path) -> None:
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/custom/sample.jsp'
    _write(jsp, '<html><body><section><form action="/save.do" method="post"><input type="text" name="name"/></section></body></html>')

    issues = _scan_malformed_jsp_structure(tmp_path)
    issue = next(item for item in issues if item['path'].endswith('custom/sample.jsp'))
    assert 'structurally unbalanced' in (issue.get('message') or '')

    assert _repair_malformed_jsp_structure(jsp, issue, tmp_path)
    body = jsp.read_text(encoding='utf-8')
    assert body.count('<form') == body.count('</form>') == 1
    assert body.count('<section') == body.count('</section>') == 1
    assert body.index('</form>') < body.index('</body>')


def test_repair_closes_multiple_unclosed_tags_in_reverse_order(tmp_path: Path) -> None:
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/custom/nested.jsp'
    _write(jsp, '<html><body><div><form action="/save.do"><table><tr><td>ok</body></html>')

    issues = _scan_malformed_jsp_structure(tmp_path)
    issue = next(item for item in issues if item['path'].endswith('custom/nested.jsp'))
    assert _repair_malformed_jsp_structure(jsp, issue, tmp_path)

    body = jsp.read_text(encoding='utf-8')
    for tag in ('div', 'form', 'table', 'tr', 'td'):
        assert body.count(f'<{tag}') == body.count(f'</{tag}>') == 1
    assert body.index('</td></tr></table></form></div>') < body.index('</body>')
