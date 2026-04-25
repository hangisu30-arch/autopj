from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from app.engine.analysis import AnalysisContext, AnalysisEngine
from app.ui.analysis_bridge import save_analysis_result
from app.ui.backend_bridge import build_backend_plan, save_backend_plan
from app.ui.react_bridge import build_react_plan, save_react_plan
from app.ui.validation_bridge import (
    build_validation_report,
    save_validation_report,
    build_auto_repair_plan,
    save_auto_repair_plan,
)
from app.ui.debug_artifacts import load_debug_bundle, render_debug_summary_text


def _prepare_debug_dir(root: Path) -> None:
    ctx = AnalysisContext.from_inputs(
        project_root=str(root),
        project_name='autotest01',
        frontend_mode='react',
        database_type='mysql',
        requirements_text='회원 관리 목록/상세/등록/수정/삭제 화면과 REST API 생성',
        schema_text='''
        CREATE TABLE member (
            member_id VARCHAR(50) NOT NULL,
            member_name VARCHAR(100) NOT NULL,
            email VARCHAR(100),
            PRIMARY KEY (member_id)
        );
        ''',
    )
    analysis = AnalysisEngine().run(ctx).to_dict()
    backend = build_backend_plan(analysis)
    react = build_react_plan(analysis, backend)
    report = build_validation_report(analysis, backend_plan=backend, react_plan=react, frontend_key='react')
    repair = build_auto_repair_plan(report)
    save_analysis_result(analysis, str(root))
    save_backend_plan(backend, str(root))
    save_react_plan(react, str(root))
    save_validation_report(report, str(root))
    save_auto_repair_plan(repair, str(root))
    (root / 'apply_report.json').write_text(json.dumps({'ok': True, 'written': ['a.java'], 'failed': []}, ensure_ascii=False), encoding='utf-8')


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _prepare_debug_dir(root)
        try:
            from PyQt6.QtWidgets import QApplication
            from app.ui.main_window import MainWindow
        except ModuleNotFoundError:
            source = Path('app/ui/main_window.py').read_text(encoding='utf-8')
            for tab_name in ['분석 결과', '생성 계획', '검증/복구', '적용 보고서']:
                assert tab_name in source, tab_name
            bundle = load_debug_bundle(str(root))
            summary = render_debug_summary_text(bundle)
            assert 'frontend_mode: react' in summary
            Path('tests/smoke_test_ui_reinforcement_window_output.json').write_text(
                json.dumps({'mode': 'source_fallback', 'summary_head': summary.splitlines()[:8]}, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            return

        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        window.folder_picker.set_value(str(root))
        window._sync_cfg()
        window._refresh_debug_views()

        tab_names = [window.output_tabs.tabText(i) for i in range(window.output_tabs.count())]
        assert tab_names == ['Gemini 출력', '실행 로그', '분석 결과', '생성 계획', '검증/복구', '적용 보고서'], tab_names
        assert 'frontend_mode: react' in window.debug_summary_view.toPlainText()
        assert 'member: feature_kind=crud' in window.analysis_view.toPlainText()
        assert '[REACT PLAN]' in window.plan_view.toPlainText()
        assert '[VALIDATION REPORT]' in window.validation_view.toPlainText()
        assert '[APPLY REPORT]' in window.apply_report_view.toPlainText()

        Path('tests/smoke_test_ui_reinforcement_window_output.json').write_text(
            json.dumps({'mode': 'pyqt_runtime', 'tabs': tab_names, 'summary_head': window.debug_summary_view.toPlainText().splitlines()[:8]}, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )
        window.close()
        app.quit()


if __name__ == '__main__':
    main()
