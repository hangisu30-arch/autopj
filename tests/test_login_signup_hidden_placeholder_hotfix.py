from pathlib import Path

from app.validation.project_auto_repair import _rewrite_signup_jsp_to_safe_routes


def test_login_signup_rewrite_does_not_emit_empty_hidden_value_attributes(tmp_path: Path) -> None:
    signup_jsp = tmp_path / 'src/main/webapp/WEB-INF/views/login/signup.jsp'
    signup_jsp.parent.mkdir(parents=True, exist_ok=True)
    signup_jsp.write_text('<html><body>broken</body></html>', encoding='utf-8')

    controller = tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.PostMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @GetMapping("/signup.do") public String signup(){ return "login/signup"; }\n'
        '  @PostMapping("/save.do") public String save(){ return "redirect:/login/login.do"; }\n'
        '}\n',
        encoding='utf-8',
    )

    vo = tmp_path / 'src/main/java/egovframework/test/login/service/vo/LoginVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        'package egovframework.test.login.service.vo;\n'
        'public class LoginVO {\n'
        '  private String loginId;\n'
        '  private String password;\n'
        '  private String roleCd;\n'
        '  private String useYn;\n'
        '  private String createdBy;\n'
        '}\n',
        encoding='utf-8',
    )

    changed = _rewrite_signup_jsp_to_safe_routes(signup_jsp, tmp_path)
    body = signup_jsp.read_text(encoding='utf-8')

    assert changed is True
    assert 'type="hidden" name="roleCd"/>' in body
    assert 'type="hidden" name="useYn"/>' in body
    assert 'type="hidden" name="createdBy"/>' in body
    assert 'type="hidden" name="roleCd" value=""' not in body
    assert 'type="hidden" name="useYn" value=""' not in body
    assert 'type="hidden" name="createdBy" value=""' not in body
