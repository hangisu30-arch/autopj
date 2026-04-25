from app.validation.project_auto_repair import _repair_ambiguous_request_mapping, _repair_malformed_jsp_structure
from app.validation.post_generation_repair import _validate_jsp_asset_consistency


def test_duplicate_login_mapping_rewrites_conflicting_membership_controller(tmp_path):
    root = tmp_path
    login = root / 'src/main/java/egovframework/test/login/web/LoginController.java'
    admin = root / 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java'
    login.parent.mkdir(parents=True, exist_ok=True)
    admin.parent.mkdir(parents=True, exist_ok=True)
    login.write_text(
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller\n'
        '@RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @GetMapping("/login.do") public String loginForm(){ return "login/login"; }\n'
        '  @PostMapping("/actionLogin.do") public String actionLogin(){ return "redirect:/login/actionMain.do"; }\n'
        '}\n',
        encoding='utf-8',
    )
    admin.write_text(
        'package egovframework.test.adminMember.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller\n'
        '@RequestMapping("/login")\n'
        'public class AdminMemberController {\n'
        '  @GetMapping("/login.do") public String loginForm(){ return "login/login"; }\n'
        '  @PostMapping("/actionLogin.do") public String actionLogin(){ return "redirect:/login/actionMain.do"; }\n'
        '}\n',
        encoding='utf-8',
    )
    issue = {'details': {'route': '/login/login.do', 'conflicting_path': 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java'}}
    assert _repair_ambiguous_request_mapping(login, issue, root) is True
    rewritten = admin.read_text(encoding='utf-8')
    assert '@RequestMapping("/adminMember")' in rewritten or '@RequestMapping("/adminmember")' in rewritten
    assert '@GetMapping("/register.do"' in rewritten or '@GetMapping({"/register.do", "/form.do"})' in rewritten or '@GetMapping("/form.do")' in rewritten
    assert '@PostMapping({"/actionRegister.do", "/save.do"})' in rewritten or '@PostMapping("/save.do")' in rewritten


def test_signup_calendar_jsp_is_removed_for_auth_alias(tmp_path):
    root = tmp_path
    jsp = root / 'src/main/webapp/WEB-INF/views/signup/signupCalendar.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<div>${item.name}</div>', encoding='utf-8')
    assert _repair_malformed_jsp_structure(jsp, project_root=root) is True
    assert not jsp.exists()


def test_index_target_route_validation_accepts_array_getmapping_login_route(tmp_path):
    root = tmp_path
    controller = root / 'src/main/java/egovframework/test/login/web/LoginController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller\n'
        '@RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @GetMapping({"/login.do", "/form.do"}) public String loginForm(){ return "login/login"; }\n'
        '}\n',
        encoding='utf-8',
    )
    index = root / 'src/main/webapp/index.jsp'
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text('<% response.sendRedirect(request.getContextPath() + "/login/login.do"); %>', encoding='utf-8')
    static_index = root / 'src/main/resources/static/index.html'
    static_index.parent.mkdir(parents=True, exist_ok=True)
    static_index.write_text('<script>location.replace("/login/login.do");</script>', encoding='utf-8')
    css = root / 'src/main/webapp/css/common.css'
    css.parent.mkdir(parents=True, exist_ok=True)
    css.write_text('body{}', encoding='utf-8')
    issues = _validate_jsp_asset_consistency(root, [])
    reasons = [item['reason'] for item in issues]
    assert 'index.jsp missing target route' not in reasons
    assert 'static index.html missing target route' not in reasons



def test_duplicate_login_mapping_rewrites_conflicting_controller_when_issue_points_to_login(tmp_path):
    root = tmp_path
    login = root / 'src/main/java/egovframework/test/login/web/LoginController.java'
    admin = root / 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java'
    login.parent.mkdir(parents=True, exist_ok=True)
    admin.parent.mkdir(parents=True, exist_ok=True)
    login.write_text(
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller\n'
        '@RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @GetMapping("/login.do") public String loginForm(){ return "login/login"; }\n'
        '}\n',
        encoding='utf-8',
    )
    admin.write_text(
        'package egovframework.test.adminMember.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller\n'
        '@RequestMapping("/login")\n'
        'public class AdminMemberController {\n'
        '  @GetMapping("/login.do") public String loginForm(){ return "login/login"; }\n'
        '  @PostMapping("/actionLogin.do") public String actionLogin(){ return "redirect:/login/actionMain.do"; }\n'
        '}\n',
        encoding='utf-8',
    )
    issue = {'details': {'route': '/login/login.do', 'conflicting_path': 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java'}}
    assert _repair_ambiguous_request_mapping(login, issue, root) is True
    rewritten = admin.read_text(encoding='utf-8').lower()
    assert '@requestmapping("/adminmember")' in rewritten


def test_index_target_route_validation_prefers_primary_login_route_for_jsp_startup_bundle(tmp_path):
    root = tmp_path
    controller = root / 'src/main/java/egovframework/test/login/web/LoginController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller\n'
        '@RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @GetMapping({"/login.do", "/form.do"}) public String loginForm(){ return "login/login"; }\n'
        '}\n',
        encoding='utf-8',
    )
    index = root / 'src/main/webapp/index.jsp'
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text('<% response.sendRedirect(request.getContextPath() + "/login/login.do"); %>', encoding='utf-8')
    static_index = root / 'src/main/resources/static/index.html'
    static_index.parent.mkdir(parents=True, exist_ok=True)
    static_index.write_text('<script>location.replace("/login/login.do");</script>', encoding='utf-8')
    css = root / 'src/main/webapp/css/common.css'
    css.parent.mkdir(parents=True, exist_ok=True)
    css.write_text('body{}', encoding='utf-8')
    issues = _validate_jsp_asset_consistency(root, [])
    reasons = [item['reason'] for item in issues]
    assert 'index.jsp missing target route' not in reasons
    assert 'static index.html missing target route' not in reasons
