from pathlib import Path
from types import SimpleNamespace

from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def test_login_list_alias_is_rewritten_to_login_page(tmp_path: Path):
    _write(tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java', """package egovframework.test.login.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class LoginController {
    @GetMapping("/login/login.do")
    public String login() { return "login/login"; }
}
""")
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/login/loginList.jsp', """<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<a href="<c:url value='/login/detail.do'/>">상세</a>
<a href="<c:url value='/login/form.do'/>">등록</a>
<a href="<c:url value='/login/delete.do'/>">삭제</a>
""")

    report = validate_generated_project(tmp_path, SimpleNamespace(frontend_key='jsp'), run_runtime=False)
    issues = [i for i in report.get('issues', []) if i['path'].endswith('login/loginList.jsp')]
    assert any(i['code'] == 'jsp_missing_route_reference' for i in issues)

    repaired = apply_generated_project_auto_repair(tmp_path, report)
    assert repaired['changed']
    body = (tmp_path / 'src/main/webapp/WEB-INF/views/login/loginList.jsp').read_text(encoding='utf-8').lower()
    assert 'type="password"' in body or "type='password'" in body
    assert '/login/detail.do' not in body
    assert '/login/form.do' not in body
    assert '/login/delete.do' not in body


def test_generation_path_repair_uses_login_template_for_auth_alias_collections():
    from app.io.execution_core_apply import _repair_content_by_path
    from execution_core.builtin_crud import schema_for
    from execution_core.feature_rules import FEATURE_KIND_AUTH

    schema = schema_for('Login', inferred_fields=[('loginId', 'login_id', 'String'), ('loginPassword', 'login_password', 'String')], table='login', feature_kind=FEATURE_KIND_AUTH)
    content = '<a href="/login/detail.do">상세</a>'
    out = _repair_content_by_path('src/main/webapp/WEB-INF/views/login/loginList.jsp', content, 'egovframework.test', preferred_entity='Login', schema_map={'Login': schema})
    low = out.lower()
    assert 'type="password"' in low or "type='password'" in low
    assert '/login/detail.do' not in low and '/login/form.do' not in low and '/login/delete.do' not in low
    assert '/login/actionlogin.do' in low or '/login/login.do' in low
