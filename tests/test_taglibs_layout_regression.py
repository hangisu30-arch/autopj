from pathlib import Path

from app.validation.post_generation_repair import (
    _ensure_jsp_common_taglibs,
    _validate_jsp_include_consistency,
)
from app.io.execution_core_apply import _ensure_jsp_taglibs_file


def test_post_generation_creates_common_taglibs_and_resolves_layout_include(tmp_path: Path):
    layout = tmp_path / 'src/main/webapp/WEB-INF/views/common/layout.jsp'
    layout.parent.mkdir(parents=True, exist_ok=True)
    layout.write_text('<%@ include file="/WEB-INF/views/common/taglibs.jsp" %>\n<div>ok</div>\n', encoding='utf-8')

    assert _ensure_jsp_common_taglibs(tmp_path) is True
    issues = _validate_jsp_include_consistency(tmp_path, ['src/main/webapp/WEB-INF/views/common/layout.jsp'])
    assert not [x for x in issues if 'taglibs.jsp' in x.get('reason', '')]


def test_execution_core_writes_taglibs_partial(tmp_path: Path):
    rel = _ensure_jsp_taglibs_file(tmp_path)
    path = tmp_path / rel
    body = path.read_text(encoding='utf-8')
    assert 'jstl/core' in body
    assert 'jstl/fmt' in body
    assert 'jstl/functions' in body
