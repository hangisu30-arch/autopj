from __future__ import annotations

import json
from pathlib import Path

from app.ui.analysis_bridge import build_analysis_from_config
from app.ui.backend_bridge import build_backend_plan
from app.ui.react_bridge import build_react_plan
from app.ui.validation_bridge import build_validation_report, build_auto_repair_plan
from app.ui.state import ProjectConfig


REQ = """회원 관리 목록 상세 등록 수정 삭제 화면과 REST API 생성
CREATE TABLE member (
 member_id VARCHAR(50) NOT NULL,
 member_name VARCHAR(100) NOT NULL,
 email VARCHAR(100),
 PRIMARY KEY (member_id)
);
"""


def main() -> None:
    cfg = ProjectConfig(
        project_name='autotest01',
        backend_key='egov_spring',
        frontend_key='react',
        database_key='mysql',
        output_dir='.',
        extra_requirements=REQ,
    )
    analysis = build_analysis_from_config(cfg).to_dict()
    backend = build_backend_plan(analysis)
    react = build_react_plan(analysis, backend)
    report = build_validation_report(analysis, backend_plan=backend, react_plan=react, frontend_key='react')
    repair = build_auto_repair_plan(report)
    out = {
        'validation_ok': report.get('ok'),
        'repair_mode': repair.get('repair_mode'),
        'error_count': len(report.get('errors') or []),
    }
    Path('tests/smoke_test_validation_engine_output.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    assert report.get('ok') is True, report
    assert repair.get('repair_mode') in {'none', 'targeted'}


if __name__ == '__main__':
    main()
