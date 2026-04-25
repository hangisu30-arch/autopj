from pathlib import Path

from app.validation.project_auto_repair import _repair_jsp_missing_route_reference


def test_admin_jsp_missing_routes_create_safe_controller_when_absent(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/admin/adminList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        "<a href=\"<c:url value='/admin/delete.do'/>\">삭제</a>"
        "<a href=\"<c:url value='/admin/detail.do'/>\">상세</a>"
        "<a href=\"<c:url value='/admin/form.do'/>\">등록</a>",
        encoding='utf-8',
    )
    changed = _repair_jsp_missing_route_reference(
        jsp,
        {'details': {'missing_routes': ['/admin/delete.do', '/admin/detail.do', '/admin/form.do'], 'discovered_routes': []}},
        tmp_path,
    )
    assert changed is True
    controller = tmp_path / 'src/main/java/egovframework/app/admin/web/AdminController.java'
    body = controller.read_text(encoding='utf-8')
    assert '@RequestMapping("/admin")' in body or '@RequestMapping({"/admin"' in body
    assert '/delete.do' in body and '/detail.do' in body and '/list.do' in body and '/form.do' in body
