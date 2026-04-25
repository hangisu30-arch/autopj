from pathlib import Path

from execution_core.builtin_crud import builtin_file, schema_for
from app.ui.generated_content_validator import validate_generated_content
from app.validation.post_generation_repair import _validate_controller_jsp_consistency


def _schedule_schema():
    fields = [
        ('scheduleId', 'schedule_id', 'Long'),
        ('title', 'title', 'String'),
        ('content', 'content', 'String'),
        ('startDatetime', 'start_datetime', 'java.util.Date'),
        ('endDatetime', 'end_datetime', 'java.util.Date'),
        ('statusCd', 'status_cd', 'String'),
        ('priorityCd', 'priority_cd', 'String'),
        ('location', 'location', 'String'),
        ('writerId', 'writer_id', 'String'),
        ('useYn', 'use_yn', 'String'),
        ('regDt', 'reg_dt', 'java.util.Date'),
        ('updDt', 'upd_dt', 'java.util.Date'),
    ]
    return schema_for('Schedule', fields, table='schedule', feature_kind='SCHEDULE')


def test_schedule_schema_routes_and_views_are_calendar_first():
    schema = _schedule_schema()
    assert schema.routes['calendar'] == '/schedule/calendar.do'
    assert 'list' not in schema.routes
    assert schema.views['calendar'] == 'schedule/scheduleCalendar'


def test_schedule_controller_uses_calendar_mapping_not_list():
    schema = _schedule_schema()
    controller = builtin_file('java/controller/ScheduleController.java', 'egovframework.demo', schema)
    assert controller is not None
    low = controller.lower()
    assert '@getmapping("/calendar.do")' in low
    assert '@getmapping("/list.do")' not in low
    assert 'return "schedule/schedulecalendar"' in low
    assert 'return "schedule/scheduledetail"' in low
    assert 'return "schedule/scheduleform"' in low
    assert '@initbinder' in low
    assert 'simpledateformat' in low


def test_schedule_jsp_and_controller_consistency_scan(tmp_path: Path):
    schema = _schedule_schema()
    project_root = tmp_path
    controller_rel = Path('src/main/java/egovframework/demo/schedule/web/ScheduleController.java')
    jsp_rel = Path('src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp')
    detail_rel = Path('src/main/webapp/WEB-INF/views/schedule/scheduleDetail.jsp')
    form_rel = Path('src/main/webapp/WEB-INF/views/schedule/scheduleForm.jsp')
    (project_root / controller_rel).parent.mkdir(parents=True, exist_ok=True)
    (project_root / jsp_rel).parent.mkdir(parents=True, exist_ok=True)
    (project_root / controller_rel).write_text(builtin_file('java/controller/ScheduleController.java', 'egovframework.demo', schema), encoding='utf-8')
    (project_root / jsp_rel).write_text(builtin_file('jsp/ScheduleList.jsp', 'egovframework.demo', schema), encoding='utf-8')
    (project_root / detail_rel).write_text(builtin_file('jsp/ScheduleDetail.jsp', 'egovframework.demo', schema), encoding='utf-8')
    (project_root / form_rel).write_text(builtin_file('jsp/ScheduleForm.jsp', 'egovframework.demo', schema), encoding='utf-8')

    ok, reason = validate_generated_content(str(controller_rel), (project_root / controller_rel).read_text(encoding='utf-8'), frontend_key='jsp')
    assert ok, reason
    issues = _validate_controller_jsp_consistency(project_root)
    assert issues == []
