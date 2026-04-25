from pathlib import Path

from app.validation.post_generation_repair import _ensure_jsp_common_header, _ensure_jsp_domain_header_aliases, _validate_jsp_include_consistency
from app.io.execution_core_apply import _ensure_jsp_header_file, _ensure_jsp_domain_header_alias_files


def test_domain_header_alias_materialized_and_validator_accepts(tmp_path: Path):
    base = tmp_path / 'src/main/webapp/WEB-INF/views/if'
    base.mkdir(parents=True, exist_ok=True)
    _ensure_jsp_common_header(tmp_path)
    jsp = base / 'ifCalendar.jsp'
    jsp.write_text('<%@ include file="/WEB-INF/views/if/_header.jsp" %>\n<div>ok</div>\n', encoding='utf-8')
    assert _ensure_jsp_domain_header_aliases(tmp_path) is True
    alias = tmp_path / 'src/main/webapp/WEB-INF/views/if/_header.jsp'
    assert alias.exists()
    issues = _validate_jsp_include_consistency(tmp_path, [])
    assert not [x for x in issues if '_header.jsp' in x.get('reason', '')]


def test_execution_core_creates_domain_header_alias(tmp_path: Path):
    _ensure_jsp_header_file(tmp_path)
    base = tmp_path / 'src/main/webapp/WEB-INF/views/if'
    base.mkdir(parents=True, exist_ok=True)
    (base / 'ifCalendar.jsp').write_text('<%@ include file="/WEB-INF/views/if/_header.jsp" %>\n', encoding='utf-8')
    created = _ensure_jsp_domain_header_alias_files(tmp_path)
    assert 'src/main/webapp/WEB-INF/views/if/_header.jsp' in created
    assert (tmp_path / 'src/main/webapp/WEB-INF/views/if/_header.jsp').exists()
