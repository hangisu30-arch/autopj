from app.ui.prompt_templates import build_gemini_json_fileops_prompt
from app.ui.state import ProjectConfig


def test_prompt_includes_form_calendar_and_active_menu_rules():
    cfg = ProjectConfig(project_name='demo', frontend_key='jsp', frontend_label='jsp')
    prompt = build_gemini_json_fileops_prompt(cfg)
    assert '달력 또는 일시 선택 컴포넌트' in prompt
    assert 'active 상태' in prompt
    assert 'grid/card 기반 섹션형 레이아웃' in prompt



def test_prompt_includes_entry_only_multifront_rule():
    cfg = ProjectConfig(project_name='demo', frontend_key='react', frontend_label='react')
    prompt = build_gemini_json_fileops_prompt(cfg)
    assert 'JSP/React/Vue/Nexacro 공통 규칙' in prompt
    assert 'entry 화면에 CRUD save/delete/list URL' in prompt
