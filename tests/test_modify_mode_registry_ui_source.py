from __future__ import annotations

from pathlib import Path


def test_main_window_contains_registry_modify_mode_ui():
    source = Path('app/ui/main_window.py').read_text(encoding='utf-8')
    assert '저장된 autopj 프로젝트' in source
    assert 'saved_projects_combo' in source
    assert 'validate_registered_project' in source
    assert '_register_successful_project' in source
    assert '저장된 autopj 프로젝트만 수정할 수 있습니다' in source or '저장된 autopj 프로젝트 목록' in source
