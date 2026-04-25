from pathlib import Path

from app.ui.state import ProjectConfig
from app.ui.template_generator import render_mvnw_cmd
from app.validation.post_generation_repair import validate_and_repair_generated_files
from app.validation.project_auto_repair import normalize_project_package_roots


def test_render_mvnw_cmd_has_no_control_characters_and_keeps_windows_paths():
    body = render_mvnw_cmd()
    assert '\x07' not in body
    assert '\x08' not in body
    assert '.mvn\\wrapper' in body
    assert '\\bin\\mvn.cmd' in body


def test_normalize_project_package_roots_rewrites_java_and_mapper_namespace(tmp_path: Path):
    project_root = tmp_path / 'rtest'
    controller = project_root / 'src/main/java/egovframework/test/index/web/IndexController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.index.web;\n'
        'import egovframework.test.schedule.service.ScheduleService;\n'
        'public class IndexController {}\n',
        encoding='utf-8',
    )
    mapper = project_root / 'src/main/resources/egovframework/mapper/schedule/ScheduleMapper.xml'
    mapper.parent.mkdir(parents=True, exist_ok=True)
    mapper.write_text(
        '<mapper namespace="egovframework.test.schedule.service.mapper.ScheduleMapper"></mapper>',
        encoding='utf-8',
    )

    changed = normalize_project_package_roots(project_root, ProjectConfig(project_name='rtest'))

    normalized_controller = project_root / 'src/main/java/egovframework/rtest/index/web/IndexController.java'
    assert normalized_controller.exists()
    body = normalized_controller.read_text(encoding='utf-8')
    assert 'package egovframework.rtest.index.web;' in body
    assert 'import egovframework.rtest.schedule.service.ScheduleService;' in body
    mapper_body = mapper.read_text(encoding='utf-8')
    assert 'egovframework.rtest.schedule.service.mapper.ScheduleMapper' in mapper_body
    assert changed


def test_post_generation_repair_stops_repeated_wrapper_bootstrap_and_excludes_debug_invalids(tmp_path: Path, monkeypatch):
    rel = 'src/main/java/egovframework/rtest/schedule/service/ScheduleService.java'
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('package egovframework.rtest.schedule.service;\npublic interface ScheduleService {}\n', encoding='utf-8')
    (tmp_path / 'pom.xml').write_text('<project/>\n', encoding='utf-8')
    (tmp_path / 'mvnw').write_text('#!/bin/sh\n', encoding='utf-8')
    (tmp_path / 'mvnw.cmd').write_text('broken wrapper\n', encoding='utf-8')
    props = tmp_path / '.mvn/wrapper/maven-wrapper.properties'
    props.parent.mkdir(parents=True, exist_ok=True)
    props.write_text('distributionUrl=broken\n', encoding='utf-8')

    def fake_runtime(project_root: Path, backend_key: str = '', compile_timeout_seconds: int = 300, startup_timeout_seconds: int = 120):
        return {
            'ok': False,
            'status': 'failed',
            'compile': {
                'status': 'failed',
                'command': 'cmd /c mvnw.cmd -q -DskipTests clean compile',
                'raw_output': 'Invoke-WebRequest : 경로에 잘못된 문자가 있습니다.\n[mvnw.cmd] Maven 배포본 다운로드에 실패했습니다.',
                'errors': [{'code': 'maven_wrapper_bootstrap', 'path': 'mvnw.cmd', 'message': 'Maven wrapper bootstrap failed'}],
            },
            'startup': {'status': 'skipped'},
            'endpoint_smoke': {'status': 'skipped'},
        }

    monkeypatch.setattr('app.validation.post_generation_repair.run_spring_boot_runtime_validation', fake_runtime)
    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_project', lambda project_root, cfg, manifest=None, include_runtime=False: {'ok': True, 'static_issue_count': 0, 'static_issues': []})
    monkeypatch.setattr('app.validation.post_generation_repair.validate_generated_content', lambda rel, body, frontend_key='': (True, ''))

    result = validate_and_repair_generated_files(
        project_root=tmp_path,
        cfg=ProjectConfig(project_name='rtest', frontend_key='jsp', database_key='sqlite', backend_key='egov_spring'),
        report={'created': [rel], 'overwritten': [], 'errors': [], 'patched': {}},
        file_ops=[{'path': rel, 'purpose': 'service', 'content': 'spec text'}],
        regenerate_callback=None,
        use_execution_core=False,
        max_regen_attempts=0,
    )

    rounds = result.get('compile_repair_rounds') or []
    assert len(rounds) == 1
    assert rounds[0].get('terminal_failure') == 'wrapper_bootstrap_repeated'
    remaining = result.get('remaining_invalid_files') or []
    assert not any((item.get('path') or '').startswith('.autopj_debug/') for item in remaining)
    assert result['ok'] is False
