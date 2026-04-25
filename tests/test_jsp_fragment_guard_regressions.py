from pathlib import Path

from app.validation.generated_project_validator import _scan_malformed_jsp_structure
from app.validation.project_auto_repair import _repair_malformed_jsp_structure


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_validator_flags_orphan_jstl_and_empty_bindings_in_list_jsp(tmp_path: Path):
    _write(
        tmp_path / "src/main/webapp/WEB-INF/views/member/memberList.jsp",
        """<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<c:forEach var="row" items="${list}">
  <a href="<c:url value='/member/detail.do'/>?id="><c:out value=""/></a>
  <input name="insertDate" value="${param.insertDate}"/ type="date">
</c:forEach>
""",
    )

    issues = _scan_malformed_jsp_structure(tmp_path)
    messages = {issue["message"] for issue in issues}
    assert (
        "jsp contains empty output binding placeholder" in messages
        or "jsp contains malformed input tag attribute order" in messages
        or "jsp contains unresolved route parameter placeholder" in messages
    )


def test_common_css_partial_is_repaired_to_stylesheet_only(tmp_path: Path):
    _write(
        tmp_path / "src/main/webapp/WEB-INF/views/common/css.jsp",
        """<%@ include file="/WEB-INF/views/common/header.jsp" %>
<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>
""",
    )

    issues = _scan_malformed_jsp_structure(tmp_path)
    issue = next(i for i in issues if i["path"].endswith("common/css.jsp"))
    assert _repair_malformed_jsp_structure(tmp_path / issue["path"], issue, tmp_path)
    body = (tmp_path / "src/main/webapp/WEB-INF/views/common/css.jsp").read_text(encoding="utf-8")
    assert "common.css" in body
    assert "header.jsp" not in body
    assert "leftNav.jsp" not in body


def test_jwt_login_fragment_is_rebuilt_as_jwt_screen(tmp_path: Path):
    _write(
        tmp_path / "src/main/java/egovframework/test/login/web/JwtLoginController.java",
        """package egovframework.test.login.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.*;
@Controller @RequestMapping("/login")
public class JwtLoginController {
  @GetMapping("/jwtLogin.do") public String form(){ return "login/jwtLogin"; }
  @PostMapping("/actionJwtLogin.do") public String login(){ return "login/jwtLogin"; }
}
""",
    )
    _write(
        tmp_path / "src/main/webapp/WEB-INF/views/login/jwtLogin.jsp",
        """<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<!DOCTYPE html><html><body>
  <textarea><c:out value="${jwtToken}"/></textarea>
</c:if>
</body></html>
""",
    )

    issues = _scan_malformed_jsp_structure(tmp_path)
    issue = next(i for i in issues if i["path"].endswith("login/jwtLogin.jsp"))
    assert _repair_malformed_jsp_structure(tmp_path / issue["path"], issue, tmp_path)
    body = (tmp_path / "src/main/webapp/WEB-INF/views/login/jwtLogin.jsp").read_text(encoding="utf-8")
    assert "JWT 로그인" in body
    assert "/login/actionJwtLogin.do" in body
    assert '<textarea class="form-control"' in body
    assert "/WEB-INF/views/common/leftNav.jsp" in body
