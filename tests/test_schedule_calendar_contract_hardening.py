from pathlib import Path
from types import SimpleNamespace

from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import auto_repair_generated_project
from execution_core.builtin_crud import builtin_file, schema_for


def _schedule_schema():
    return schema_for(
        "Schedule",
        inferred_fields=[
            ("scheduleId", "schedule_id", "Long"),
            ("title", "title", "String"),
            ("content", "content", "String"),
            ("startDatetime", "start_datetime", "java.util.Date"),
            ("endDatetime", "end_datetime", "java.util.Date"),
            ("statusCd", "status_cd", "String"),
            ("priorityCd", "priority_cd", "String"),
            ("location", "location", "String"),
        ],
        feature_kind="SCHEDULE",
    )


def test_builtin_schedule_calendar_jsp_has_ssr_grid_and_safe_title():
    body = builtin_file("jsp/schedule/scheduleCalendar.jsp", "egovframework.demo", _schedule_schema())
    assert 'items="${calendarCells}"' in body
    assert 'items="${selectedDateSchedules}"' in body
    assert 'not empty currentYear and not empty currentMonth' in body
    assert 'data-role="calendar-grid"></div>' not in body


def test_validator_and_auto_repair_harden_shell_only_calendar_and_contract(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/demo/schedule/web/ScheduleController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.demo.schedule.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.ui.Model;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller @RequestMapping("/schedule") public class ScheduleController {\n'
        '  @GetMapping("/calendar.do") public String calendar(Model model) { return "schedule/scheduleCalendar"; }\n'
        '}\n',
        encoding='utf-8',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>\n'
        '<html><body><div class="calendar-shell"><div class="page-card schedule-page">\n'
        '<div class="calendar-toolbar"><h2><c:out value="${currentYear}"/>년 <c:out value="${currentMonth}"/>월</h2></div>\n'
        '<div class="schedule-layout"><div class="calendar-board card-panel"><div class="calendar-weekdays"></div><div class="calendar-grid" data-role="calendar-grid"></div></div>\n'
        '<div class="schedule-sidepanel right-bottom-area"><div data-role="schedule-list"></div></div></div></div></div></body></html>',
        encoding='utf-8',
    )

    report = validate_generated_project(tmp_path, SimpleNamespace(frontend_key='jsp'), run_runtime=False)
    codes = {item['code'] for item in report['issues']}
    assert 'calendar_ssr_missing' in codes
    assert 'calendar_data_contract_missing' in codes

    repair = auto_repair_generated_project(tmp_path, {'static_issues': report['issues']})
    assert repair['changed_count'] >= 2

    repaired_report = validate_generated_project(tmp_path, SimpleNamespace(frontend_key='jsp'), run_runtime=False)
    repaired_codes = {item['code'] for item in repaired_report['issues']}
    assert 'calendar_ssr_missing' not in repaired_codes
    assert 'calendar_data_contract_missing' not in repaired_codes

    repaired_jsp = jsp.read_text(encoding='utf-8')
    repaired_controller = controller.read_text(encoding='utf-8')
    assert 'items="${calendarCells}"' in repaired_jsp
    assert 'items="${selectedDateSchedules}"' in repaired_jsp
    assert 'model.addAttribute("calendarCells"' in repaired_controller
    assert 'model.addAttribute("currentYear"' in repaired_controller
