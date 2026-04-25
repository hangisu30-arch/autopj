from pathlib import Path

from app.io.execution_core_apply import _compact_frontend_content, _write_file
from app.adapters.jsp.jsp_prompt_builder import jsp_plan_to_prompt_text
from app.adapters.react.react_prompt_builder import react_plan_to_prompt_text


def test_compact_frontend_content_strips_autopj_hints_and_empty_wrappers():
    raw = '''<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<section>
  <p class="autopj-eyebrow">회원</p>
  <div class="autopj-form-hero__meta">
  </div>
  <div class="autopj-form-section-header">
    <div>
      <h3 class="autopj-section-title">기본 정보</h3>
    </div>
  </div>
  <label class="autopj-field">
    <span class="autopj-field__label">이름</span>
    <span class="autopj-field__hint">길게 설명</span>
    <input type="text"/>
  </label>
</section>
'''
    compact = _compact_frontend_content('src/main/webapp/WEB-INF/views/member/memberForm.jsp', raw)
    assert compact.count('<%@ taglib prefix="c"') == 1
    assert 'autopj-field__hint' not in compact
    assert 'autopj-form-hero__meta' not in compact
    assert '<div class="autopj-form-section-header">' not in compact
    assert '<h3 class="autopj-section-title">기본 정보</h3>' in compact


def test_write_file_applies_compaction(tmp_path: Path):
    project_root = tmp_path
    rel = 'src/main/webapp/WEB-INF/views/member/memberForm.jsp'
    raw = '<label><span class="autopj-field__hint">설명</span><input/></label>'
    status = _write_file(project_root, rel, raw, overwrite=True)
    body = (project_root / rel).read_text(encoding='utf-8')
    assert status == 'created'
    assert 'autopj-field__hint' not in body


def test_prompt_builders_request_compact_reuse_rules():
    jsp_prompt = jsp_plan_to_prompt_text({'project_name': 'p', 'domains': []})
    react_prompt = react_plan_to_prompt_text({'project_name': 'p', 'domains': []})
    assert 'compact JSP markup' in jsp_prompt
    assert 'Reuse shared components' in react_prompt
