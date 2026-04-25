from execution_core.builtin_crud import schema_for
from execution_core.generator import _canonical_tasks_for_schema


def test_schedule_jsp_tasks_use_calendar_and_header():
    schema = schema_for('Schedule', feature_kind='schedule')
    tasks = _canonical_tasks_for_schema(schema, 'jsp')
    paths = [t['path'] for t in tasks]
    assert 'jsp/scheduleCalendar.jsp' in paths
    assert 'jsp/scheduleDetail.jsp' in paths
    assert 'jsp/scheduleForm.jsp' in paths
    assert 'jsp/common/header.jsp' in paths
    assert 'jsp/scheduleList.jsp' not in paths
