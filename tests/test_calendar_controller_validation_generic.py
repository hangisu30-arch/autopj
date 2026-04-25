from app.ui.generated_content_validator import validate_generated_content


def test_generic_calendar_controller_accepts_entity_specific_calendar_view():
    body = """
package egovframework.demo.reservation.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/reservation")
public class ReservationController {
    @GetMapping("/calendar.do")
    public String calendar() {
        return "reservation/reservationCalendar";
    }
}
"""
    ok, reason = validate_generated_content('src/main/java/egovframework/demo/reservation/web/ReservationController.java', body)
    assert ok, reason


def test_generic_calendar_controller_rejects_wrong_calendar_view_name():
    body = """
package egovframework.demo.reservation.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/reservation")
public class ReservationController {
    @GetMapping("/calendar.do")
    public String calendar() {
        return "schedule/scheduleCalendar";
    }
}
"""
    ok, reason = validate_generated_content('src/main/java/egovframework/demo/reservation/web/ReservationController.java', body)
    assert not ok
    assert 'reservation/reservationCalendar' in reason
