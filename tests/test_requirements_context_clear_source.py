from pathlib import Path


def test_main_window_contains_requirements_context_clear_controls() -> None:
    source = Path('app/ui/main_window.py').read_text(encoding='utf-8')
    assert '요구사항 / 기능설명 초기화' in source
    assert 'def _clear_requirement_related_outputs(self) -> None:' in source
    assert 'def on_clear_requirements_context(self) -> None:' in source
    assert 'self.clear_requirements_context_btn.clicked.connect(self.on_clear_requirements_context)' in source


def test_requirements_context_clear_resets_outputs_and_internal_state() -> None:
    source = Path('app/ui/main_window.py').read_text(encoding='utf-8')
    assert 'self._last_gemini_json_ok = False' in source
    assert 'self._last_analysis_result = None' in source
    assert 'self._last_validation_report = None' in source
    assert 'self._last_repair_plan = None' in source
    assert '"gemini_out"' in source
    assert '"log_view"' in source
    assert 'self.extra_edit.clear()' in source
    assert 'self.status_lbl.setText("요구사항 / 기능설명 초기화 완료")' in source
