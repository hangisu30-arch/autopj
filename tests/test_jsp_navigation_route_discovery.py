from pathlib import Path

from app.io.execution_core_apply import _patch_generated_jsp_assets


class _ScheduleSchema:
    entity_var = "schedule"
    feature_kind = "SCHEDULE"
    routes = {
        "calendar": "/schedule/scheduleCalendar.do",
        "detail": "/schedule/view.do",
        "form": "/schedule/edit.do",
    }


def test_route_discovery_prefers_real_controller_routes_and_skips_required_detail(tmp_path: Path):
    controller = tmp_path / "src/main/java/egovframework/retest/schedule/web/ScheduleController.java"
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        """package egovframework.retest.schedule.web;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Controller
@RequestMapping(\"/schedule\")
public class ScheduleController {

    @GetMapping(\"/calendar.do\")
    public String list(Model model) {
        return \"schedule/scheduleCalendar\";
    }

    @GetMapping(\"/view.do\")
    public String detail(@RequestParam(\"scheduleId\") String scheduleId, Model model) {
        return \"schedule/scheduleDetail\";
    }

    @GetMapping(\"/edit.do\")
    public String form(@RequestParam(value = \"scheduleId\", required = false) String scheduleId, Model model) {
        return \"schedule/scheduleForm\";
    }
}
""",
        encoding="utf-8",
    )

    view = tmp_path / "src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp"
    view.parent.mkdir(parents=True, exist_ok=True)
    view.write_text('<html><head></head><body>calendar</body></html>', encoding='utf-8')

    report = _patch_generated_jsp_assets(
        tmp_path,
        ["src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp"],
        "Schedule",
        {"Schedule": _ScheduleSchema()},
    )

    index_body = (tmp_path / report["index_jsp"]).read_text(encoding="utf-8")
    header = (tmp_path / report["header_jsp"]).read_text(encoding="utf-8")
    leftnav = (tmp_path / report["leftnav_jsp"]).read_text(encoding="utf-8")

    assert 'response.sendRedirect' in index_body and '/schedule/calendar.do' in index_body
    assert '/schedule/calendar.do' in header
    assert '/schedule/edit.do' in leftnav
    assert '/schedule/view.do' not in leftnav
    assert '/schedule/scheduleCalendar.do' not in index_body
    assert report["main_route"] == "/schedule/calendar.do"
