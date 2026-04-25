from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.io.execution_core_apply import _patch_generated_jsp_assets
from app.validation.post_generation_repair import _validate_jsp_asset_consistency
from app.ui.state import ProjectConfig
from execution_core.builtin_crud import _guess_java_type, schema_for


def test_guess_java_type_recognizes_datetime_and_date_names():
    assert _guess_java_type('startDatetime', 'start_datetime') == 'java.util.Date'
    assert _guess_java_type('endTime', 'end_time') == 'java.util.Date'
    assert _guess_java_type('startDate', 'start_date') == 'java.util.Date'


def test_patch_generated_jsp_assets_uses_temporal_components_even_when_schema_types_are_string(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleForm.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        """<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<form action="<c:url value='/schedule/save.do'/>" method="post">
  <p>Start Datetime<br/><input type="text" name="startDatetime"/></p>
  <p>End Datetime<br/><input type="text" name="endDatetime"/></p>
  <p>Start Date<br/><input type="text" name="startDate"/></p>
  <p>End Date<br/><input type="text" name="endDate"/></p>
</form>
""",
        encoding='utf-8',
    )
    schema = schema_for(
        'Schedule',
        [
            ('scheduleId', 'schedule_id', 'Long'),
            ('startDatetime', 'start_datetime', 'String'),
            ('endDatetime', 'end_datetime', 'String'),
            ('startDate', 'start_date', 'String'),
            ('endDate', 'end_date', 'String'),
        ],
        table='schedule',
        feature_kind='SCHEDULE',
    )
    cfg = ProjectConfig(project_name='demo', frontend_key='jsp', frontend_label='jsp')
    _patch_generated_jsp_assets(tmp_path, [str(jsp.relative_to(tmp_path)).replace('\\', '/')], 'Schedule', {'Schedule': schema}, cfg)
    body = jsp.read_text(encoding='utf-8')
    assert 'name="startDatetime"' in body and 'type="datetime-local"' in body
    assert 'name="endDatetime"' in body and 'type="datetime-local"' in body
    assert 'name="startDate"' in body and 'type="date"' in body
    assert 'name="endDate"' in body and 'type="date"' in body


def test_validate_jsp_asset_consistency_checks_index_redirect_quality(tmp_path: Path):
    index = tmp_path / 'src/main/webapp/index.jsp'
    css = tmp_path / 'src/main/webapp/css/common.css'
    view = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'
    index.parent.mkdir(parents=True, exist_ok=True)
    css.parent.mkdir(parents=True, exist_ok=True)
    view.parent.mkdir(parents=True, exist_ok=True)
    css.write_text('body {}', encoding='utf-8')
    view.write_text(
        """<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ include file="/WEB-INF/views/common/header.jsp" %>
<link rel="stylesheet" href="${pageContext.request.contextPath}/css/common.css" />""",
        encoding='utf-8',
    )
    index.write_text('<html><body>broken</body></html>', encoding='utf-8')

    issues = _validate_jsp_asset_consistency(tmp_path, ['src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'])
    reasons = {item['reason'] for item in issues if item['path'] == 'src/main/webapp/index.jsp'}
    assert 'index.jsp missing server redirect' in reasons
    assert 'index.jsp missing target route' in reasons
