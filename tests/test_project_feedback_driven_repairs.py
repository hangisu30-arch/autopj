from pathlib import Path

from app.validation.generated_project_validator import _scan_malformed_jsp_structure, _scan_unresolved_jsp_routes
from app.validation.project_auto_repair import (
    _repair_jsp_dependency_missing,
    _repair_jsp_missing_route_reference,
    _repair_malformed_jsp_structure,
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _seed_project(root: Path) -> None:
    _write(
        root / "src/main/java/egovframework/test/login/web/LoginController.java",
        "package egovframework.test.login.web;\n"
        "import org.springframework.stereotype.Controller;\n"
        "import org.springframework.web.bind.annotation.*;\n"
        "@Controller\n"
        "@RequestMapping(\"/login\")\n"
        "public class LoginController {\n"
        "  @GetMapping(\"/login.do\") public String form(){ return \"login/login\"; }\n"
        "}\n",
    )
    _write(
        root / "src/main/java/egovframework/test/member/web/MemberController.java",
        "package egovframework.test.member.web;\n"
        "import org.springframework.stereotype.Controller;\n"
        "import org.springframework.web.bind.annotation.*;\n"
        "@Controller\n"
        "@RequestMapping(\"/member\")\n"
        "public class MemberController {\n"
        "  @GetMapping(\"/list.do\") public String list(){ return \"member/memberList\"; }\n"
        "  @GetMapping(\"/detail.do\") public String detail(){ return \"member/memberDetail\"; }\n"
        "  @GetMapping(\"/form.do\") public String form(){ return \"member/memberForm\"; }\n"
        "  @PostMapping(\"/save.do\") public String save(){ return \"redirect:/member/list.do\"; }\n"
        "  @PostMapping(\"/delete.do\") public String delete(){ return \"redirect:/member/list.do\"; }\n"
        "}\n",
    )
    _write(
        root / "src/main/java/egovframework/test/member/service/vo/MemberVO.java",
        "package egovframework.test.member.service.vo;\n"
        "public class MemberVO {\n"
        "  private String loginId;\n"
        "  private String memberName;\n"
        "  private String memberStatusCd;\n"
        "  public String getLoginId(){ return loginId; }\n"
        "  public void setLoginId(String v){ this.loginId=v; }\n"
        "  public String getMemberName(){ return memberName; }\n"
        "  public void setMemberName(String v){ this.memberName=v; }\n"
        "  public String getMemberStatusCd(){ return memberStatusCd; }\n"
        "  public void setMemberStatusCd(String v){ this.memberStatusCd=v; }\n"
        "}\n",
    )
    _write(
        root / "src/main/webapp/WEB-INF/views/common/header.jsp",
        '<a href="<c:url value=\'/login.do\' />">로그인</a>',
    )
    _write(
        root / "src/main/webapp/WEB-INF/views/common/leftNav.jsp",
        '<a href="<c:url value=\'/login.do\' />">로그인</a>',
    )
    _write(
        root / "src/main/webapp/WEB-INF/views/member/memberList.jsp",
        '<%@ include file="/WEB-INF/views/common/header.jsp" %>\n'
        '<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>\n'
        '</div>\n'
        '<form action="<c:url value=\'/member/delete.do\'/>" method="post">\n'
        '  <div class="autopj-search-fields"><input name="memberName"/></div>\n'
        '</form>\n',
    )
    _write(
        root / "src/main/webapp/WEB-INF/views/member/memberDetail.jsp",
        '<%@ include file="/WEB-INF/views/common/header.jsp" %>\n'
        '<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>\n'
        '</div>\n',
    )
    _write(
        root / "src/main/webapp/WEB-INF/views/member/memberSignup.jsp",
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<script>$.ajax({url: "${pageContext.request.contextPath}/member/checkIdDupl"});</script>\n'
        '<body>\n'
        '<%@ include file="/WEB-INF/views/common/header.jsp" %>\n'
        '<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>\n'
        '<form action="${pageContext.request.contextPath}/member/signup" method="post">\n'
        '  <input type="text" name="id"/>\n'
        '  <input type="password" name="pw"/>\n'
        '</form>\n'
        '</body>\n',
    )


def test_validator_detects_feedback_patterns_from_generated_project(tmp_path: Path):
    _seed_project(tmp_path)

    malformed = _scan_malformed_jsp_structure(tmp_path)
    malformed_paths = {item["path"] for item in malformed}
    assert "src/main/webapp/WEB-INF/views/member/memberList.jsp" in malformed_paths
    assert "src/main/webapp/WEB-INF/views/member/memberDetail.jsp" in malformed_paths

    route_issues = _scan_unresolved_jsp_routes(tmp_path)
    kinds_and_paths = {(item["type"], item["path"]) for item in route_issues}
    assert ("jsp_missing_route_reference", "src/main/webapp/WEB-INF/views/common/header.jsp") in kinds_and_paths
    assert ("jsp_missing_route_reference", "src/main/webapp/WEB-INF/views/common/leftNav.jsp") in kinds_and_paths
    assert ("jsp_missing_route_reference", "src/main/webapp/WEB-INF/views/member/memberSignup.jsp") in kinds_and_paths
    assert ("jsp_dependency_missing", "src/main/webapp/WEB-INF/views/member/memberSignup.jsp") in kinds_and_paths


def test_repair_flow_normalizes_nav_signup_and_malformed_member_views(tmp_path: Path):
    _seed_project(tmp_path)

    for issue in _scan_unresolved_jsp_routes(tmp_path):
        path = tmp_path / issue["path"]
        if issue["type"] == "jsp_missing_route_reference":
            assert _repair_jsp_missing_route_reference(path, issue, tmp_path)
        elif issue["type"] == "jsp_dependency_missing":
            assert _repair_jsp_dependency_missing(path, issue, tmp_path)

    for issue in _scan_malformed_jsp_structure(tmp_path):
        assert _repair_malformed_jsp_structure(tmp_path / issue["path"], issue, tmp_path)

    header = (tmp_path / "src/main/webapp/WEB-INF/views/common/header.jsp").read_text(encoding="utf-8")
    leftnav = (tmp_path / "src/main/webapp/WEB-INF/views/common/leftNav.jsp").read_text(encoding="utf-8")
    signup = (tmp_path / "src/main/webapp/WEB-INF/views/member/memberSignup.jsp").read_text(encoding="utf-8")

    assert "/login/login.do" in header
    assert "/login/login.do" in leftnav
    assert "/member/save.do" in signup
    assert "/member/signup" not in signup
    assert "/member/checkIdDupl" not in signup
    assert "$.ajax" not in signup
    assert not _scan_malformed_jsp_structure(tmp_path)
    assert not _scan_unresolved_jsp_routes(tmp_path)
