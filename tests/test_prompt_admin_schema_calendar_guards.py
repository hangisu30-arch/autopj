from app.ui.prompt_templates import build_gemini_json_fileops_prompt
from app.ui.state import ProjectConfig


def test_prompt_includes_db_comment_reflection_admin_guard_and_no_implicit_calendar_rule():
    cfg = ProjectConfig(project_name='demo', frontend_key='jsp', frontend_label='jsp')
    prompt = build_gemini_json_fileops_prompt(cfg)
    assert '실제 DB 물리 테이블에 반영' in prompt
    assert '관리자 권한' in prompt
    assert 'calendar/캘린더/달력 화면이 명시된 경우에만 생성' in prompt
