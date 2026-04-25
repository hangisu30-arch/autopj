from pathlib import Path


def test_main_window_contains_last_form_state_ui_and_methods() -> None:
    source = Path('app/ui/main_window.py').read_text(encoding='utf-8')
    assert '이전 입력 불러오기' in source
    assert '초기화' in source
    assert 'def collect_current_form_state(self) -> dict:' in source
    assert 'def apply_form_state(self, state: dict | None) -> None:' in source
    assert 'def clear_form_state(self) -> None:' in source
    assert 'def save_last_form_state(self) -> bool:' in source
    assert 'def load_last_form_state(self) -> dict | None:' in source
    assert 'def on_clear_form(self) -> None:' in source
    assert 'def on_load_last_form_state(self) -> None:' in source


def test_main_window_excludes_sensitive_db_password_from_persisted_form_state() -> None:
    source = Path('app/ui/main_window.py').read_text(encoding='utf-8')
    assert '"db_password", "kind": "line", "widget": self.db_pw_edit' in source
    assert '"persist": False' in source
    assert 'if spec.get("sensitive"):' in source
    assert 'payload["fields"][key]' in source
    assert 'AUTOPJ_LAST_FORM_STATE_PATH' in source
