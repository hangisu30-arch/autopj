from pathlib import Path

from app.io.execution_core_apply import _build_entity_calendar_jsp, _normalize_calendar_jsp


class _ScheduleSchema:
    entity = "Schedule"
    entity_var = "schedule"
    feature_kind = "SCHEDULE"
    id_prop = "scheduleId"
    fields = [
        ("scheduleId", "schedule_id", "Long"),
        ("title", "title", "String"),
        ("content", "content", "String"),
        ("startDatetime", "start_datetime", "java.util.Date"),
        ("endDatetime", "end_datetime", "java.util.Date"),
        ("statusCd", "status_cd", "String"),
        ("priorityCd", "priority_cd", "String"),
        ("location", "location", "String"),
    ]
    routes = {
        "calendar": "/schedule/calendar.do",
        "detail": "/schedule/detail.do",
        "form": "/schedule/form.do",
        "save": "/schedule/save.do",
        "delete": "/schedule/delete.do",
    }


def test_entity_calendar_jsp_prefers_calendar_board_and_server_rendered_fallbacks():
    body = _build_entity_calendar_jsp(_ScheduleSchema())
    assert body.index('calendar-board card-panel') < body.index('schedule-sidepanel right-bottom-area')
    assert 'items="${calendarCells}"' in body
    assert 'items="${selectedDateSchedules}"' in body
    assert 'schedule-event-list' in body
    assert 'data-role="schedule-list"' in body
    assert 'currentYear' in body and 'currentMonth' in body


def test_normalize_calendar_jsp_rewrites_old_autopj_calendar_layout(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<html><body>
<div class="calendar-shell">
  <div class="page-card schedule-page" data-autopj-schedule-page>
    <div class="schedule-layout">
      <div class="schedule-sidepanel right-bottom-area"><div data-role="schedule-list"></div></div>
      <div class="calendar-board card-panel"><div class="calendar-grid" data-role="calendar-grid"></div></div>
    </div>
    <div class="autopj-hidden" data-role="selected-date-schedules-source"></div>
    <div class="autopj-hidden" data-role="schedule-source"></div>
  </div>
</div>
</body></html>''',
        encoding='utf-8',
    )

    assert _normalize_calendar_jsp(tmp_path, str(jsp.relative_to(tmp_path)).replace('\\', '/'), _ScheduleSchema())
    body = jsp.read_text(encoding='utf-8')
    assert body.index('calendar-board card-panel') < body.index('schedule-sidepanel right-bottom-area')
    assert 'items="${calendarCells}"' in body
    assert 'items="${selectedDateSchedules}"' in body
    assert 'schedule-event-list' in body
