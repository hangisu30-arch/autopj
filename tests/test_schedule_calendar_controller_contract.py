from pathlib import Path

from app.validation.generated_project_validator import validate_generated_project
from types import SimpleNamespace


def test_calendar_controller_missing_list_contract_is_reported(tmp_path: Path):
    controller = tmp_path / "src/main/java/egovframework/demo/schedule/web/ScheduleController.java"
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        "package egovframework.demo.schedule.web;\n"
        "import org.springframework.stereotype.Controller;\n"
        "import org.springframework.ui.Model;\n"
        "import org.springframework.web.bind.annotation.GetMapping;\n"
        "import org.springframework.web.bind.annotation.RequestMapping;\n"
        "@Controller @RequestMapping(\"/schedule\") public class ScheduleController {\n"
        "  @GetMapping(\"/calendar.do\") public String calendar(Model model) {\n"
        "    model.addAttribute(\"calendarCells\", java.util.Collections.emptyList());\n"
        "    model.addAttribute(\"selectedDateSchedules\", java.util.Collections.emptyList());\n"
        "    model.addAttribute(\"currentYear\", 2026);\n"
        "    model.addAttribute(\"currentMonth\", 3);\n"
        "    model.addAttribute(\"prevYear\", 2026);\n"
        "    model.addAttribute(\"prevMonth\", 2);\n"
        "    model.addAttribute(\"nextYear\", 2026);\n"
        "    model.addAttribute(\"nextMonth\", 4);\n"
        "    return \"schedule/scheduleCalendar\";\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp"
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>\n'
        '<div class="page-card schedule-page" data-autopj-schedule-page data-current-year="${currentYear}" data-current-month="${currentMonth}" data-selected-date="${selectedDate}">\n'
        '  <div class="calendar-grid" data-role="calendar-grid">\n'
        '    <c:forEach var="cell" items="${calendarCells}"></c:forEach>\n'
        '  </div>\n'
        '  <div data-role="schedule-list"><c:forEach var="row" items="${selectedDateSchedules}"></c:forEach></div>\n'
        '  <div data-role="schedule-source"><c:forEach var="item" items="${list}"></c:forEach></div>\n'
        '</div>',
        encoding="utf-8",
    )

    report = validate_generated_project(tmp_path, SimpleNamespace(frontend_key='jsp'), run_runtime=False)
    issues = [item for item in report['issues'] if item['code'] == 'calendar_data_contract_missing']
    assert issues
    assert 'list' in issues[0]['details']['missing']
