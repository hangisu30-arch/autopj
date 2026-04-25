from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.engine.analysis import AnalysisContext, AnalysisEngine
from app.ui.backend_bridge import build_backend_plan, save_backend_plan
from app.ui.react_bridge import build_react_plan, save_react_plan
from app.ui.validation_bridge import (
    build_validation_report,
    save_validation_report,
    build_auto_repair_plan,
    save_auto_repair_plan,
)
from app.ui.analysis_bridge import save_analysis_result
from app.ui.debug_artifacts import (
    load_debug_bundle,
    render_debug_summary_text,
    render_analysis_text,
    render_plan_text,
    render_validation_text,
    render_apply_report_text,
)


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
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
        (root / 'apply_report.json').write_text(json.dumps({
            'ok': True,
            'written': ['frontend/react/src/pages/member/MemberListPage.jsx'],
            'failed': [],
        }, ensure_ascii=False, indent=2), encoding='utf-8')

        bundle = load_debug_bundle(str(root))
        summary_text = render_debug_summary_text(bundle)
        analysis_text = render_analysis_text(bundle)
        plan_text = render_plan_text(bundle)
        validation_text = render_validation_text(bundle)
        apply_text = render_apply_report_text(bundle)

        assert 'project_name: autotest01' in summary_text
        assert 'frontend_plan: react_plan' in summary_text
        assert '[ANALYSIS RESULT]' in analysis_text
        assert 'member: feature_kind=crud' in analysis_text
        assert '[BACKEND PLAN]' in plan_text
        assert '[REACT PLAN]' in plan_text
        assert 'frontend/react/src/pages/member/MemberListPage.jsx' in plan_text
        assert '[VALIDATION REPORT]' in validation_text
        assert '[REPAIR PLAN]' in validation_text
        assert '[APPLY REPORT]' in apply_text

        out = {
            'summary': summary_text.splitlines()[:8],
            'analysis_head': analysis_text.splitlines()[:8],
            'plan_head': plan_text.splitlines()[:8],
        }
        Path('tests/smoke_test_ui_debug_artifacts_output.json').write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8'
        )


if __name__ == '__main__':
    main()
