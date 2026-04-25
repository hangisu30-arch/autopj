from pathlib import Path

from app.ui.state import ProjectConfig


def test_main_window_contains_modify_mode_ui_controls() -> None:
    source = Path('app/ui/main_window.py').read_text(encoding='utf-8')
    assert '작업 모드' in source
    assert 'self.operation_mode_combo = QComboBox()' in source
    assert 'self.operation_mode_combo.addItem("신규 생성", "create")' in source
    assert 'self.operation_mode_combo.addItem("기존 프로젝트 수정", "modify")' in source
    assert 'def _update_operation_mode_state(self) -> None:' in source
    assert 'def _validate_run_preconditions(self) -> bool:' in source


def test_project_config_effective_requirements_include_modify_mode_block() -> None:
    cfg = ProjectConfig(project_name='demo', operation_mode='modify', extra_requirements='회원관리 수정')
    text = cfg.normalize().effective_extra_requirements()
    assert '[WORK MODE CONFIRMED SETTINGS - SOURCE OF TRUTH]' in text
    assert 'modify_existing_project' in text
    assert '기존 프로젝트 수정' in text
    assert '관련 파일만 수정' in text
