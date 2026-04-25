from pathlib import Path

from app.io.execution_core_apply import _patch_generated_jsp_assets
from app.ui.state import ProjectConfig
from execution_core.builtin_crud import schema_for


def test_patch_generated_jsp_assets_rewrites_form_and_uses_date_components(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleForm.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<form action="<c:url value=\'/schedule/save.do\'/>" method="post">\n'
        '  <p>Title<br/><input type="text" name="title"/></p>\n'
        '  <p>Start Datetime<br/><input type="text" name="startDatetime"/></p>\n'
        '  <p>End Date<br/><input type="text" name="endDate"/></p>\n'
        '</form>\n',
        encoding='utf-8',
    )
    schema = schema_for(
        'Schedule',
        [
            ('scheduleId', 'schedule_id', 'Long'),
            ('title', 'title', 'String'),
            ('startDatetime', 'start_datetime', 'java.time.LocalDateTime'),
            ('endDate', 'end_date', 'java.time.LocalDate'),
            ('content', 'content', 'String'),
        ],
        table='schedule',
        feature_kind='SCHEDULE',
    )
    cfg = ProjectConfig(project_name='demo', frontend_key='jsp', frontend_label='jsp')
    _patch_generated_jsp_assets(tmp_path, [str(jsp.relative_to(tmp_path)).replace('\\', '/')], 'Schedule', {'Schedule': schema}, cfg)
    body = jsp.read_text(encoding='utf-8')
    assert 'autopj-form-grid' in body
    assert 'type="datetime-local" name="startDatetime"' in body or 'name="startDatetime" class="form-control" value="<c:out value=\'${item.startDatetime}\'/>" step="1" type="datetime-local"' in body
    assert 'type="date" name="endDate"' in body or 'name="endDate" class="form-control" value="<c:out value=\'${item.endDate}\'/>" type="date"' in body
    assert '날짜/시간 항목은 캘린더 컴포넌트로 선택합니다.' in body
