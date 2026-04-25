from pathlib import Path

from app.ui.generated_content_validator import validate_generated_content
from app.validation.post_generation_repair import _normalize_jsp_layout_includes, _validate_jsp_include_consistency


def test_schedule_jsp_with_layout_include_is_invalid():
    body = '<%@ page contentType="text/html; charset=UTF-8" %>\n<%@ include file="/WEB-INF/views/_layout.jsp" %>\n<div>ok</div>'
    ok, reason = validate_generated_content('src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp', body, frontend_key='jsp')
    assert not ok
    assert '_layout.jsp' in reason


def test_missing_layout_include_is_normalized_to_header(tmp_path: Path):
    jsp_rel = 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'
    jsp_path = tmp_path / jsp_rel
    jsp_path.parent.mkdir(parents=True, exist_ok=True)
    jsp_path.write_text(
        '<%@ page contentType="text/html; charset=UTF-8" %>\n'
        '<%@ include file="/WEB-INF/views/_layout.jsp" %>\n'
        '<div>calendar</div>\n',
        encoding='utf-8',
    )
    changed = _normalize_jsp_layout_includes(tmp_path, [jsp_rel])
    assert changed == [jsp_rel]
    updated = jsp_path.read_text(encoding='utf-8')
    assert '/WEB-INF/views/common/header.jsp' in updated
    issues = _validate_jsp_include_consistency(tmp_path, [jsp_rel])
    assert issues == [{'path': jsp_rel, 'reason': 'jsp includes missing /WEB-INF/views/common/header.jsp'}]
