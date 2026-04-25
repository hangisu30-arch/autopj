from __future__ import annotations

import json
from pathlib import Path

from app.engine.analysis import AnalysisContext, AnalysisEngine
from app.ui.backend_bridge import build_backend_plan
from app.ui.vue_bridge import build_vue_plan
from app.ui.validation_bridge import build_validation_report, build_auto_repair_plan


def main() -> None:
    ctx = AnalysisContext.from_inputs(
        project_root=r"C:/workspace/autotest01",
        frontend_mode="vue",
        database_type="mysql",
        requirements_text="회원 관리 목록 상세 등록 수정 삭제 화면과 REST API 생성",
        schema_text="""
        CREATE TABLE member (
            member_id VARCHAR(50) NOT NULL,
            member_name VARCHAR(100) NOT NULL,
            email VARCHAR(100),
            PRIMARY KEY (member_id)
        );
        """,
    )
    analysis = AnalysisEngine().run(ctx).to_dict()
    backend = build_backend_plan(analysis)
    vue = build_vue_plan(analysis, backend)
    report = build_validation_report(analysis, backend_plan=backend, vue_plan=vue, frontend_key='vue')
    repair = build_auto_repair_plan(report)
    out = {
        'validation_ok': report.get('ok'),
        'repair_mode': repair.get('repair_mode'),
        'error_count': len(report.get('errors') or []),
    }
    Path('tests/smoke_test_vue_validation_output.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    assert report.get('ok') is True, report
    assert repair.get('repair_mode') in {'none', 'targeted'}


if __name__ == '__main__':
    main()
