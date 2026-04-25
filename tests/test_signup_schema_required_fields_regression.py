from pathlib import Path

from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import _rewrite_signup_jsp_to_safe_routes


class _Cfg:
    frontend_key = 'jsp'
    database_key = 'mysql'


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_signup_repair_includes_member_id_and_email_fields(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java',
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @GetMapping("/login.do") public String loginForm(){ return "login/login"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java',
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.PostMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/member")\n'
        'public class MemberController {\n'
        '  @PostMapping("/save.do") public String save(){ return "redirect:/login/login.do"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/member/service/vo/MemberVO.java',
        'package egovframework.test.member.service.vo;\n'
        'public class MemberVO {\n'
        '  private String memberId;\n'
        '  private String password;\n'
        '  private String memberName;\n'
        '  private String email;\n'
        '  public String getMemberId(){ return memberId; }\n'
        '  public void setMemberId(String v){ memberId = v; }\n'
        '  public String getPassword(){ return password; }\n'
        '  public void setPassword(String v){ password = v; }\n'
        '  public String getMemberName(){ return memberName; }\n'
        '  public void setMemberName(String v){ memberName = v; }\n'
        '  public String getEmail(){ return email; }\n'
        '  public void setEmail(String v){ email = v; }\n'
        '}\n',
    )
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/common/header.jsp', '<div>header</div>')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/common/leftNav.jsp', '<div>left</div>')
    signup = tmp_path / 'src/main/webapp/WEB-INF/views/member/signup.jsp'
    _write(signup, '<form><input name="password"/></form>')

    assert _rewrite_signup_jsp_to_safe_routes(signup, tmp_path)
    body = signup.read_text(encoding='utf-8')
    assert 'name="memberId"' in body
    assert 'name="email"' in body
    assert 'name="password"' in body
    assert '/member/save.do' in body

    report = validate_generated_project(tmp_path, _Cfg(), include_runtime=False)
    signup_issues = [
        item for item in (report.get('static_issues') or [])
        if str(item.get('path') or '').endswith('member/signup.jsp')
    ]
    assert not any(item.get('type') == 'form_fields_incomplete' for item in signup_issues), signup_issues
