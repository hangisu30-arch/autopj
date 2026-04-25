from pathlib import Path
import subprocess

from app.validation.post_generation_repair import _repair_timed_out_auth_endpoints, _repair_timed_out_calendar_endpoints


def test_repair_timed_out_calendar_endpoints_rewrites_calendar_controller_to_contract_safe_calendar(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/demo/schedule/web/ScheduleController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.demo.schedule.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.ui.Model;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n'
        '@RequestMapping("/schedule")\n'
        'public class ScheduleController {\n'
        '    @GetMapping("/calendar.do")\n'
        '    public String calendar(Model model) throws Exception {\n'
        '        model.addAttribute("events", scheduleService.selectScheduleList(null));\n'
        '        return "schedule/scheduleList";\n'
        '    }\n'
        '}\n',
        encoding='utf-8',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<html></html>', encoding='utf-8')

    runtime_validation = {
        'endpoint_smoke': {
            'status': 'failed',
            'results': [
                {
                    'route': '/schedule/calendar.do',
                    'ok': False,
                    'error': 'timed out',
                }
            ],
        }
    }

    changed = _repair_timed_out_calendar_endpoints(tmp_path, runtime_validation)
    body = controller.read_text(encoding='utf-8')

    assert 'src/main/java/egovframework/demo/schedule/web/ScheduleController.java' in changed
    assert 'return "schedule/scheduleCalendar";' in body
    assert 'model.addAttribute("calendarCells"' in body
    assert 'model.addAttribute("selectedDateSchedules"' in body


def test_repair_timed_out_calendar_endpoints_removes_service_calls_for_smoke_safety(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/demo/schedule/web/ScheduleController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.demo.schedule.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.ui.Model;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n'
        '@RequestMapping("/schedule")\n'
        'public class ScheduleController {\n'
        '    @GetMapping("/calendar.do")\n'
        '    public String calendar(Model model) throws Exception {\n'
        '        model.addAttribute("events", scheduleService.selectScheduleList(null));\n'
        '        return "schedule/scheduleCalendar";\n'
        '    }\n'
        '}\n',
        encoding='utf-8',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<html></html>', encoding='utf-8')

    runtime_validation = {
        'endpoint_smoke': {
            'status': 'failed',
            'results': [{'route': '/schedule/calendar.do', 'ok': False, 'error': 'timed out'}],
        }
    }

    changed = _repair_timed_out_calendar_endpoints(tmp_path, runtime_validation)
    body = controller.read_text(encoding='utf-8')
    assert changed
    assert 'scheduleService' not in body
    assert 'selectScheduleList' not in body
    assert 'model.addAttribute("calendarCells"' in body


def test_repair_timed_out_auth_endpoints_rewrites_login_assets_to_smoke_safe_pages(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/demo/login/web/LoginController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.demo.login.web;\n'
        'import javax.servlet.http.HttpSession;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.ui.Model;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n'
        '@RequestMapping("/login")\n'
        'public class LoginController {\n'
        '    @GetMapping("/login.do")\n'
        '    public String loginForm(HttpSession session, Model model) {\n'
        '        model.addAttribute("item", new Object());\n'
        '        return "login/login";\n'
        '    }\n'
        '    @GetMapping("/actionMain.do")\n'
        '    public String actionMain(HttpSession session, Model model) {\n'
        '        Object loginVO = session == null ? null : session.getAttribute("loginVO");\n'
        '        if (loginVO == null) {\n'
        '            return "redirect:/login/login.do";\n'
        '        }\n'
        '        model.addAttribute("loginUser", loginVO);\n'
        '        return "login/main";\n'
        '    }\n'
        '}\n',
        encoding='utf-8',
    )

    runtime_validation = {
        'endpoint_smoke': {
            'status': 'failed',
            'results': [
                {'route': '/login/login.do', 'ok': False, 'error': 'timed out'},
                {'route': '/login/actionMain.do', 'ok': False, 'error': 'timed out'},
            ],
        }
    }

    changed = _repair_timed_out_auth_endpoints(tmp_path, runtime_validation)
    login_body = (tmp_path / 'src/main/webapp/WEB-INF/views/login/login.jsp').read_text(encoding='utf-8')
    main_body = (tmp_path / 'src/main/webapp/WEB-INF/views/login/main.jsp').read_text(encoding='utf-8')
    controller_body = controller.read_text(encoding='utf-8')

    assert 'src/main/webapp/WEB-INF/views/login/login.jsp' in changed
    assert 'src/main/webapp/WEB-INF/views/login/main.jsp' in changed
    assert 'AUTOPJ smoke-safe login page' in login_body
    assert 'AUTOPJ smoke-safe main page' in main_body
    assert 'return "login/login";' in controller_body
    assert 'return "login/main";' in controller_body


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def test_repair_timed_out_auth_endpoints_keeps_login_controller_java_syntax_with_nested_blocks(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/demo/login/web/LoginController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.demo.login.web;\n'
        'import javax.servlet.http.HttpSession;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.ui.Model;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n'
        '@RequestMapping("/login")\n'
        'public class LoginController {\n'
        '    @GetMapping("/login.do")\n'
        '    public String loginForm(HttpSession session, Model model) {\n'
        '        if (session != null && session.getAttribute("loginVO") != null) {\n'
        '            return "redirect:/login/actionMain.do";\n'
        '        }\n'
        '        model.addAttribute("item", new Object());\n'
        '        return "login/login";\n'
        '    }\n'
        '    @GetMapping("/actionMain.do")\n'
        '    public String actionMain(HttpSession session, Model model) {\n'
        '        Object loginVO = session == null ? null : session.getAttribute("loginVO");\n'
        '        if (loginVO == null) {\n'
        '            return "redirect:/login/login.do";\n'
        '        }\n'
        '        model.addAttribute("loginUser", loginVO);\n'
        '        return "login/main";\n'
        '    }\n'
        '}\n',
        encoding='utf-8',
    )

    runtime_validation = {
        'endpoint_smoke': {
            'status': 'failed',
            'results': [
                {'route': '/login/login.do', 'ok': False, 'error': 'timed out'},
                {'route': '/login/actionMain.do', 'ok': False, 'error': 'timed out'},
            ],
        }
    }

    changed = _repair_timed_out_auth_endpoints(tmp_path, runtime_validation)
    controller_body = controller.read_text(encoding='utf-8')

    assert changed
    assert controller_body.count('@GetMapping("/login.do")') == 1
    assert controller_body.count('@GetMapping("/actionMain.do")') == 1
    assert 'return "login/login";' in controller_body
    assert 'return "login/main";' in controller_body

    src_root = tmp_path / 'javac-src'
    _write(src_root / 'egovframework/demo/login/web/LoginController.java', controller_body)
    _write(src_root / 'javax/servlet/http/HttpSession.java', 'package javax.servlet.http; public interface HttpSession { Object getAttribute(String name); }')
    _write(src_root / 'org/springframework/stereotype/Controller.java', 'package org.springframework.stereotype; public @interface Controller {}')
    _write(src_root / 'org/springframework/ui/Model.java', 'package org.springframework.ui; public interface Model { Model addAttribute(String key, Object value); }')
    _write(src_root / 'org/springframework/web/bind/annotation/GetMapping.java', 'package org.springframework.web.bind.annotation; public @interface GetMapping { String[] value() default {}; }')
    _write(src_root / 'org/springframework/web/bind/annotation/RequestMapping.java', 'package org.springframework.web.bind.annotation; public @interface RequestMapping { String[] value() default {}; }')

    result = subprocess.run(
        [
            'javac',
            '-encoding', 'UTF-8',
            '-d', str(tmp_path / 'classes'),
            str(src_root / 'javax/servlet/http/HttpSession.java'),
            str(src_root / 'org/springframework/stereotype/Controller.java'),
            str(src_root / 'org/springframework/ui/Model.java'),
            str(src_root / 'org/springframework/web/bind/annotation/GetMapping.java'),
            str(src_root / 'org/springframework/web/bind/annotation/RequestMapping.java'),
            str(src_root / 'egovframework/demo/login/web/LoginController.java'),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
