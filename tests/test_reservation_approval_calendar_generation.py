from execution_core.builtin_crud import FEATURE_KIND_SCHEDULE, builtin_file, infer_schema_from_plan, schema_for
from app.io.execution_core_apply import _build_entity_calendar_jsp


def _reservation_schema(*, approval_workflow: bool = False):
    return schema_for(
        'Reservation',
        [
            ('reservationId', 'reservation_id', 'String'),
            ('roomId', 'room_id', 'String'),
            ('purpose', 'purpose', 'String'),
            ('startDatetime', 'start_datetime', 'String'),
            ('endDatetime', 'end_datetime', 'String'),
            ('statusCd', 'status_cd', 'String'),
        ],
        table='reservation',
        feature_kind=FEATURE_KIND_SCHEDULE,
        approval_workflow=approval_workflow,
    )


def test_schedule_schema_infers_approval_workflow_and_route_from_requirements():
    plan = {
        'requirements_text': '사용자가 예약을 요청하면 관리자 승인 후 달력에 반영되어야 한다.',
        'tasks': [
            {'path': 'src/main/java/egovframework/test/reservation/web/ReservationController.java'},
        ],
    }

    schema = infer_schema_from_plan(plan)

    assert schema.approval_workflow is True
    assert schema.routes['approve'] == '/reservation/approve.do'


def test_schedule_controller_generation_separates_requested_and_approved_calendar_flow():
    schema = _reservation_schema(approval_workflow=True)

    body = builtin_file('java/controller/ReservationController.java', 'egovframework.test', schema)

    assert '@PostMapping("/approve.do")' in body
    assert 'private String requestedCode;' in body
    assert 'private String approvedCode;' in body
    assert 'calendarSchedules = new ArrayList<>()' in body
    assert 'requestMap.computeIfAbsent' in body
    assert 'if (_matchesCode(row.getStatusCd(), approvedCode))' in body
    assert 'model.addAttribute("visibleScheduleCount", calendarSchedules.size())' in body
    assert 'model.addAttribute("approvalWorkflow", true);' in body
    assert 'vo.setStatusCd(requestedCode);' in body


def test_schedule_calendar_jsp_prefers_existing_business_field_over_optional_remark_and_renders_approval_action():
    schema = _reservation_schema(approval_workflow=True)

    body = builtin_file('jsp/reservationCalendar.jsp', 'egovframework.test', schema)
    repaired_body = _build_entity_calendar_jsp(schema)

    assert 'row.purpose' in body
    assert 'row.remark' not in body
    assert 'requestCode' not in body  # guard against typo in generated template
    assert 'requestedCode' in body
    assert '/reservation/approve.do' in body

    assert 'row.purpose' in repaired_body
    assert 'row.remark' not in repaired_body
    assert '/reservation/approve.do' in repaired_body
    assert '${scheduleCount}' in repaired_body
    assert '${visibleScheduleCount}' in repaired_body
