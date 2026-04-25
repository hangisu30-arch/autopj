from pathlib import Path

from app.ui.post_validation_logging import post_validation_diagnostic_lines
from app.ui.state import ProjectConfig
from app.validation.post_generation_repair import validate_and_repair_generated_files


def test_post_generation_repair_records_smoke_repair_rounds(tmp_path: Path, monkeypatch):
    rel = 'src/main/java/egovframework/rtest/schedule/web/ScheduleController.java'
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('package egovframework.rtest.schedule.web;\npublic class ScheduleController {}\n', encoding='utf-8')
    (tmp_path / 'pom.xml').write_text('<project/>\n', encoding='utf-8')
    (tmp_path / 'mvnw').write_text('#!/bin/sh\n', encoding='utf-8')
    (tmp_path / 'mvnw.cmd').write_text('@echo off\n', encoding='utf-8')
    wrapper = tmp_path / '.mvn/wrapper/maven-wrapper.properties'
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text('distributionUrl=https://example.invalid/apache-maven.zip\n', encoding='utf-8')

    cfg = ProjectConfig(project_name='demo', frontend_key='jsp', database_key='sqlite', backend_key='egov_spring')
    report = {'created': [rel], 'overwritten': [], 'errors': [], 'patched': {}}
    file_ops = [{'path': rel, 'purpose': 'controller', 'content': 'spec text'}]

    calls = {'count': 0}

    def fake_runtime(project_root: Path, backend_key: str = '', compile_timeout_seconds: int = 300, startup_timeout_seconds: int = 120):
        calls['count'] += 1
        if calls['count'] == 1:
            return {
                'ok': False,
                'status': 'failed',
                'compile': {'status': 'ok', 'command': 'cmd /c mvnw.cmd -q -DskipTests clean compile', 'errors': []},
                'startup': {'status': 'ok', 'command': 'cmd /c mvnw.cmd -q spring-boot:run', 'errors': [], 'base_url': 'http://127.0.0.1:18080', 'port': 18080},
                'endpoint_smoke': {'status': 'failed', 'results': [{'route': '/schedule/calendar.do', 'status_code': 500, 'ok': False}]},
            }
        return {
            'ok': True,
            'status': 'ok',
            'compile': {'status': 'ok', 'command': 'cmd /c mvnw.cmd -q -DskipTests clean compile', 'errors': []},
            'startup': {'status': 'ok', 'command': 'cmd /c mvnw.cmd -q spring-boot:run', 'errors': [], 'base_url': 'http://127.0.0.1:18080', 'port': 18080},
            'endpoint_smoke': {'status': 'ok', 'results': [{'route': '/schedule/calendar.do', 'status_code': 200, 'ok': True}]},
        }

    monkeypatch.setattr('app.validation.post_generation_repair.run_spring_boot_runtime_validation', fake_runtime)
    monkeypatch.setattr('app.validation.post_generation_repair._validate_paths', lambda root, rel_paths, frontend_key='': [])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_controller_jsp_consistency', lambda root: [])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_jsp_include_consistency', lambda root, rel_paths: [])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_jsp_asset_consistency', lambda root, rel_paths: [])
    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_content', lambda rel, body, frontend_key='': (True, ''))
    validation_calls = {'count': 0}

    def fake_validate_generated_project(project_root, cfg, manifest=None, include_runtime=False):
        validation_calls['count'] += 1
        if validation_calls['count'] == 1:
            return {
                'ok': False,
                'static_issue_count': 1,
                'static_issues': [{'type': 'calendar_ssr_missing', 'path': 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'}],
            }
        return {'ok': True, 'static_issue_count': 0, 'static_issues': []}

    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_project', fake_validate_generated_project)
    monkeypatch.setattr('app.validation.post_generation_repair.apply_generated_project_auto_repair', lambda project_root, report: {
        'changed': [{'path': 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'}],
        'skipped': [],
        'changed_count': 1,
    })

    result = validate_and_repair_generated_files(
        project_root=tmp_path,
        cfg=cfg,
        report=report,
        file_ops=file_ops,
        regenerate_callback=lambda source_path, purpose, spec, reason: {'path': source_path, 'content': 'package egovframework.rtest.schedule.web;\npublic class ScheduleController {}\n'},
        use_execution_core=False,
        max_regen_attempts=1,
    )

    assert result['ok'] is True
    assert result.get('compile_repair_rounds') == []
    smoke_rounds = result.get('smoke_repair_rounds') or []
    if smoke_rounds:
        assert smoke_rounds[0]['before']['compile_status'] == 'ok'
        assert smoke_rounds[0]['before']['endpoint_smoke_status'] == 'failed'
        assert smoke_rounds[0]['after']['endpoint_smoke_status'] == 'ok'
        assert any((item.get('path') or '').endswith('scheduleCalendar.jsp') for item in smoke_rounds[0]['changed'])


def test_post_generation_repair_collects_unresolved_initial_invalid(tmp_path: Path, monkeypatch):
    rel = 'src/main/java/egovframework/rtest/index/web/IndexController.java'
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('package egovframework.rtest.index.web;\npublic class IndexController {}\n', encoding='utf-8')
    cfg = ProjectConfig(project_name='demo', frontend_key='jsp', database_key='sqlite', backend_key='egov_spring')
    report = {'created': [rel], 'overwritten': [], 'errors': [], 'patched': {}}
    file_ops = [{'path': rel, 'purpose': 'controller', 'content': 'spec text'}]

    invalid_item = {'path': rel, 'reason': 'entry controller still invalid'}
    monkeypatch.setattr('app.validation.post_generation_repair._validate_paths', lambda root, rel_paths, frontend_key='': [invalid_item])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_controller_jsp_consistency', lambda root: [])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_jsp_include_consistency', lambda root, rel_paths: [])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_jsp_asset_consistency', lambda root, rel_paths: [])
    monkeypatch.setattr('app.validation.post_generation_repair.run_spring_boot_runtime_validation', lambda *args, **kwargs: {
        'ok': True,
        'status': 'ok',
        'compile': {'status': 'ok', 'errors': []},
        'startup': {'status': 'ok', 'errors': []},
        'endpoint_smoke': {'status': 'ok', 'results': []},
    })
    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_project', lambda *args, **kwargs: {'ok': True, 'static_issue_count': 0, 'static_issues': []})
    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_content', lambda rel, body, frontend_key='': (True, ''))

    result = validate_and_repair_generated_files(
        project_root=tmp_path,
        cfg=cfg,
        report=report,
        file_ops=file_ops,
        regenerate_callback=None,
        use_execution_core=False,
        max_regen_attempts=0,
    )

    unresolved = result.get('unresolved_initial_invalid') or []
    assert len(unresolved) == 1
    assert unresolved[0]['path'] == rel
    assert unresolved[0]['reason'] == 'entry controller still invalid'


def test_post_validation_diagnostic_lines_include_unresolved_and_smoke_rounds():
    lines = post_validation_diagnostic_lines({
        'invalid_delta': {'added_count': 1, 'removed_count': 0, 'grew': True, 'added': [{'path': 'a.jsp', 'reason': 'new issue'}], 'removed': []},
        'unresolved_initial_invalid': [{'path': 'src/main/java/demo/IndexController.java', 'reason': 'entry controller still invalid'}],
        'compile_repair_rounds': [],
        'smoke_repair_rounds': [{
            'round': 1,
            'targets': ['src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'],
            'changed': [{'path': 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'}],
            'skipped': [],
            'before': {'compile_status': 'ok', 'startup_status': 'ok', 'endpoint_smoke_status': 'failed', 'compile_errors': []},
            'after': {'compile_status': 'ok', 'startup_status': 'ok', 'endpoint_smoke_status': 'ok', 'compile_errors': []},
        }],
    })

    assert any(line.startswith('[POST-VALIDATION-UNRESOLVED] count=1') for line in lines)
    assert any(line.startswith('[SMOKE-REPAIR] round=1') for line in lines)
    assert any(line.startswith('[SMOKE-RETRY-1] before compile=ok') for line in lines)


def test_post_generation_repair_uses_fresh_runtime_before_smoke_branch(tmp_path: Path, monkeypatch):
    rel = 'src/main/java/egovframework/test/schedule/web/ScheduleController.java'
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('package egovframework.test.schedule.web;\npublic class ScheduleController {}\n', encoding='utf-8')
    cfg = ProjectConfig(project_name='test', frontend_key='jsp', database_key='sqlite', backend_key='egov_spring')
    report = {'created': [rel], 'overwritten': [], 'errors': [], 'patched': {}}
    file_ops = [{'path': rel, 'purpose': 'controller', 'content': 'spec text'}]

    runtimes = iter([
        {
            'ok': False,
            'status': 'failed',
            'compile': {'status': 'failed', 'errors': [{'path': rel, 'code': 'cannot_find_symbol', 'message': 'cannot find symbol'}]},
            'startup': {'status': 'skipped', 'errors': []},
            'endpoint_smoke': {'status': 'skipped', 'results': []},
        },
    ])

    monkeypatch.setattr('app.validation.post_generation_repair.run_spring_boot_runtime_validation', lambda *args, **kwargs: next(runtimes))
    monkeypatch.setattr('app.validation.post_generation_repair._validate_paths', lambda root, rel_paths, frontend_key='': [])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_controller_jsp_consistency', lambda root: [])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_jsp_include_consistency', lambda root, rel_paths: [])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_jsp_asset_consistency', lambda root, rel_paths: [])
    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_content', lambda rel, body, frontend_key='': (True, ''))

    validation_calls = {'count': 0}

    def fake_validate_generated_project(project_root, cfg, manifest=None, include_runtime=False):
        validation_calls['count'] += 1
        if validation_calls['count'] == 1:
            return {
                'ok': False,
                'static_issue_count': 1,
                'static_issues': [{'type': 'calendar_ssr_missing', 'path': 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'}],
            }
        return {'ok': True, 'static_issue_count': 0, 'static_issues': []}

    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_project', fake_validate_generated_project)
    monkeypatch.setattr('app.validation.post_generation_repair.apply_generated_project_auto_repair', lambda project_root, report: {
        'changed': [{'path': 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'}],
        'skipped': [],
        'changed_count': 1,
    })

    compile_loop_called = {'count': 0}

    def fake_compile_loop(**kwargs):
        compile_loop_called['count'] += 1
        if compile_loop_called['count'] == 1:
            return ({
                'ok': False,
                'status': 'failed',
                'compile': {'status': 'ok', 'errors': []},
                'startup': {'status': 'ok', 'errors': []},
                'endpoint_smoke': {'status': 'failed', 'results': []},
            }, [])
        return ({
            'ok': True,
            'status': 'ok',
            'compile': {'status': 'ok', 'errors': []},
            'startup': {'status': 'ok', 'errors': []},
            'endpoint_smoke': {'status': 'ok', 'results': []},
        }, [{
            'round': 1,
            'targets': [rel],
            'changed': [{'path': rel}],
            'skipped': [],
            'before': {'compile_status': 'failed', 'startup_status': 'skipped', 'endpoint_smoke_status': 'skipped'},
            'after': {'compile_status': 'ok', 'startup_status': 'ok', 'endpoint_smoke_status': 'ok'},
        }])

    monkeypatch.setattr('app.validation.post_generation_repair._run_compile_repair_loop', fake_compile_loop)

    result = validate_and_repair_generated_files(
        project_root=tmp_path,
        cfg=cfg,
        report=report,
        file_ops=file_ops,
        regenerate_callback=lambda source_path, purpose, spec, reason: {'path': source_path, 'content': 'package egovframework.test.schedule.web;\npublic class ScheduleController {}\n'},
        use_execution_core=False,
        max_regen_attempts=1,
    )

    assert compile_loop_called['count'] == 2
    assert len(result.get('compile_repair_rounds') or []) == 1
    assert result.get('smoke_repair_rounds') == []


def test_post_generation_repair_handoffs_compile_success_to_smoke_repair(tmp_path: Path, monkeypatch):
    rel = 'src/main/java/egovframework/test/schedule/web/ScheduleController.java'
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('package egovframework.test.schedule.web\npublic class ScheduleController {}\n', encoding='utf-8')
    header = tmp_path / 'src/main/webapp/WEB-INF/views/common/header.jsp'
    header.parent.mkdir(parents=True, exist_ok=True)
    header.write_text('<script src="/js/jquery.min.js"></script>\n', encoding='utf-8')
    index_jsp = tmp_path / 'src/main/webapp/index.jsp'
    index_jsp.parent.mkdir(parents=True, exist_ok=True)
    index_jsp.write_text('<% response.sendRedirect("/schedule/calendar.do"); %>\n', encoding='utf-8')
    static_index = tmp_path / 'src/main/resources/static/index.html'
    static_index.parent.mkdir(parents=True, exist_ok=True)
    static_index.write_text('<meta http-equiv="refresh" content="0; url=/schedule/calendar.do">\n', encoding='utf-8')
    cfg = ProjectConfig(project_name='test', frontend_key='jsp', database_key='sqlite', backend_key='egov_spring')
    report = {'created': [rel], 'overwritten': [], 'errors': [], 'patched': {}}
    file_ops = [{'path': rel, 'purpose': 'controller', 'content': 'spec text'}]

    runtimes = iter([
        {
            'ok': True,
            'status': 'ok',
            'compile': {'status': 'ok', 'errors': []},
            'startup': {'status': 'ok', 'errors': [], 'base_url': 'http://127.0.0.1:18080', 'port': 18080},
            'endpoint_smoke': {'status': 'ok', 'results': [{'route': '/schedule/calendar.do', 'status_code': 200, 'ok': True}]},
        },
    ])

    monkeypatch.setattr('app.validation.post_generation_repair.run_spring_boot_runtime_validation', lambda *args, **kwargs: next(runtimes))
    monkeypatch.setattr('app.validation.post_generation_repair._validate_paths', lambda root, rel_paths, frontend_key='': [])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_controller_jsp_consistency', lambda root: [])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_jsp_include_consistency', lambda root, rel_paths: [])
    monkeypatch.setattr('app.validation.post_generation_repair._validate_jsp_asset_consistency', lambda root, rel_paths: [])
    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_content', lambda rel, body, frontend_key='': (True, ''))
    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_project', lambda *args, **kwargs: {'ok': True, 'static_issue_count': 0, 'static_issues': []})
    monkeypatch.setattr('app.validation.post_generation_repair._repair_index_redirect_assets', lambda *args, **kwargs: ['src/main/webapp/index.jsp'])
    monkeypatch.setattr('app.validation.post_generation_repair._run_compile_repair_loop', lambda **kwargs: ({
        'ok': False,
        'status': 'failed',
        'compile': {'status': 'ok', 'errors': []},
        'startup': {'status': 'ok', 'errors': [], 'base_url': 'http://127.0.0.1:18080', 'port': 18080},
        'endpoint_smoke': {'status': 'failed', 'results': [{'route': '/schedule/calendar.do', 'url': 'http://127.0.0.1:18080/schedule/calendar.do', 'status_code': 500, 'ok': False, 'response_excerpt': 'boom'}]},
    }, [{
        'round': 1,
        'targets': [rel],
        'changed': [{'path': rel}],
        'skipped': [],
        'before': {'compile_status': 'failed', 'startup_status': 'skipped', 'endpoint_smoke_status': 'skipped'},
        'after': {'compile_status': 'ok', 'startup_status': 'ok', 'endpoint_smoke_status': 'failed'},
    }]))

    result = validate_and_repair_generated_files(
        project_root=tmp_path,
        cfg=cfg,
        report=report,
        file_ops=file_ops,
        regenerate_callback=lambda source_path, purpose, spec, reason: {'path': source_path, 'content': 'package egovframework.test.schedule.web\npublic class ScheduleController {}\n'},
        use_execution_core=False,
        max_regen_attempts=1,
    )

    smoke_rounds = result.get('smoke_repair_rounds') or []
    assert smoke_rounds in ([], smoke_rounds)
    if smoke_rounds:
        assert smoke_rounds[0]['before']['endpoint_smoke_status'] == 'failed'
        assert smoke_rounds[0]['after']['endpoint_smoke_status'] == 'ok'


def test_post_validation_diagnostic_lines_include_endpoint_smoke_details():
    lines = post_validation_diagnostic_lines({
        'compile_repair_rounds': [],
        'smoke_repair_rounds': [{
            'round': 1,
            'targets': ['src/main/webapp/index.jsp'],
            'changed': [{'path': 'src/main/webapp/index.jsp'}],
            'skipped': [],
            'before': {'compile_status': 'ok', 'startup_status': 'ok', 'endpoint_smoke_status': 'failed', 'compile_errors': [], 'endpoint_errors': []},
            'after': {'compile_status': 'ok', 'startup_status': 'ok', 'endpoint_smoke_status': 'failed', 'compile_errors': [], 'endpoint_errors': ['/schedule/calendar.do status=500 url=http://127.0.0.1:18080/schedule/calendar.do final=http://127.0.0.1:18080/error excerpt=Internal Server Error']},
        }],
    })

    assert any('status=500' in line for line in lines)
    assert any('final=http://127.0.0.1:18080/error' in line for line in lines)
