from pathlib import Path

from app.validation.backend_compile_repair import enforce_generated_project_invariants
from app.validation.project_auto_repair import (
    _auth_alias_kind_for_jsp_path,
    _repair_jsp_missing_route_reference,
    _repair_malformed_jsp_structure,
)
from app.validation.generated_project_validator import _scan_malformed_jsp_structure


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_login_folder_signup_jsp_is_classified_as_signup_and_repaired(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java',
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @GetMapping("/login.do") public String form(){ return "login/login"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java',
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/member")\n'
        'public class MemberController {\n'
        '  @PostMapping("/save.do") public String save(){ return "redirect:/login/login.do"; }\n'
        '}\n',
    )
    signup = tmp_path / 'src/main/webapp/WEB-INF/views/login/signup.jsp'
    _write(
        signup,
        '<div class="page-card">\n'
        '  <input type="text" name="loginId"/>\n'
        '  <button type="submit">가입</button>\n'
        '</form>\n'
        '</div>\n',
    )

    assert _auth_alias_kind_for_jsp_path(signup) == 'signup'
    issues = _scan_malformed_jsp_structure(tmp_path)
    issue = next(item for item in issues if item['path'].endswith('login/signup.jsp'))
    assert _repair_malformed_jsp_structure(signup, issue, tmp_path)

    body = signup.read_text(encoding='utf-8')
    assert body.count('<form') == 1
    assert '/member/save.do' in body
    assert '/login/login.do' in body
    assert 'loginPasswordConfirm' in body


def test_entry_only_index_form_jsp_is_rewritten_to_safe_redirect_page(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java',
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @GetMapping("/login.do") public String form(){ return "login/login"; }\n'
        '}\n',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/index/indexForm.jsp'
    _write(
        jsp,
        '<form action="<c:url value=\'/index/save.do\'/>" method="post">\n'
        '  <a href="<c:url value=\'/index/list.do\'/>">목록</a>\n'
        '  <a href="<c:url value=\'/index/delete.do\'/>">삭제</a>\n'
        '</form>\n',
    )
    issue = {
        'type': 'jsp_missing_route_reference',
        'path': 'src/main/webapp/WEB-INF/views/index/indexForm.jsp',
        'details': {
            'discovered_routes': ['/login/login.do'],
            'missing_routes': ['/index/save.do', '/index/list.do', '/index/delete.do'],
        },
    }

    assert _repair_jsp_missing_route_reference(jsp, issue, tmp_path)
    body = jsp.read_text(encoding='utf-8')
    assert '/index/save.do' not in body
    assert '/index/list.do' not in body
    assert '/index/delete.do' not in body
    assert '/login/login.do' in body
    assert '진입 전용 화면' in body


def test_boot_application_invariants_normalize_main_class_and_scan_base_packages(tmp_path: Path):
    boot = tmp_path / 'src/main/java/egovframework/example/EgovBootApplication.java'
    _write(
        boot,
        'package egovframework.example;\n\n'
        'import org.springframework.boot.autoconfigure.SpringBootApplication;\n\n'
        '@SpringBootApplication\n'
        'public class WrongBootName {\n'
        '    public static void main(String[] args) {\n'
        '        SpringApplication.run(WrongBootName.class, args);\n'
        '    }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java',
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        '@Controller\n'
        'public class MemberController {\n'
        '  @GetMapping("/member/list.do") public String list(){ return "member/memberList"; }\n'
        '}\n',
    )

    report = enforce_generated_project_invariants(tmp_path)
    body = boot.read_text(encoding='utf-8')

    assert report['changed_count'] >= 1
    assert 'public class EgovBootApplication' in body
    assert 'import org.springframework.boot.SpringApplication;' in body
    assert 'SpringApplication.run(EgovBootApplication.class, args);' in body
    assert '@SpringBootApplication(scanBasePackages = {"egovframework.example", "egovframework.test"})' in body


def test_entry_only_index_form_without_form_tag_is_not_flagged_as_malformed(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/index/indexForm.jsp'
    _write(
        jsp,
        """<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<!DOCTYPE html>
<html lang="ko">
<body>
  <h2>진입 전용 화면</h2>
  <a href="<c:url value='/login/login.do'/>">이동</a>
</body>
</html>
""",
    )

    issues = _scan_malformed_jsp_structure(tmp_path)
    assert not any(item['path'].endswith('index/indexForm.jsp') for item in issues)


def test_entry_only_index_form_malformed_issue_rewrites_to_redirect_page(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java',
        """package egovframework.test.login.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.*;
@Controller @RequestMapping("/login")
public class LoginController {
  @GetMapping("/login.do") public String form(){ return "login/login"; }
}
""",
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/index/indexForm.jsp'
    _write(
        jsp,
        """<div class="page-card">
  <h2>홈</h2>
  <a href="<c:url value='/login/login.do'/>">로그인</a>
</div>
""",
    )
    issue = {
        'type': 'malformed_jsp_structure',
        'path': 'src/main/webapp/WEB-INF/views/index/indexForm.jsp',
        'message': 'form-like jsp is missing opening form tag',
        'details': {'screen_role': 'entry'},
    }

    assert _repair_malformed_jsp_structure(jsp, issue, tmp_path)
    body = jsp.read_text(encoding='utf-8')
    assert '진입 전용 화면' in body
    assert '/login/login.do' in body
    assert '<form' not in body
