from app.ui.fallback_builder import build_builtin_fallback_content


def test_schedule_controller_fallback_uses_calendar_route():
    path = 'src/main/java/egovframework/worktest/schedule/web/ScheduleController.java'
    spec = '달력 기반 일정관리시스템 schedule calendar 메인 화면은 월간 달력이며 list.do 금지'
    content = build_builtin_fallback_content(path, spec, project_name='worktest')
    lower = content.lower()
    assert '@getmapping("/calendar.do")' in lower
    assert '@getmapping("/list.do")' not in lower
    assert 'return "schedule/schedulecalendar"' in lower



def test_schedule_calendar_jsp_fallback_uses_ssr_contract():
    path = 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'
    spec = '달력 기반 일정관리시스템 schedule calendar 메인 화면은 월간 달력이며 SSR 계약을 포함해야 한다'
    content = build_builtin_fallback_content(path, spec, project_name='worktest')
    lower = content.lower()
    assert 'items="${calendarcells}"' in lower
    assert 'items="${selecteddateschedules}"' in lower
    assert 'data-autopj-schedule-page' in lower
    assert '<c:choose>' in lower


def test_schedule_form_jsp_fallback_avoids_nested_form_markup():
    path = 'src/main/webapp/WEB-INF/views/schedule/scheduleForm.jsp'
    spec = '일정 등록 수정 화면은 저장과 삭제를 지원하지만 중첩 form 은 금지'
    content = build_builtin_fallback_content(path, spec, project_name='worktest')
    lower = content.lower()
    assert lower.count('<form') == 1
    assert 'formaction=' in lower
