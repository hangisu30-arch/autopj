
from pathlib import Path

from app.validation.backend_compile_repair import collect_compile_repair_targets
from app.validation.post_generation_repair import validate_and_repair_generated_files
from app.validation.runtime_smoke import run_backend_compile
from app.ui.state import ProjectConfig


def test_run_backend_compile_clears_stale_outputs_and_uses_clean_compile(tmp_path: Path, monkeypatch):
    (tmp_path / 'pom.xml').write_text('<project/>', encoding='utf-8')
    (tmp_path / 'mvnw').write_text('#!/bin/sh\n', encoding='utf-8')
    stale = tmp_path / 'target/classes/demo'
    stale.mkdir(parents=True, exist_ok=True)
    (stale / 'Stale.class').write_bytes(b'x')

    captured = {}

    def fake_run_compile(candidate, project_root, timeout_seconds=300):
        captured['command'] = candidate['command']
        captured['project_root'] = project_root
        return {'status': 'ok', 'tool': candidate.get('tool'), 'family': candidate.get('family'), 'errors': []}

    monkeypatch.setattr('app.validation.runtime_smoke._run_compile', fake_run_compile)
    result = run_backend_compile(tmp_path)

    assert result['status'] == 'ok'
    assert result['clean_compile_required'] is True
    assert 'target/classes' in result['stale_outputs_removed']
    assert not (tmp_path / 'target/classes').exists()
    assert captured['command'][-2:] == ['clean', 'compile']


def test_collect_compile_repair_targets_expands_related_domain_files_from_startup_unresolved(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/rtest/schedule/web/ScheduleController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text('class ScheduleController {}', encoding='utf-8')
    service = tmp_path / 'src/main/java/egovframework/rtest/schedule/service/ScheduleService.java'
    service.parent.mkdir(parents=True, exist_ok=True)
    service.write_text('interface ScheduleService {}', encoding='utf-8')
    impl = tmp_path / 'src/main/java/egovframework/rtest/schedule/service/impl/ScheduleServiceImpl.java'
    impl.parent.mkdir(parents=True, exist_ok=True)
    impl.write_text('class ScheduleServiceImpl {}', encoding='utf-8')
    mapper = tmp_path / 'src/main/resources/egovframework/mapper/schedule/ScheduleMapper.xml'
    mapper.parent.mkdir(parents=True, exist_ok=True)
    mapper.write_text('<mapper/>', encoding='utf-8')
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<html/>', encoding='utf-8')

    runtime_report = {
        'compile': {'status': 'ok', 'errors': []},
        'startup': {
            'status': 'failed',
            'errors': [{'code': 'unresolved_compilation', 'message': 'Compiled class contains unresolved compilation problems'}],
            'log_tail': """
            Error creating bean with name 'scheduleController' defined in file [C:/workspace/rtest/target/classes/egovframework/rtest/schedule/web/ScheduleController.class]:
            nested exception is java.lang.Error: Unresolved compilation problems:
            """,
        },
    }

    targets = collect_compile_repair_targets(runtime_report, manifest={}, project_root=tmp_path)
    assert 'src/main/java/egovframework/rtest/schedule/web/ScheduleController.java' in targets
    assert 'src/main/java/egovframework/rtest/schedule/service/ScheduleService.java' in targets
    assert 'src/main/java/egovframework/rtest/schedule/service/impl/ScheduleServiceImpl.java' in targets
    assert 'src/main/resources/egovframework/mapper/schedule/ScheduleMapper.xml' in targets
    assert 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp' in targets


def test_post_generation_repair_retries_when_startup_hits_unresolved_compilation(tmp_path: Path, monkeypatch):
    rel = 'src/main/java/egovframework/rtest/schedule/web/ScheduleController.java'
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("package egovframework.rtest.schedule.web;\nimport org.springframework.stereotype.Controller;\nimport org.springframework.web.bind.annotation.GetMapping;\nimport org.springframework.web.bind.annotation.RequestMapping;\n@Controller\n@RequestMapping(\"/schedule\")\npublic class ScheduleController { @GetMapping(\"/calendar.do\") public String calendar(){ return \"schedule/scheduleCalendar\"; } }\n", encoding='utf-8')
    (tmp_path / 'pom.xml').write_text("<project/>\n", encoding='utf-8')
    index_jsp = tmp_path / 'src/main/webapp/index.jsp'
    index_jsp.parent.mkdir(parents=True, exist_ok=True)
    index_jsp.write_text('<meta http-equiv="refresh" content="0; url=/schedule/calendar.do">', encoding='utf-8')
    cal_jsp = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'
    cal_jsp.parent.mkdir(parents=True, exist_ok=True)
    cal_jsp.write_text('<html><body>calendar</body></html>', encoding='utf-8')

    manifest_op = {'path': rel, 'purpose': 'controller', 'content': 'spec text'}
    report = {'created': [rel], 'overwritten': [], 'errors': [], 'patched': {}}
    cfg = ProjectConfig(project_name='demo', frontend_key='jsp', database_key='sqlite', backend_key='egov_spring')

    calls = {'count': 0}

    def fake_runtime(project_root: Path, backend_key: str = '', compile_timeout_seconds: int = 300, startup_timeout_seconds: int = 120):
        calls['count'] += 1
        if calls['count'] == 1:
            return {
                'ok': False,
                'status': 'failed',
                'compile': {'status': 'ok', 'command': 'mvnw.cmd -q -DskipTests clean compile', 'errors': []},
                'startup': {
                    'status': 'failed',
                    'errors': [{'code': 'unresolved_compilation', 'message': 'Compiled class contains unresolved compilation problems'}],
                    'log_tail': 'defined in file [C:/workspace/rtest/target/classes/egovframework/rtest/schedule/web/ScheduleController.class]: Unresolved compilation problems:',
                },
                'endpoint_smoke': {'status': 'skipped'},
            }
        return {
            'ok': True,
            'status': 'ok',
            'compile': {'status': 'ok', 'command': 'mvnw.cmd -q -DskipTests clean compile', 'errors': []},
            'startup': {'status': 'ok', 'command': 'mvnw.cmd -q -DskipTests spring-boot:run', 'errors': [], 'base_url': 'http://127.0.0.1:18080', 'port': 18080},
            'endpoint_smoke': {'status': 'ok', 'results': []},
        }

    monkeypatch.setattr('app.validation.post_generation_repair.run_spring_boot_runtime_validation', fake_runtime)
    monkeypatch.setattr(
        'app.validation.post_generation_repair.validate_generated_project',
        lambda project_root, cfg, manifest=None, include_runtime=False: {'ok': True, 'static_issue_count': 0, 'static_issues': []},
    )
    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_content', lambda rel, body, frontend_key='': (True, ''))

    regen_calls = []

    def fake_regen(source_path: str, purpose: str, spec: str, reason: str):
        regen_calls.append((source_path, reason))
        return {'path': source_path, 'content': "package egovframework.rtest.schedule.web;\nimport org.springframework.stereotype.Controller;\nimport org.springframework.web.bind.annotation.GetMapping;\nimport org.springframework.web.bind.annotation.RequestMapping;\n@Controller\n@RequestMapping(\"/schedule\")\npublic class ScheduleController { @GetMapping(\"/calendar.do\") public String calendar(){ return \"schedule/scheduleCalendar\"; } }\n"}

    result = validate_and_repair_generated_files(
        project_root=tmp_path,
        cfg=cfg,
        report=report,
        file_ops=[manifest_op],
        regenerate_callback=fake_regen,
        use_execution_core=False,
        max_regen_attempts=1,
    )

    assert result['ok'] is True
    assert calls['count'] >= 2
    assert regen_calls
    assert any(item['path'] == rel for item in result['compile_repair_rounds'][0]['changed'])


def test_post_generation_repair_reports_invalid_delta_and_retry_snapshots(tmp_path: Path, monkeypatch):
    rel = 'src/main/java/egovframework/rtest/schedule/web/ScheduleController.java'
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "package egovframework.rtest.schedule.web;\npublic class ScheduleController {}\n",
        encoding='utf-8',
    )
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
        return {
            'ok': False,
            'status': 'failed',
            'compile': {
                'status': 'failed',
                'command': 'cmd /c mvnw.cmd -q -DskipTests clean compile',
                'errors': [{'code': 'maven_wrapper_bootstrap', 'message': 'Maven wrapper bootstrap failed', 'snippet': ''}],
            },
            'startup': {'status': 'skipped'},
            'endpoint_smoke': {'status': 'skipped'},
        }

    validation_calls = {'count': 0}

    def fake_validate_generated_project(project_root, cfg, manifest=None, include_runtime=False):
        validation_calls['count'] += 1
        if validation_calls['count'] == 1:
            return {'ok': True, 'static_issue_count': 0, 'static_issues': []}
        return {
            'ok': False,
            'static_issue_count': 1,
            'static_issues': [{'path': 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp', 'message': 'calendar shell only'}],
        }

    monkeypatch.setattr('app.validation.post_generation_repair.run_spring_boot_runtime_validation', fake_runtime)
    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_content', lambda rel, body, frontend_key='': (True, ''))
    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_project', fake_validate_generated_project)
    monkeypatch.setattr('app.validation.post_generation_repair.apply_generated_project_auto_repair', lambda project_root, report: {'changed': [], 'skipped': [], 'changed_count': 0})

    result = validate_and_repair_generated_files(
        project_root=tmp_path,
        cfg=cfg,
        report=report,
        file_ops=file_ops,
        regenerate_callback=lambda source_path, purpose, spec, reason: {
            'path': source_path,
            'content': "package egovframework.rtest.schedule.web;\npublic class ScheduleController {}\n",
        },
        use_execution_core=False,
        max_regen_attempts=1,
    )

    delta = result.get('invalid_delta') or {}
    assert delta.get('added_count', 0) >= 1
    assert any((item.get('path') or '').endswith('scheduleCalendar.jsp') for item in delta.get('added') or [])
    rounds = result.get('compile_repair_rounds') or []
    assert rounds
    assert rounds[0].get('before', {}).get('compile_status') == 'failed'
    assert rounds[0].get('after', {}).get('compile_status') == 'failed'
