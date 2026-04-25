from pathlib import Path

from app.ui.state import ProjectConfig
from app.validation.generated_project_validator import validate_generated_project
from app.validation.runtime_smoke import _discover_controller_routes


INDEX_REDIRECT_CONTROLLER = '''package egovframework.rtest.index.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/index")
public class IndexController {

    @GetMapping("/calendar.do")
    public String calendar() {
        return "redirect:/schedule/calendar.do";
    }
}
'''


ENTRYPOINT_CONTROLLER = '''package egovframework.rtest.index.web;

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


def test_redirect_only_index_calendar_controller_does_not_require_calendar_model_contract(tmp_path: Path):
    controller = tmp_path / "src/main/java/egovframework/rtest/index/web/IndexController.java"
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(INDEX_REDIRECT_CONTROLLER, encoding="utf-8")

    jsp = tmp_path / "src/main/webapp/WEB-INF/views/index/indexCalendar.jsp"
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core" %>\n'
        '<div class="schedule-page">\n'
        '  <div class="calendar-grid"></div>\n'
        '  <c:forEach items="${calendarCells}" var="cell"></c:forEach>\n'
        '  <ul class="schedule-event-list"><c:forEach items="${selectedDateSchedules}" var="row"></c:forEach></ul>\n'
        '  <c:if test="${not empty currentYear and not empty currentMonth}">${currentYear}년 ${currentMonth}월</c:if>\n'
        '</div>',
        encoding="utf-8",
    )

    cfg = ProjectConfig(project_name="rtest", frontend_key="jsp", database_key="mysql", backend_key="egov_spring")
    report = validate_generated_project(tmp_path, cfg, manifest={"routes": []}, include_runtime=False)

    codes = {item["type"] for item in report["static_issues"]}
    assert "calendar_data_contract_missing" not in codes
    assert "calendar_view_mismatch" not in codes


def test_runtime_route_discovery_prefers_controller_entrypoints_over_raw_index_jsp(tmp_path: Path):
    controller = tmp_path / "src/main/java/egovframework/rtest/index/web/IndexController.java"
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(ENTRYPOINT_CONTROLLER, encoding="utf-8")

    routes = _discover_controller_routes(tmp_path)
    assert "/" in routes
    assert "/index.do" in routes
    assert "/index.jsp" not in routes


def test_runtime_route_discovery_skips_required_parameter_routes_and_does_not_assume_index_do(tmp_path: Path):
    controller = tmp_path / "src/main/java/egovframework/rtest/schedule/web/ScheduleController.java"
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        """package egovframework.rtest.schedule.web;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
@RequestMapping("/schedule")
public class ScheduleController {

    @GetMapping("/calendar.do")
    public String calendar(Model model) {
        return "schedule/scheduleCalendar";
    }

    @GetMapping("/view.do")
    public String detail(@RequestParam("id") Long id, Model model) {
        return "schedule/scheduleDetail";
    }
}
""",
        encoding="utf-8",
    )

    routes = _discover_controller_routes(tmp_path)
    assert "/" in routes
    assert "/schedule/calendar.do" in routes
    assert "/schedule/view.do" not in routes
    assert "/index.do" not in routes
