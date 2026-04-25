from pathlib import Path


def test_main_window_contains_registry_reset_controls():
    text = Path('app/ui/main_window.py').read_text(encoding='utf-8')
    assert '선택 초기화' in text
    assert '저장 목록 초기화' in text
    assert 'def _clear_registered_project_selection' in text
    assert 'def _reset_registered_projects' in text
    assert 'clear_registry()' in text
