from pathlib import Path
from types import SimpleNamespace

from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair
from execution_core.builtin_crud import infer_schema_from_plan


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_validator_repairs_unresolved_jsp_routes_against_existing_controller_mappings(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/demo/login/web/LoginController.java',
        '''package egovframework.demo.login.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
@Controller
@RequestMapping("/login")
public class LoginController {
    @GetMapping("/login.do")
    public String form() { return "login/login"; }
}
''',
    )
    header = tmp_path / 'src/main/webapp/WEB-INF/views/common/header.jsp'
    _write(
        header,
        '''<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<a class="nav-link" href="<c:url value='/login/integratedCallback.do' />">로그인</a>
''',
    )

    report = validate_generated_project(tmp_path, SimpleNamespace(frontend_key='jsp'), include_runtime=False, run_runtime=False)
    issue_types = {item['type'] for item in report['static_issues']}
    assert 'jsp_route_resolution' in issue_types

    repair = apply_generated_project_auto_repair(tmp_path, report)
    assert repair['changed_count'] >= 1
    body = header.read_text(encoding='utf-8')
    assert "/login/login.do" in body
    assert "/login/integratedCallback.do" not in body


def test_validator_repairs_jsp_head_body_misplacement_and_form_imbalance(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/demo/member/web/MemberController.java',
        '''package egovframework.demo.member.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
@Controller
@RequestMapping("/member")
public class MemberController {
    @GetMapping("/form.do")
    public String form() { return "member/memberSignup"; }
    @PostMapping("/save.do")
    public String save() { return "redirect:/login/login.do"; }
}
''',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/demo/login/web/LoginController.java',
        '''package egovframework.demo.login.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
@Controller
@RequestMapping("/login")
public class LoginController {
    @GetMapping("/login.do")
    public String form() { return "login/login"; }
}
''',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberSignup.jsp'
    _write(
        jsp,
        '''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<!DOCTYPE html>
<html>
<head>
<title>회원가입</title>
<div class="card-body">
<label for="loginId">아이디</label>
<input type="text" id="loginId" name="loginId"/>
<button type="submit">가입</button>
</div>
</head>
<body>
</form>
</body>
</html>
''',
    )

    report = validate_generated_project(tmp_path, SimpleNamespace(frontend_key='jsp'), include_runtime=False, run_runtime=False)
    issue_types = {item['type'] for item in report['static_issues']}
    assert 'jsp_form_tag_imbalance' in issue_types
    assert 'jsp_head_body_misplacement' in issue_types

    repair = apply_generated_project_auto_repair(tmp_path, report)
    assert repair['changed_count'] >= 1
    body = jsp.read_text(encoding='utf-8')
    assert body.lower().count('<form') == body.lower().count('</form>')
    head = body.lower().split('</head>')[0]
    assert '<input' not in head
    assert '/member/save.do' in body


def test_linked_signup_login_contract_augments_userish_schema_with_auth_fields():
    plan = {
        'requirements': '''기존 로그인과 연동되는 회원가입 기능을 만든다.
회원가입을 하면 기존 로그인으로 바로 로그인해야 한다.
테이블명은 members 이고 컬럼이 부족하면 추가해야 한다.
회원가입 화면과 회원관리도 같이 필요하다.
''',
        'tasks': [],
    }
    schema = infer_schema_from_plan(plan)
    columns = {col for _prop, col, _jt in schema.fields}
    assert schema.table == 'members'
    assert 'login_id' in columns
    assert 'password' in columns
    assert 'use_yn' in columns
