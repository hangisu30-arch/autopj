from pathlib import Path

from app.validation.post_generation_repair import (
    _ensure_jsp_include_alias,
    _validate_jsp_include_consistency,
)
from app.io.execution_core_apply import _ensure_jsp_include_file


def test_include_jsp_alias_is_materialized_and_validator_accepts(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/if/ifCalendar.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<%@ include file="/WEB-INF/views/include.jsp" %>\n<div>ok</div>\n', encoding='utf-8')

    assert _ensure_jsp_include_alias(tmp_path) is True
    issues = _validate_jsp_include_consistency(tmp_path, ['src/main/webapp/WEB-INF/views/if/ifCalendar.jsp'])
    assert not [x for x in issues if 'include.jsp' in x.get('reason', '')]


def test_execution_core_creates_include_jsp_alias(tmp_path: Path):
    rel = _ensure_jsp_include_file(tmp_path)
    target = tmp_path / rel
    assert target.exists()
    body = target.read_text(encoding='utf-8')
    assert 'jstl/core' in body
    assert 'jstl/fmt' in body
    assert 'jstl/functions' in body
