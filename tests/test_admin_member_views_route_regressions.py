from pathlib import Path

from app.validation.project_auto_repair import _repair_jsp_missing_route_reference, _is_membership_like_domain
from app.validation.generated_project_validator import validate_generated_project


class _Cfg:
    frontend_key = "jsp"
    database_key = "mysql"
    database_type = "mysql"


def test_membership_like_domain_includes_admin():
    assert _is_membership_like_domain("admin") is True
    assert _is_membership_like_domain("adminMember") is True


def test_route_repair_deletes_structural_views_crud_jsp(tmp_path: Path):
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/views/viewsList.jsp"
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text("<a href=\"<c:url value='/views/detail.do'/>\">x</a>", encoding="utf-8")
    assert _repair_jsp_missing_route_reference(jsp, {"details": {"missing_routes": ["/views/detail.do"]}}, tmp_path) is True
    assert not jsp.exists()


def test_validator_flags_structural_views_list_form_artifacts(tmp_path: Path):
    for name in ("viewsList.jsp", "viewsForm.jsp"):
        jsp = tmp_path / f"src/main/webapp/WEB-INF/views/views/{name}"
        jsp.parent.mkdir(parents=True, exist_ok=True)
        jsp.write_text("broken", encoding="utf-8")
    report = validate_generated_project(tmp_path, _Cfg(), manifest=None, include_runtime=False)
    messages = [issue.get("details", {}).get("message", "") for issue in report["issues"]]
    assert any("structural views directory must not contain CRUD jsp artifact" in m for m in messages)


def test_admin_jsp_missing_routes_trigger_safe_controller_rewrite(tmp_path: Path):
    controller = tmp_path / "src/main/java/egovframework/test/admin/web/AdminController.java"
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        "package egovframework.test.admin.web;\n"
        "import org.springframework.stereotype.Controller;\n"
        "import org.springframework.web.bind.annotation.GetMapping;\n"
        "import org.springframework.web.bind.annotation.RequestMapping;\n"
        "@Controller\n@RequestMapping(\"/admin\")\n"
        "public class AdminController {\n"
        "  @GetMapping(\"/manage.do\") public String manage(){ return \"admin/adminList\"; }\n"
        "}\n",
        encoding="utf-8",
    )
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/admin/adminList.jsp"
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        "<a href=\"<c:url value='/admin/delete.do'/>\">삭제</a>"
        "<a href=\"<c:url value='/admin/detail.do'/>\">상세</a>",
        encoding="utf-8",
    )
    issue = {"details": {"missing_routes": ["/admin/delete.do", "/admin/detail.do"], "discovered_routes": ["/admin/manage.do"]}}
    assert _repair_jsp_missing_route_reference(jsp, issue, tmp_path) is True
    controller_body = controller.read_text(encoding="utf-8")
    assert '/delete.do' in controller_body and '/detail.do' in controller_body and '/list.do' in controller_body
