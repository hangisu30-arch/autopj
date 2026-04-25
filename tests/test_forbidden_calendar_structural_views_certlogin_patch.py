from pathlib import Path

from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import _repair_jsp_missing_route_reference, _repair_malformed_jsp_structure


class _Cfg:
    frontend_key = "jsp"
    database_key = "mysql"
    database_type = "mysql"


def test_validator_flags_forbidden_user_calendar_and_structural_views(tmp_path: Path):
    (tmp_path / "src/main/java/egovframework/test/user/service/vo").mkdir(parents=True, exist_ok=True)
    (tmp_path / "src/main/java/egovframework/test/user/service/vo/UserVO.java").write_text(
        "package egovframework.test.user.service.vo; public class UserVO { private String userId; public String getUserId(){return userId;} }",
        encoding="utf-8",
    )
    user_cal = tmp_path / "src/main/webapp/WEB-INF/views/user/userCalendar.jsp"
    user_cal.parent.mkdir(parents=True, exist_ok=True)
    user_cal.write_text('<c:out value="${item.regDt}"/>', encoding="utf-8")
    views_list = tmp_path / "src/main/webapp/WEB-INF/views/views/viewsList.jsp"
    views_list.parent.mkdir(parents=True, exist_ok=True)
    views_list.write_text("<a href=\"<c:url value='/views/list.do'/>\">x</a>", encoding="utf-8")
    report = validate_generated_project(tmp_path, _Cfg(), manifest=None, include_runtime=False)
    messages = [i.get("details", {}).get("message", "") for i in report["issues"]]
    assert any("forbidden calendar jsp generated" in m for m in messages)
    assert any("structural views directory must not contain CRUD jsp artifact" in m for m in messages)


def test_missing_route_repair_deletes_structural_views_artifact(tmp_path: Path):
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/views/viewsList.jsp"
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text("broken", encoding="utf-8")
    assert _repair_jsp_missing_route_reference(jsp, {"details": {"missing_routes": ["/views/list.do"]}}, tmp_path) is True
    assert not jsp.exists()


def test_malformed_certlogin_rerenders_balanced_form(tmp_path: Path):
    (tmp_path / "src/main/java/egovframework/test/login/web").mkdir(parents=True, exist_ok=True)
    controller = tmp_path / "src/main/java/egovframework/test/login/web/LoginController.java"
    controller.write_text(
        'package egovframework.test.login.web; '
        'import org.springframework.stereotype.Controller; '
        'import org.springframework.web.bind.annotation.GetMapping; '
        'import org.springframework.web.bind.annotation.RequestMapping; '
        '@Controller @RequestMapping("/login") '
        'public class LoginController { '
        '@GetMapping("/certLogin.do") public String form(){ return "login/certLogin"; } '
        '}',
        encoding="utf-8",
    )
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/login/certLogin.jsp"
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('</form><c:if test="${empty item}"><div>x</div>', encoding="utf-8")
    assert _repair_malformed_jsp_structure(jsp, {"type": "malformed_jsp_structure"}, tmp_path) is True
    body = jsp.read_text(encoding="utf-8")
    assert body.count("<form") == body.count("</form>") == 1
    assert body.count("<c:if") == body.count("</c:if>")
    assert "actionCertLogin.do" in body
