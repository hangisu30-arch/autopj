from pathlib import Path

from app.validation.project_auto_repair import _repair_jsp_missing_route_reference, _repair_malformed_jsp_structure


def test_manage_jsp_missing_routes_are_rewritten_semantically(tmp_path: Path) -> None:
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/admin/memberManage.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '''<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>
<form action="<c:url value='/admin/member/update'/>" method="post">
  <input type="hidden" name="memberId" value="${item.memberId}" />
</form>
<a href="<c:url value='/admin/memberManage?searchId='/>${searchId}">조회</a>
''',
        encoding='utf-8',
    )

    changed = _repair_jsp_missing_route_reference(
        jsp,
        {
            'details': {
                'missing_routes': ['/admin/member/update', '/admin/memberManage?searchId='],
                'discovered_routes': ['/adminMember/list.do', '/adminMember/save.do', '/adminMember/detail.do'],
            }
        },
        tmp_path,
    )

    body = jsp.read_text(encoding='utf-8')
    assert changed is True
    assert "/adminMember/save.do" in body
    assert "/adminMember/list.do?searchId=" in body


def test_unbalanced_form_tags_are_balanced_for_manage_jsp(tmp_path: Path) -> None:
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/admin/memberManage.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '''<html><body>
<form action="/adminMember/save.do" method="post">
  <div>body</div>
</body></html>
''',
        encoding='utf-8',
    )

    changed = _repair_malformed_jsp_structure(jsp, {'message': 'jsp form tags are structurally unbalanced'}, tmp_path)

    body = jsp.read_text(encoding='utf-8')
    assert changed is True
    assert body.lower().count('<form') == 1
    assert body.lower().count('</form') == 1
