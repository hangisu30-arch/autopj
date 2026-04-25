from app.validation.project_auto_repair import apply_generated_project_auto_repair
from pathlib import Path
from types import SimpleNamespace

from execution_core.builtin_crud import Schema, builtin_file
from app.io.execution_core_apply import (
    _rewrite_form_jsp_from_schema,
    _rewrite_detail_jsp_from_schema,
    _rewrite_list_jsp_from_schema,
)


def _sample_schema():
    return Schema(
        entity="Member",
        entity_var="member",
        table="member",
        id_prop="memberId",
        id_column="member_id",
        fields=[
            ("memberId", "member_id", "String"),
            ("memberName", "member_name", "String"),
            ("regDt", "reg_dt", "java.util.Date"),
        ],
        routes={
            "list": "/member/list.do",
            "detail": "/member/detail.do",
            "form": "/member/form.do",
            "save": "/member/save.do",
            "delete": "/member/delete.do",
        },
        views={},
    )


def test_builtin_jsp_templates_include_delete_ui():
    schema = _sample_schema()

    list_jsp = builtin_file("jsp/member/memberList.jsp", "egovframework.demo", schema)
    detail_jsp = builtin_file("jsp/member/memberDetail.jsp", "egovframework.demo", schema)
    form_jsp = builtin_file("jsp/member/memberForm.jsp", "egovframework.demo", schema)

    assert list_jsp is not None and "/member/delete.do" in list_jsp and "confirm('삭제하시겠습니까?')" in list_jsp
    assert detail_jsp is not None and "/member/delete.do" in detail_jsp and "삭제" in detail_jsp
    assert form_jsp is not None and "/member/delete.do" in form_jsp and "not empty item and not empty item.memberId" in form_jsp


def test_execution_core_apply_rewrites_add_delete_ui(tmp_path: Path):
    schema = SimpleNamespace(
        entity="Member",
        entity_var="member",
        id_prop="memberId",
        id_column="member_id",
        fields=[
            ("memberId", "member_id", "String"),
            ("memberName", "member_name", "String"),
            ("regDt", "reg_dt", "java.util.Date"),
        ],
        routes={
            "list": "/member/list.do",
            "detail": "/member/detail.do",
            "form": "/member/form.do",
            "save": "/member/save.do",
            "delete": "/member/delete.do",
        },
    )

    list_path = tmp_path / "src/main/webapp/WEB-INF/views/member/memberList.jsp"
    detail_path = tmp_path / "src/main/webapp/WEB-INF/views/member/memberDetail.jsp"
    form_path = tmp_path / "src/main/webapp/WEB-INF/views/member/memberForm.jsp"
    for p, body in [
        (list_path, "<html><body><ul><c:forEach var='row' items='${list}'></c:forEach></ul></body></html>"),
        (detail_path, "<html><body>detail</body></html>"),
        (form_path, "<html><body><form></form></body></html>"),
    ]:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    assert _rewrite_list_jsp_from_schema(tmp_path, str(list_path.relative_to(tmp_path)).replace("\\", "/"), schema)
    assert _rewrite_detail_jsp_from_schema(tmp_path, str(detail_path.relative_to(tmp_path)).replace("\\", "/"), schema)
    assert _rewrite_form_jsp_from_schema(tmp_path, str(form_path.relative_to(tmp_path)).replace("\\", "/"), schema)

    assert "/member/delete.do" in list_path.read_text(encoding="utf-8")
    assert "/member/delete.do" in detail_path.read_text(encoding="utf-8")
    assert "/member/delete.do" in form_path.read_text(encoding="utf-8")


def test_project_auto_repair_missing_delete_ui_repairs_jsp_from_controller_issue(tmp_path: Path):
    controller = tmp_path / "src/main/java/egovframework/demo/user/web/UserController.java"
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        "package egovframework.demo.user.web;\n"
        "import org.springframework.stereotype.Controller;\n"
        "import org.springframework.web.bind.annotation.PostMapping;\n"
        "import org.springframework.web.bind.annotation.RequestMapping;\n"
        "@Controller\n"
        "@RequestMapping(\"/user\")\n"
        "public class UserController {\n"
        "    @PostMapping(\"/delete.do\")\n"
        "    public String delete() { return \"redirect:/user/list.do\"; }\n"
        "}\n",
        encoding="utf-8",
    )
    list_jsp = tmp_path / "src/main/webapp/WEB-INF/views/user/userList.jsp"
    list_jsp.parent.mkdir(parents=True, exist_ok=True)
    list_jsp.write_text("<html><body><table></table></body></html>", encoding="utf-8")

    report = {
        "issues": [
            {
                "type": "missing_delete_ui",
                "path": "src/main/java/egovframework/demo/user/web/UserController.java",
                "repairable": True,
                "details": {"delete_routes": ["/user/delete.do"], "field": "userId"},
            }
        ]
    }

    result = apply_generated_project_auto_repair(tmp_path, report)

    assert result["changed_count"] == 1
    body = list_jsp.read_text(encoding="utf-8")
    assert "/user/delete.do" in body
    assert "삭제" in body
