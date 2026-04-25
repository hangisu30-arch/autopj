from pathlib import Path

from app.validation.project_auto_repair import (
    _repair_jsp_missing_route_reference,
    _repair_route_param_mismatch,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_repair_route_param_mismatch_normalizes_tbmember_controller_to_member(tmp_path: Path):
    controller = tmp_path / "src/main/java/egovframework/test/tbMember/web/TbMemberController.java"
    _write(
        controller,
        "package egovframework.test.tbMember.web;\n"
        "import org.springframework.stereotype.Controller;\n"
        "import org.springframework.ui.Model;\n"
        "import org.springframework.web.bind.annotation.*;\n"
        "@Controller\n@RequestMapping(\"/tbMember\")\n"
        "public class TbMemberController {\n"
        "  @GetMapping(\"/detail.do\") public String detail(@RequestParam(\"id\") String id, Model model){ return \"tbMember/tbMemberDetail\"; }\n"
        "}\n",
    )
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/tbMember/tbMemberDetail.jsp"
    _write(jsp, '<a href="<c:url value="/member/detail.do"/>?memberId=1">상세</a>')

    changed = _repair_route_param_mismatch(
        controller,
        {
            "details": {
                "domain": "tbMember",
                "route_params": {"/tbMember/detail.do": "id"},
            }
        },
        tmp_path,
    )

    assert changed is True
    controller_body = controller.read_text(encoding="utf-8")
    assert '@RequestMapping("/member")' in controller_body
    assert 'return "member/memberDetail";' in controller_body


def test_repair_jsp_missing_route_reference_rewrites_tbmember_controller_from_member_view(tmp_path: Path):
    controller = tmp_path / "src/main/java/egovframework/test/tbMember/web/TbMemberController.java"
    _write(
        controller,
        "package egovframework.test.tbMember.web;\n"
        "import org.springframework.stereotype.Controller;\n"
        "import org.springframework.web.bind.annotation.*;\n"
        "@Controller\n@RequestMapping(\"/tbMember\")\n"
        "public class TbMemberController {\n"
        "  @GetMapping(\"/list.do\") public String list(){ return \"tbMember/tbMemberList\"; }\n"
        "}\n",
    )
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/member/memberList.jsp"
    _write(
        jsp,
        '<a href="<c:url value="/member/form.do"/>">form</a>'
        '<a href="<c:url value="/member/detail.do"/>">detail</a>'
        '<a href="<c:url value="/member/delete.do"/>">delete</a>',
    )

    changed = _repair_jsp_missing_route_reference(
        jsp,
        {
            "details": {
                "missing_routes": ["/member/form.do", "/member/detail.do", "/member/delete.do"],
                "discovered_routes": ["/tbMember/list.do"],
            }
        },
        tmp_path,
    )

    assert changed is True
    controller_body = controller.read_text(encoding="utf-8")
    assert '@RequestMapping("/member")' in controller_body
    assert 'return "member/memberList";' in controller_body
