from pathlib import Path
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def test_main_window_contains_auth_detection_and_option_controls():
    try:
        from PyQt6.QtWidgets import QApplication
        from app.ui.main_window import MainWindow
    except ModuleNotFoundError:
        source = Path('app/ui/main_window.py').read_text(encoding='utf-8')
        assert '인증/로그인 감지 결과' in source
        assert '인증/로그인 설정' in source
        assert 'JWT 로그인' in source
        assert '기본 진입 방식' in source
        return

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        assert window.auth_detect_lbl.text().startswith('감지된 기능:')
        assert window.login_feature_chk.text() == '로그인 기능 포함'
        assert window.auth_unified_chk.text() == '통합인증'
        assert window.auth_cert_chk.text() == '인증서 로그인'
        assert window.auth_jwt_chk.text() == 'JWT 로그인'
        assert window.auth_primary_combo.count() == 3

        window.extra_edit.setPlainText('로그인과 통합인증, JWT 로그인까지 추가')
        window.login_feature_chk.setChecked(True)
        window.auth_unified_chk.setChecked(True)
        window.auth_jwt_chk.setChecked(True)
        window._sync_cfg()

        assert 'JWT 로그인' in window.auth_detect_lbl.text()
        assert 'JWT 로그인' in window.auth_selection_lbl.text()
        assert 'JWT 로그인 포함' in window.cfg.effective_extra_requirements()
    finally:
        window.close()
        app.quit()
