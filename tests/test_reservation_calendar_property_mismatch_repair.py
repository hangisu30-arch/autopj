from pathlib import Path
from types import SimpleNamespace

from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair, _safe_schedule_schema_for_domain


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_validator_and_repair_fix_missing_jsp_vo_property_on_reservation_calendar(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/reservation/service/vo/ReservationVO.java',
        '''package egovframework.test.reservation.service.vo;
public class ReservationVO {
    private String reservationId;
    private String roomId;
    private String purpose;
    private String startDatetime;
    private String endDatetime;
    private String statusCd;
    public String getReservationId(){ return reservationId; }
    public void setReservationId(String reservationId){ this.reservationId = reservationId; }
    public String getRoomId(){ return roomId; }
    public void setRoomId(String roomId){ this.roomId = roomId; }
    public String getPurpose(){ return purpose; }
    public void setPurpose(String purpose){ this.purpose = purpose; }
    public String getStartDatetime(){ return startDatetime; }
    public void setStartDatetime(String startDatetime){ this.startDatetime = startDatetime; }
    public String getEndDatetime(){ return endDatetime; }
    public void setEndDatetime(String endDatetime){ this.endDatetime = endDatetime; }
    public String getStatusCd(){ return statusCd; }
    public void setStatusCd(String statusCd){ this.statusCd = statusCd; }
}
''',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/reservation/web/ReservationController.java',
        '''package egovframework.test.reservation.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.ui.Model;
@Controller
@RequestMapping("/reservation")
public class ReservationController {
    @GetMapping("/calendar.do")
    public String calendar(Model model) {
        model.addAttribute("calendarCells", java.util.Collections.emptyList());
        model.addAttribute("selectedDateSchedules", java.util.Collections.emptyList());
        model.addAttribute("currentYear", 2026);
        model.addAttribute("currentMonth", 4);
        model.addAttribute("prevYear", 2026);
        model.addAttribute("prevMonth", 3);
        model.addAttribute("nextYear", 2026);
        model.addAttribute("nextMonth", 5);
        return "reservation/reservationCalendar";
    }
}
''',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/reservation/reservationCalendar.jsp',
        '''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<ul>
  <c:forEach items="${selectedDateSchedules}" var="row">
    <li>
      <p><c:out value="${row.purpose}"/></p>
      <p><c:choose><c:when test="${not empty row.remark}"><c:out value="${row.remark}"/></c:when><c:otherwise>상세 설명이 없습니다.</c:otherwise></c:choose></p>
    </li>
  </c:forEach>
</ul>''',
    )

    report = validate_generated_project(tmp_path, SimpleNamespace(frontend_key='jsp'), run_runtime=False)
    mismatch_issues = [i for i in report['static_issues'] if i['type'] == 'jsp_vo_property_mismatch']
    assert mismatch_issues
    assert mismatch_issues[0]['details']['missing_props'] == ['remark']

    repair = apply_generated_project_auto_repair(tmp_path, report)
    assert repair['changed_count'] >= 1

    body = (tmp_path / 'src/main/webapp/WEB-INF/views/reservation/reservationCalendar.jsp').read_text(encoding='utf-8')
    assert 'row.remark' not in body
    assert 'row.purpose' in body

    report_after = validate_generated_project(tmp_path, SimpleNamespace(frontend_key='jsp'), run_runtime=False)
    assert not any(i['type'] == 'jsp_vo_property_mismatch' for i in report_after['static_issues'])


def test_safe_schedule_schema_for_domain_does_not_inject_remark_when_project_fields_do_not_have_it(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/reservation/service/vo/ReservationVO.java',
        '''package egovframework.test.reservation.service.vo;
public class ReservationVO {
    private String reservationId;
    private String roomId;
    private String purpose;
    private String startDatetime;
    private String endDatetime;
    private String statusCd;
}
''',
    )
    _write(
        tmp_path / 'src/main/resources/egovframework/mapper/reservation/ReservationMapper.xml',
        '<mapper namespace="egovframework.test.reservation.service.mapper.ReservationMapper">SELECT reservation_id, room_id, purpose, start_datetime, end_datetime, status_cd FROM reservation</mapper>',
    )

    schema = _safe_schedule_schema_for_domain(tmp_path, 'reservation', 'Reservation')
    props = {prop for prop, _col, _jt in schema.fields}
    assert 'remark' not in props
    assert {'reservationId', 'roomId', 'purpose', 'startDatetime', 'endDatetime', 'statusCd'}.issubset(props)
