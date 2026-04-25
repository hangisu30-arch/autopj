from pathlib import Path

from app.ui.state import ProjectConfig
from app.validation.post_generation_repair import (
    _validate_controller_jsp_consistency,
    _validate_jsp_asset_consistency,
    validate_and_repair_generated_files,
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_validate_controller_jsp_consistency_treats_index_as_entry_bundle(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/index/web/IndexController.java'
    _write(
        controller,
        '''package egovframework.test.index.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class IndexController {
    @GetMapping({"/", "/index.do"})
    public String index() {
        return "index/indexCalendar";
    }
}
''',
    )
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/common/header.jsp', '<div></div>')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/common/leftNav.jsp', '<div></div>')

    issues = _validate_controller_jsp_consistency(tmp_path)
    reasons = {item['reason'] for item in issues}
    assert 'entry controller must be redirect-only' in reasons
    assert not any('return view missing jsp -> index/indexCalendar' == reason for reason in reasons)


def test_validate_jsp_asset_consistency_accepts_discovered_entry_target_route(tmp_path: Path):
    _write(tmp_path / 'src/main/webapp/css/common.css', 'body {}')
    _write(
        tmp_path / 'src/main/webapp/index.jsp',
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n<% response.sendRedirect(request.getContextPath() + "/reservation/calendar.do"); %>',
    )
    _write(
        tmp_path / 'src/main/resources/static/index.html',
        '<meta http-equiv="refresh" content="0;url=/reservation/calendar.do" /><script>window.location.replace("/reservation/calendar.do");</script>',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/reservation/web/ReservationController.java',
        '''package egovframework.test.reservation.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/reservation")
public class ReservationController {
    @GetMapping("/calendar.do")
    public String calendar() { return "reservation/reservationCalendar"; }
}
''',
    )
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/reservation/reservationCalendar.jsp', '<div></div>')
    issues = _validate_jsp_asset_consistency(tmp_path, ['src/main/webapp/WEB-INF/views/reservation/reservationCalendar.jsp'])
    reasons = {item['reason'] for item in issues}
    assert 'index.jsp missing target route' not in reasons
    assert 'static index.html missing target route' not in reasons




def test_validate_jsp_asset_consistency_accepts_any_discovered_entry_route(tmp_path: Path):
    _write(tmp_path / 'src/main/webapp/css/common.css', 'body {}')
    _write(
        tmp_path / 'src/main/webapp/index.jsp',
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n<% response.sendRedirect(request.getContextPath() + "/login/login.do"); %>',
    )
    _write(
        tmp_path / 'src/main/resources/static/index.html',
        '<meta http-equiv="refresh" content="0;url=/login/login.do" /><script>window.location.replace("/login/login.do");</script>',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java',
        '''package egovframework.test.login.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/login")
public class LoginController {
    @GetMapping("/login.do")
    public String loginForm() { return "login/login"; }
}
''',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/signup/web/SignupController.java',
        '''package egovframework.test.signup.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/signup")
public class SignupController {
    @GetMapping("/list.do")
    public String list() { return "signup/signupList"; }
}
''',
    )
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/login/login.jsp', '<div></div>')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupList.jsp', '<div></div>')
    issues = _validate_jsp_asset_consistency(tmp_path, [
        'src/main/webapp/WEB-INF/views/login/login.jsp',
        'src/main/webapp/WEB-INF/views/signup/signupList.jsp',
    ])
    reasons = {item['reason'] for item in issues}
    assert 'index.jsp missing target route' not in reasons
    assert 'static index.html missing target route' not in reasons

def test_smoke_repair_normalizes_entry_bundle(tmp_path: Path, monkeypatch):
    rel = 'src/main/java/egovframework/test/index/web/IndexController.java'
    _write(
        tmp_path / rel,
        '''package egovframework.test.index.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class IndexController {
    @GetMapping({"/", "/index.do"})
    public String index() {
        return "index/indexCalendar";
    }
}
''',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/schedule/web/ScheduleController.java',
        '''package egovframework.test.schedule.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/schedule")
public class ScheduleController {
    @GetMapping("/calendar.do")
    public String calendar() { return "schedule/scheduleCalendar"; }
}
''',
    )
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp', '<div></div>')
    _write(tmp_path / 'pom.xml', '<project/>\n')
    _write(tmp_path / 'mvnw', '#!/bin/sh\n')
    _write(tmp_path / 'mvnw.cmd', '@echo off\n')
    _write(tmp_path / '.mvn/wrapper/maven-wrapper.properties', 'distributionUrl=https://example.invalid/apache-maven.zip\n')

    cfg = ProjectConfig(project_name='demo', frontend_key='jsp', database_key='sqlite', backend_key='egov_spring')
    report = {'created': [rel], 'overwritten': [], 'errors': [], 'patched': {}}
    file_ops = [
        {'path': rel, 'purpose': 'controller', 'content': 'spec text'},
        {'path': 'src/main/java/egovframework/test/schedule/web/ScheduleController.java', 'purpose': 'controller', 'content': 'spec text'},
        {'path': 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp', 'purpose': 'calendar_jsp', 'content': 'spec text'},
    ]

    calls = {'count': 0}
    def fake_runtime(project_root: Path, backend_key: str = '', compile_timeout_seconds: int = 300, startup_timeout_seconds: int = 120):
        calls['count'] += 1
        if calls['count'] < 3:
            return {
                'ok': False,
                'status': 'failed',
                'compile': {'status': 'ok', 'errors': []},
                'startup': {'status': 'ok', 'errors': []},
                'endpoint_smoke': {'status': 'failed', 'results': [{'route': '/', 'status_code': 500, 'ok': False}]},
            }
        return {
            'ok': True,
            'status': 'ok',
            'compile': {'status': 'ok', 'errors': []},
            'startup': {'status': 'ok', 'errors': []},
            'endpoint_smoke': {'status': 'ok', 'results': [{'route': '/', 'status_code': 200, 'ok': True}]},
        }

    monkeypatch.setattr('app.validation.post_generation_repair.run_spring_boot_runtime_validation', fake_runtime)
    monkeypatch.setattr('app.validation.post_generation_repair._validate_paths', lambda root, rel_paths, frontend_key='': [])
    # keep real controller/jsp validators for this test
    monkeypatch.setattr('app.validation.post_generation_repair._validate_jsp_include_consistency', lambda root, rel_paths: [])
    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_content', lambda rel, body, frontend_key='': (True, ''))
    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_project', lambda *args, **kwargs: {
        'ok': False,
        'static_issue_count': 1,
        'static_issues': [{'type': 'calendar_ssr_missing', 'path': 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'}],
    })
    monkeypatch.setattr('app.validation.post_generation_repair.apply_generated_project_auto_repair', lambda *args, **kwargs: {
        'changed': [{'path': 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'}],
        'skipped': [],
        'changed_count': 1,
    })

    result = validate_and_repair_generated_files(
        project_root=tmp_path,
        cfg=cfg,
        report=report,
        file_ops=file_ops,
        regenerate_callback=None,
        use_execution_core=False,
        max_regen_attempts=0,
    )

    smoke_rounds = result.get('smoke_repair_rounds') or []
    assert smoke_rounds
    changed_paths = {item.get('path') for item in smoke_rounds[-1].get('changed') or []}
    assert 'src/main/webapp/index.jsp' in changed_paths
    controllers = list((tmp_path / 'src/main/java').rglob('IndexController.java'))
    assert controllers
    body = controllers[0].read_text(encoding='utf-8')
    assert 'redirect:/schedule/calendar.do' in body
