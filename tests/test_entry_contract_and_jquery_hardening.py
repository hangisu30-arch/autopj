from pathlib import Path

from app.ui.generated_content_validator import validate_generated_content
from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair
from app.validation.backend_compile_repair import regenerate_compile_failure_targets


class DummyCfg:
    project_name = "ttte"
    frontend_key = "jsp"


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_generated_content_validator_allows_redirect_only_index_controller():
    body = '''package egovframework.ttte.index.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class IndexController {
    @GetMapping({"/", "/index.do"})
    public String index() {
        return "redirect:/schedule/calendar.do";
    }
}
'''
    ok, reason = validate_generated_content('src/main/java/egovframework/ttte/index/web/IndexController.java', body)
    assert ok, reason


def test_validator_skips_calendar_mapping_for_redirect_only_index(tmp_path: Path):
    _write(tmp_path / 'src/main/java/egovframework/ttte/index/web/IndexController.java', '''package egovframework.ttte.index.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
@Controller
public class IndexController {
    @GetMapping({"/", "/index.do"})
    public String index() { return "redirect:/schedule/calendar.do"; }
}
''')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/index/indexCalendar.jsp', '<html></html>')
    report = validate_generated_project(tmp_path, DummyCfg(), include_runtime=False, run_runtime=False)
    codes = {item['type'] for item in report['static_issues']}
    assert 'calendar_mapping_missing' not in codes
    assert 'calendar_data_contract_missing' not in codes


def test_jquery_dependency_respects_common_header_include(tmp_path: Path):
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/common/header.jsp', '<script src="${pageContext.request.contextPath}/js/jquery.min.js"></script>')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp', '<%@ include file="/WEB-INF/views/common/header.jsp" %><script>$(function(){ console.log(1); });</script>')
    report = validate_generated_project(tmp_path, DummyCfg(), include_runtime=False, run_runtime=False)
    messages = [item['message'] for item in report['static_issues']]
    assert 'jsp uses jquery syntax without jquery script include' not in messages


def test_jquery_auto_repair_injects_include(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'
    _write(jsp, '<html><body><script>$(function(){ alert(1); });</script></body></html>')
    apply_generated_project_auto_repair(
        tmp_path,
        {'issues': [{'code': 'jsp_dependency_missing', 'path': str(jsp.relative_to(tmp_path)).replace('\\', '/'), 'repairable': True, 'details': {'kind': 'jquery'}}]}
    )
    body = jsp.read_text(encoding='utf-8')
    assert '/js/jquery.min.js' in body


def test_compile_repair_normalizes_entry_controller_and_service_bundle(tmp_path: Path):
    index_path = tmp_path / 'src/main/java/egovframework/ttte/index/web/IndexController.java'
    _write(index_path, 'package egovframework.ttte.index.web;\nimport egovframework.ttte.index.service.IndexService;\npublic class IndexController {}\n')
    svc = tmp_path / 'src/main/java/egovframework/ttte/schedule/service/ScheduleService.java'
    _write(svc, 'package egovframework.ttte.schedule.service; public interface ScheduleService { int deleteSchedule(Long scheduleId) throws Exception; }')
    impl = tmp_path / 'src/main/java/egovframework/ttte/schedule/service/impl/ScheduleServiceImpl.java'
    _write(impl, 'package egovframework.ttte.schedule.service.impl; public class ScheduleServiceImpl implements egovframework.ttte.schedule.service.ScheduleService {}')
    mapper = tmp_path / 'src/main/java/egovframework/ttte/schedule/service/mapper/ScheduleMapper.java'
    _write(mapper, 'package egovframework.ttte.schedule.service.mapper; public interface ScheduleMapper {}')
    mapper_xml = tmp_path / 'src/main/resources/egovframework/mapper/schedule/ScheduleMapper.xml'
    _write(mapper_xml, '<mapper namespace="egovframework.ttte.schedule.service.mapper.ScheduleMapper"></mapper>')
    vo = tmp_path / 'src/main/java/egovframework/ttte/schedule/service/vo/ScheduleVO.java'
    _write(vo, 'package egovframework.ttte.schedule.service.vo; public class ScheduleVO { private String scheduleId; public String getScheduleId(){return scheduleId;} public void setScheduleId(String v){this.scheduleId=v;} }')
    controller = tmp_path / 'src/main/java/egovframework/ttte/schedule/web/ScheduleController.java'
    _write(controller, 'package egovframework.ttte.schedule.web; public class ScheduleController {}')

    manifest = {
        str(path.relative_to(tmp_path)).replace('\\', '/'): {
            'source_path': str(path.relative_to(tmp_path)).replace('\\', '/'),
            'purpose': 'generated',
            'spec': 'fields: schedule_id title content start_date end_date status_cd'
        }
        for path in [index_path, svc, impl, mapper, mapper_xml, vo, controller]
    }
    runtime_report = {'compile': {'errors': [
        {'code': 'package_missing', 'path': 'src/main/java/egovframework/ttte/index/web/IndexController.java', 'message': 'package egovframework.ttte.index.service does not exist'},
        {'code': 'override_mismatch', 'path': 'src/main/java/egovframework/ttte/schedule/service/impl/ScheduleServiceImpl.java', 'message': 'does not override abstract method deleteSchedule(java.lang.Long)'},
    ]}}

    result = regenerate_compile_failure_targets(tmp_path, DummyCfg(), manifest, runtime_report, None, lambda *args, **kwargs: {}, False, 'jsp')
    changed_paths = {item['path'] for item in result['changed']}
    assert 'src/main/java/egovframework/ttte/index/web/IndexController.java' in changed_paths
    assert 'src/main/java/egovframework/ttte/schedule/service/ScheduleService.java' in changed_paths
    assert 'src/main/java/egovframework/ttte/schedule/service/impl/ScheduleServiceImpl.java' in changed_paths
    index_body = index_path.read_text(encoding='utf-8')
    impl_body = impl.read_text(encoding='utf-8')
    assert 'redirect:' in index_body
    assert 'deleteSchedule' in impl_body
