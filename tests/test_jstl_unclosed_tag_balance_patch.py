from pathlib import Path

from app.ui.ui_sanitize_common import rebalance_markup_tags
from app.validation.generated_project_validator import _scan_malformed_jsp_structure
from app.validation.project_auto_repair import _repair_malformed_jsp_structure


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_validator_flags_unclosed_c_if_and_repair_closes_it(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberBroken.jsp'
    _write(
        jsp,
        '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>\n'
        '<div class="page-card">\n'
        '  <c:if test="${empty item}">\n'
        '    <div class="empty-state">조회된 데이터가 없습니다.</div>\n'
        '</div>\n',
    )

    issues = _scan_malformed_jsp_structure(tmp_path)
    issue = next(item for item in issues if item['path'].endswith('memberBroken.jsp'))
    assert 'unclosed c:if tag' in issue['message']

    changed = _repair_malformed_jsp_structure(jsp, issue, tmp_path)
    assert changed is True

    fixed = jsp.read_text(encoding='utf-8')
    assert fixed.count('<c:if') == fixed.count('</c:if>')
    assert '</c:if>' in fixed


def test_rebalance_markup_tags_closes_nested_jstl_and_html_blocks():
    body = '''<c:choose>
  <c:when test="${not empty list}">
    <div class="table-wrap">
      <table>
        <tbody>
          <c:forEach var="row" items="${list}">
            <tr>
              <td>
                <form action="/index/delete.do" method="post">
                  <button type="submit">삭제</button>
        </tbody>
  <c:otherwise>
    <div class="empty-state">조회된 데이터가 없습니다.</div>
</c:choose>
'''
    fixed = rebalance_markup_tags(body)

    for tag in ('c:choose', 'c:when', 'c:otherwise', 'c:forEach', 'div', 'table', 'tbody', 'tr', 'td', 'form'):
        assert fixed.count(f'<{tag}') == fixed.count(f'</{tag}>')

    assert '</form>' in fixed
    assert '</c:forEach>' in fixed
    assert '</c:when>' in fixed
    assert '</c:otherwise>' in fixed
