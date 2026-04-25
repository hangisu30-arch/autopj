from pathlib import Path

from app.validation import project_auto_repair as repair


def test_balance_jsp_markup_removes_orphan_form_and_closes_if():
    body = '''<%@ page contentType="text/html; charset=UTF-8" %>
<c:if test="${empty item}">
<div>empty</div>
</form>
'''
    fixed = repair._balance_jsp_markup(body)
    assert '</form>' not in fixed
    assert '</c:if>' in fixed


def test_rewrite_signup_jsp_to_safe_routes_avoids_empty_hidden_values(tmp_path: Path):
    project_root = tmp_path
    jsp = project_root / 'src/main/webapp/WEB-INF/views/login/signup.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('', encoding='utf-8')
    controller = project_root / 'src/main/java/demo/login/web/LoginController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        '''package demo.login.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.*;
@Controller
@RequestMapping("/login")
public class LoginController {
  @GetMapping("/login.do") public String login(){ return "login/login"; }
  @PostMapping("/save.do") public String save(){ return "redirect:/login/login.do"; }
}
''',
        encoding='utf-8',
    )
    assert repair._rewrite_signup_jsp_to_safe_routes(jsp, project_root) is True
    rendered = jsp.read_text(encoding='utf-8')
    assert 'value=""' not in rendered
    assert rendered.count('<form') == rendered.count('</form>')


def test_normalize_jsp_file_structure_balances_unclosed_user_detail(tmp_path: Path):
    jsp = tmp_path / 'userDetail.jsp'
    jsp.write_text('<div><form><c:if test="${true}"><span>x</span></div>', encoding='utf-8')
    assert repair._normalize_jsp_file_structure(jsp) is True
    fixed = jsp.read_text(encoding='utf-8')
    assert fixed.count('<form') == fixed.count('</form>')
    assert '</c:if>' in fixed
    assert '</div>' in fixed
