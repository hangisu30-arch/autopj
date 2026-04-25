from pathlib import Path

from app.validation.project_auto_repair import _repair_jsp_missing_route_reference, _repair_jsp_vo_property_mismatch, _infer_schema_for_jsp_repair


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_infer_schema_for_top_level_user_form_uses_filename_domain(tmp_path: Path) -> None:
    _write(
        tmp_path / "src/main/java/egovframework/test/user/service/vo/UserVO.java",
        "package egovframework.test.user.service.vo;\npublic class UserVO { private String user_id; private String user_name; }\n",
    )
    schema = _infer_schema_for_jsp_repair(tmp_path / "src/main/webapp/WEB-INF/views/UserForm.jsp", tmp_path)
    cols = [col for _prop, col, _jt in schema.fields]
    assert schema.entity.lower() == 'user'
    assert 'user_name' in cols


def test_repair_jsp_vo_property_mismatch_rewrites_top_level_login_form_as_auth_login(tmp_path: Path) -> None:
    _write(
        tmp_path / "src/main/java/egovframework/test/login/service/vo/LoginVO.java",
        "package egovframework.test.login.service.vo;\npublic class LoginVO { private String login_id; private String password; private String approval_status; }\n",
    )
    _write(
        tmp_path / "src/main/java/egovframework/test/login/web/LoginController.java",
        "package egovframework.test.login.web;\nimport org.springframework.stereotype.Controller;\nimport org.springframework.web.bind.annotation.*;\n@Controller @RequestMapping(\"/login\") public class LoginController { @GetMapping(\"/login.do\") public String login(){ return \"login/login\"; } @PostMapping(\"/process.do\") public String process(){ return \"redirect:/login/login.do\"; } }\n",
    )
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/LoginForm.jsp"
    _write(jsp, "<html>${item.name}<form action=\"<c:url value=\'/views/save.do\'/>\"></form></html>")
    changed = _repair_jsp_vo_property_mismatch(jsp, {"details": {"missing_props": ["name"]}}, tmp_path)
    body = jsp.read_text(encoding='utf-8')
    assert changed is True
    assert 'name="password"' in body and '/views/save.do' not in body
    assert '/views/save.do' not in body
    assert '${item.name}' not in body


def test_repair_jsp_missing_route_reference_rewrites_top_level_user_form_to_user_routes(tmp_path: Path) -> None:
    _write(
        tmp_path / "src/main/java/egovframework/test/user/service/vo/UserVO.java",
        "package egovframework.test.user.service.vo;\npublic class UserVO { private String user_id; private String login_id; private String user_name; }\n",
    )
    _write(
        tmp_path / "src/main/java/egovframework/test/user/web/UserController.java",
        "package egovframework.test.user.web;\nimport org.springframework.stereotype.Controller;\nimport org.springframework.web.bind.annotation.*;\n@Controller @RequestMapping(\"/user\") public class UserController { @GetMapping(\"/form.do\") public String form(){ return \"UserForm\"; } @PostMapping(\"/save.do\") public String save(){ return \"redirect:/user/list.do\"; } @GetMapping(\"/list.do\") public String list(){ return \"UserList\"; } }\n",
    )
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/UserForm.jsp"
    _write(jsp, "<form action=\"<c:url value='/views/save.do'/>\"></form><a href=\"<c:url value='/views/list.do'/>\">목록</a>")
    changed = _repair_jsp_missing_route_reference(
        jsp,
        {"details": {"missing_routes": ["/views/save.do", "/views/list.do"], "discovered_routes": ["/user/form.do", "/user/save.do", "/user/list.do"]}},
        tmp_path,
    )
    body = jsp.read_text(encoding='utf-8')
    assert changed is True
    assert '/user/save.do' in body
    assert '/user/list.do' in body
    assert '/views/save.do' not in body
