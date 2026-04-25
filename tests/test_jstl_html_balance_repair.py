from pathlib import Path

from app.ui.ui_sanitize_common import sanitize_frontend_ui_text
from app.validation.generated_project_validator import _scan_malformed_jsp_structure
from app.validation.project_auto_repair import _repair_malformed_jsp_structure


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_validator_flags_unclosed_c_if_tag(tmp_path: Path) -> None:
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/member/memberList.jsp',
        '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>\n<c:if test="${not empty list}"><div>ok</div>'
    )
    issues = _scan_malformed_jsp_structure(tmp_path)
    messages = {issue['message'] for issue in issues}
    assert 'jsp contains unclosed c:if tag' in messages


def test_auto_repair_balances_jstl_and_html_tags_from_broken_list_markup(tmp_path: Path) -> None:
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/member/memberList.jsp',
        '''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<c:choose>
  <c:when test="${not empty list}">
    <div class="table-wrap autopj-record-grid">
      <table class="data-table autopj-data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>사용 여부</th><th>Reg Dt</th>
            <th>작업</th>
        </thead>
        <tbody>
          <c:forEach var="row" items="${list}">
            <tr>
              <td><a href="<c:url value='/index/detail.do'/>?name=${row.name}"><c:out value="${row.name}"/></a></td>
              <td><c:out value="${row.useYn}"/></td>
              <td><c:out value="${row.regDt}"/></td>
              <td>
                <div class="action-bar">
                <a class="btn btn-light" href="<c:url value='/index/detail.do'/>?name=${row.name}">상세</a>
                <a class="btn btn-light" href="<c:url value='/index/form.do'/>?name=${row.name}">수정</a>
                <form action="<c:url value='/index/delete.do'/>" method="post" style="display:inline-flex;margin:0;">
                  <input type="hidden" name="name" value="${row.name}"/>
                  <button type="submit" onclick="return confirm('삭제하시겠습니까?');">삭제</button>
        </tbody>
  <c:otherwise>
''',
    )
    issues = _scan_malformed_jsp_structure(tmp_path)
    issue = next(i for i in issues if i['path'].endswith('member/memberList.jsp'))
    assert _repair_malformed_jsp_structure(tmp_path / issue['path'], issue, tmp_path)
    body = (tmp_path / 'src/main/webapp/WEB-INF/views/member/memberList.jsp').read_text(encoding='utf-8')
    assert body.count('<c:choose') == body.count('</c:choose>') == 1
    assert body.count('<c:when') == body.count('</c:when>') == 1
    assert body.count('<c:otherwise>') == body.count('</c:otherwise>') == 1
    assert body.count('<c:forEach') == body.count('</c:forEach>') == 1
    assert body.count('<form ') == body.count('</form>')
    import re
    assert len(re.findall(r'<div\b', body)) == body.count('</div>')
    assert body.count('<table ') == body.count('</table>') == 1
    assert body.count('<tbody>') == body.count('</tbody>') == 1


def test_sanitize_balances_orphaned_jstl_and_form_tags() -> None:
    body = '<c:if test="${not empty item}"><form><div>${schemaName}</div>'
    sanitized = sanitize_frontend_ui_text('src/main/webapp/WEB-INF/views/member/memberDetail.jsp', body, 'non-auth UI must not expose generation metadata fields such as db/schemaName/tableName/packageName')
    assert '${schemaName}' not in sanitized
    assert sanitized.count('<c:if') == sanitized.count('</c:if>') == 1
    assert sanitized.count('<form') == sanitized.count('</form>') == 1
    assert sanitized.count('<div') == sanitized.count('</div>')
