from pathlib import Path

from app.validation.post_generation_repair import _validate_controller_jsp_consistency, _ensure_jsp_common_header, _ensure_jsp_common_footer, _normalize_schedule_controller_views, _validate_jsp_include_consistency


def test_schedule_controller_view_name_and_route_are_normalized(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/demo/schedule/web/ScheduleController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text("""package egovframework.demo.schedule.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
@Controller
@RequestMapping("/schedule")
public class ScheduleController {
  @GetMapping("/list.do")
  public String list(){ return "schedule/scheduleList"; }
}
""", encoding='utf-8')
    changed = _normalize_schedule_controller_views(tmp_path)
    assert changed
    issues = _validate_controller_jsp_consistency(tmp_path)
    assert not any('schedule controller' in x['reason'] for x in issues)
    low = controller.read_text(encoding='utf-8').lower()
    assert '@getmapping("/calendar.do")' in low
    assert 'return "schedule/schedulecalendar"' in low


def test_missing_header_include_is_detected_and_header_can_be_created(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<%@ include file="/WEB-INF/views/common/header.jsp" %>\n<div>ok</div>', encoding='utf-8')
    issues = _validate_jsp_include_consistency(tmp_path, ['src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'])
    assert issues
    created = _ensure_jsp_common_header(tmp_path)
    assert created
    issues = _validate_jsp_include_consistency(tmp_path, ['src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'])
    assert not issues


def test_missing_footer_include_is_detected_and_footer_can_be_created(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<%@ include file="/WEB-INF/views/common/footer.jsp" %>\n<div>ok</div>', encoding='utf-8')
    issues = _validate_jsp_include_consistency(tmp_path, ['src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'])
    assert issues
    created = _ensure_jsp_common_footer(tmp_path)
    assert created
    issues = _validate_jsp_include_consistency(tmp_path, ['src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'])
    assert not issues
