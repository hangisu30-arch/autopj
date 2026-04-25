from pathlib import Path
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_main_window_contains_frontend_branch_summary_label():
    try:
        from PyQt6.QtWidgets import QApplication
        from app.ui.main_window import MainWindow
    except ModuleNotFoundError:
        source = Path("app/ui/main_window.py").read_text(encoding="utf-8")
        assert "생성 분기:" in source
        assert "frontend_branch_lbl" in source
        return

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        assert "JSP 선택: Controller + JSP + MyBatis + 서버 렌더링" in window.frontend_branch_lbl.text()
        idx = window.frontend_combo.findData("react")
        window.frontend_combo.setCurrentIndex(max(0, idx))
        window._sync_cfg()
        window._update_frontend_branch_state()
        assert "React 선택: Spring Boot REST API + React 프론트 + axios/fetch + router" in window.frontend_branch_lbl.text()
    finally:
        window.close()
        app.quit()
