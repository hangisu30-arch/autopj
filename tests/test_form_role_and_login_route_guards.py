from pathlib import Path

from app.validation.generated_project_validator import _analyze_form_structure, _jsp_screen_role, _discover_primary_login_route
from app.validation.project_auto_repair import _discover_primary_login_route as repair_discover_primary_login_route
from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_jsp_screen_role_treats_login_list_as_list_not_login(tmp_path: Path) -> None:
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/login/loginList.jsp"
    _write(jsp, "<html><body><a href='#'>목록</a></body></html>")
    assert _jsp_screen_role(jsp, jsp.read_text(encoding="utf-8")) == "list"


def test_analyze_form_structure_ignores_controls_inside_script_templates() -> None:
    body = (
        "<html><body>"
        "<form action='/save' method='post'><input name='loginId'/></form>"
        "<script>const tpl = '<input type=\"text\" name=\"ghost\" /><button type=\"button\">x</button>';</script>"
        "</body></html>"
    )
    flags = _analyze_form_structure(body)
    assert flags["control_outside_form"] is False
    assert flags["multiple_forms"] is False


def test_discover_primary_login_route_prefers_nested_login_do(tmp_path: Path) -> None:
    controller = tmp_path / "src/main/java/egovframework/test/login/web/LoginController.java"
    _write(
        controller,
        "package egovframework.test.login.web;\n"
        "import org.springframework.stereotype.Controller;\n"
        "import org.springframework.web.bind.annotation.*;\n"
        "@Controller\n"
        "@RequestMapping(\"/login\")\n"
        "public class LoginController {\n"
        "  @GetMapping(\"/login.do\") public String loginForm(){ return \"login/login\"; }\n"
        "}\n",
    )
    root_alias = tmp_path / "src/main/java/egovframework/test/root/web/RootController.java"
    _write(
        root_alias,
        "package egovframework.test.root.web;\n"
        "import org.springframework.stereotype.Controller;\n"
        "import org.springframework.web.bind.annotation.*;\n"
        "@Controller\n"
        "public class RootController {\n"
        "  @GetMapping(\"/login.do\") public String loginAlias(){ return \"redirect:/login/login.do\"; }\n"
        "}\n",
    )
    assert _discover_primary_login_route(tmp_path) == "/login/login.do"
    assert repair_discover_primary_login_route(tmp_path) == "/login/login.do"


def test_auth_interceptor_allows_root_login_alias() -> None:
    schema = schema_for("Login", feature_kind=FEATURE_KIND_AUTH)
    body = builtin_file("java/config/AuthLoginInterceptor.java", "egovframework.test.login", schema)
    assert 'path.equals("/login.do")' in body
    webmvc = builtin_file("java/config/WebMvcConfig.java", "egovframework.test.login", schema)
    assert '"/login.do"' in webmvc
