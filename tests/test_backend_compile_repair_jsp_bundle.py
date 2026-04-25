from pathlib import Path

from app.validation.backend_compile_repair import regenerate_compile_failure_targets


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


class _Cfg:
    project_name = 'ttte'


def test_compile_repair_refreshes_schedule_jsp_with_builtin_contract(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'
    _write(jsp, '<html><body><div class="calendar-grid" data-role="calendar-grid"></div><script>$(function(){})</script></body></html>')
    _write(tmp_path / 'src/main/java/egovframework/ttte/schedule/service/ScheduleService.java', 'package egovframework.ttte.schedule.service; public interface ScheduleService { int deleteSchedule(Long scheduleId) throws Exception; }')
    _write(tmp_path / 'src/main/java/egovframework/ttte/schedule/service/impl/ScheduleServiceImpl.java', 'package egovframework.ttte.schedule.service.impl; public class ScheduleServiceImpl {}')

    manifest = {
        'src/main/java/egovframework/ttte/schedule/service/impl/ScheduleServiceImpl.java': {'source_path': 'spec/serviceimpl', 'purpose': 'generated', 'spec': '일정관리 달력 기반 시스템'},
        'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp': {'source_path': 'spec/calendar', 'purpose': 'generated', 'spec': '일정관리 달력 기반 시스템'}
    }
    runtime_report = {
        'compile': {
            'status': 'failed',
            'errors': [
                {'path': 'src/main/java/egovframework/ttte/schedule/service/impl/ScheduleServiceImpl.java', 'code': 'override_mismatch', 'message': 'does not override abstract method deleteSchedule(Long)'},
            ],
        },
        'startup': {'status': 'skipped'},
        'endpoint_smoke': {'status': 'skipped'},
    }

    result = regenerate_compile_failure_targets(
        project_root=tmp_path,
        cfg=_Cfg(),
        manifest=manifest,
        runtime_report=runtime_report,
        regenerate_callback=None,
        apply_callback=lambda *args, **kwargs: {},
        use_execution_core=False,
        frontend_key='jsp',
        max_attempts=1,
    )

    body = jsp.read_text(encoding='utf-8').lower()
    assert result['attempted'] is True
    assert 'items="${calendarcells}"' in body
    assert 'items="${selecteddateschedules}"' in body
    assert 'data-autopj-schedule-page' in body


def test_compile_repair_expands_controller_symbol_errors_to_contract_bundle(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/ttte/schedule/web/ScheduleController.java'
    service = tmp_path / 'src/main/java/egovframework/ttte/schedule/service/ScheduleService.java'
    service_impl = tmp_path / 'src/main/java/egovframework/ttte/schedule/service/impl/ScheduleServiceImpl.java'
    mapper = tmp_path / 'src/main/java/egovframework/ttte/schedule/service/mapper/ScheduleMapper.java'
    mapper_xml = tmp_path / 'src/main/resources/egovframework/mapper/schedule/ScheduleMapper.xml'
    for path_obj, body in [
        (controller, 'package egovframework.ttte.schedule.web; public class ScheduleController {}'),
        (service, 'package egovframework.ttte.schedule.service; public interface ScheduleService {}'),
        (service_impl, 'package egovframework.ttte.schedule.service.impl; public class ScheduleServiceImpl {}'),
        (mapper, 'package egovframework.ttte.schedule.service.mapper; public interface ScheduleMapper {}'),
        (mapper_xml, '<mapper namespace="egovframework.ttte.schedule.service.mapper.ScheduleMapper"></mapper>'),
    ]:
        _write(path_obj, body)

    manifest = {
        str(p.relative_to(tmp_path)).replace('\\', '/'): {'source_path': 'spec/' + p.stem, 'purpose': 'generated', 'spec': '일정관리 달력 기반 시스템'}
        for p in [controller, service, service_impl, mapper, mapper_xml]
    }
    runtime_report = {
        'compile': {
            'status': 'failed',
            'errors': [
                {'path': 'src/main/java/egovframework/ttte/schedule/web/ScheduleController.java', 'code': 'cannot_find_symbol', 'message': 'cannot find symbol'},
            ],
        },
        'startup': {'status': 'skipped'},
        'endpoint_smoke': {'status': 'skipped'},
    }

    result = regenerate_compile_failure_targets(
        project_root=tmp_path,
        cfg=_Cfg(),
        manifest=manifest,
        runtime_report=runtime_report,
        regenerate_callback=None,
        apply_callback=lambda *args, **kwargs: {},
        use_execution_core=False,
        frontend_key='jsp',
        max_attempts=1,
    )

    changed_paths = {item['path'] for item in result['changed']}
    assert 'src/main/java/egovframework/ttte/schedule/web/ScheduleController.java' in changed_paths
    assert 'src/main/java/egovframework/ttte/schedule/service/ScheduleService.java' in changed_paths
    assert 'src/main/java/egovframework/ttte/schedule/service/impl/ScheduleServiceImpl.java' in changed_paths
    assert 'src/main/java/egovframework/ttte/schedule/service/mapper/ScheduleMapper.java' in changed_paths
    assert 'src/main/resources/egovframework/mapper/schedule/ScheduleMapper.xml' in changed_paths
