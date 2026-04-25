from pathlib import Path

from app.io.execution_core_apply import _patch_generated_jsp_assets
from app.validation.generated_project_validator import _scan_unresolved_jsp_routes
from app.validation.project_auto_repair import _repair_jsp_missing_route_reference


class _BrokenIndexSchema:
    entity_var = "index"
    feature_kind = "CRUD"
    routes = {
        "list": "/index/list.do",
        "form": "/index/form.do",
    }


class _MemberSchema:
    entity_var = "member"
    feature_kind = "CRUD"
    routes = {
        "list": "/member/list.do",
        "form": "/member/form.do",
    }


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_patch_generated_jsp_assets_skips_missing_index_routes_in_common_nav(tmp_path: Path):
    _write(
        tmp_path / "src/main/java/egovframework/test/member/web/MemberController.java",
        "package egovframework.test.member.web;\n"
        "import org.springframework.stereotype.Controller;\n"
        "import org.springframework.web.bind.annotation.GetMapping;\n"
        "import org.springframework.web.bind.annotation.RequestMapping;\n"
        "@Controller\n"
        "@RequestMapping(\"/member\")\n"
        "public class MemberController {\n"
        "  @GetMapping(\"/list.do\") public String list(){ return \"member/memberList\"; }\n"
        "  @GetMapping(\"/form.do\") public String form(){ return \"member/memberForm\"; }\n"
        "}\n",
    )
    _write(
        tmp_path / "src/main/webapp/WEB-INF/views/member/memberList.jsp",
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n<html><body>ok</body></html>',
    )

    report = _patch_generated_jsp_assets(
        tmp_path,
        ["src/main/webapp/WEB-INF/views/member/memberList.jsp"],
        "Member",
        {"Index": _BrokenIndexSchema(), "Member": _MemberSchema()},
    )

    header = (tmp_path / report["header_jsp"]).read_text(encoding="utf-8")
    leftnav = (tmp_path / report["leftnav_jsp"]).read_text(encoding="utf-8")

    assert "/index/list.do" not in header
    assert "/index/list.do" not in leftnav
    assert "/member/list.do" in header or "/member/form.do" in header
    assert "/member/list.do" in leftnav or "/member/form.do" in leftnav


def test_common_layout_route_repair_rewrites_missing_index_list_route(tmp_path: Path):
    _write(
        tmp_path / "src/main/java/egovframework/test/member/web/MemberController.java",
        "package egovframework.test.member.web;\n"
        "import org.springframework.stereotype.Controller;\n"
        "import org.springframework.web.bind.annotation.GetMapping;\n"
        "import org.springframework.web.bind.annotation.RequestMapping;\n"
        "@Controller\n"
        "@RequestMapping(\"/member\")\n"
        "public class MemberController {\n"
        "  @GetMapping(\"/list.do\") public String list(){ return \"member/memberList\"; }\n"
        "}\n",
    )
    header_rel = "src/main/webapp/WEB-INF/views/common/header.jsp"
    leftnav_rel = "src/main/webapp/WEB-INF/views/common/leftNav.jsp"
    _write(tmp_path / header_rel, '<a href="<c:url value=\'/index/list.do\' />">홈</a>')
    _write(tmp_path / leftnav_rel, '<a href="<c:url value=\'/index/list.do\' />">메뉴</a>')

    issues = _scan_unresolved_jsp_routes(tmp_path)
    targets = [issue for issue in issues if issue["path"] in {header_rel, leftnav_rel}]
    assert len(targets) == 2

    for issue in targets:
        assert _repair_jsp_missing_route_reference(tmp_path / issue["path"], issue, tmp_path)

    assert not _scan_unresolved_jsp_routes(tmp_path)
    assert "/member/list.do" in (tmp_path / header_rel).read_text(encoding="utf-8")
    assert "/member/list.do" in (tmp_path / leftnav_rel).read_text(encoding="utf-8")
