from pathlib import Path

from app.validation.project_auto_repair import (
    _repair_jsp_structural_views_artifact,
    _repair_route_param_mismatch,
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_admin_member_route_param_mismatch_rewrites_controller_and_jsp(tmp_path: Path):
    controller = tmp_path / "src/main/java/egovframework/test/adminMember/web/AdminMemberController.java"
    _write(
        controller,
        "package egovframework.test.adminMember.web;\n"
        "import org.springframework.stereotype.Controller;\n"
        "import org.springframework.ui.Model;\n"
        "import org.springframework.web.bind.annotation.*;\n"
        "@Controller\n@RequestMapping(\"/adminMember\")\n"
        "public class AdminMemberController {\n"
        "  @GetMapping(\"/detail.do\") public String detail(@RequestParam(\"id\") String id, Model model){ return \"adminMember/adminMemberDetail\"; }\n"
        "}\n",
    )
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/adminMember/adminMemberList.jsp"
    _write(
        jsp,
        '<a href="<c:url value="/member/detail.do"/>?id=${row.memberId}">상세</a>'
        '<form action="<c:url value="/member/delete.do"/>" method="post"><input type="hidden" name="id" value="${row.memberId}"/></form>',
    )
    changed = _repair_route_param_mismatch(
        controller,
        {"details": {"domain": "adminMember", "route_params": {"/adminMember/detail.do": "memberId", "/adminMember/delete.do": "memberId"}, "jsp_paths": ["src/main/webapp/WEB-INF/views/adminMember/adminMemberList.jsp"]}},
        tmp_path,
    )
    assert changed is True
    controller_body = controller.read_text(encoding="utf-8")
    assert '@RequestMapping("/adminMember")' in controller_body
    assert '@RequestParam(value = "memberId", required = false) String memberId' in controller_body
    body = jsp.read_text(encoding="utf-8")
    assert '/adminMember/detail.do' in body and '?memberId=' in body
    assert '/adminMember/delete.do' in body and 'name="memberId"' in body


def test_structural_views_issue_handler_deletes_crud_jsp(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/views/viewsDetail.jsp'
    _write(jsp, 'broken')
    assert _repair_jsp_structural_views_artifact(jsp, {}, tmp_path) is True
    assert not jsp.exists()
