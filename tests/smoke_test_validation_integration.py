from __future__ import annotations

import json
from pathlib import Path

from app.ui.analysis_bridge import build_analysis_from_config
from app.ui.backend_bridge import build_backend_plan
from app.ui.react_bridge import build_react_plan
from app.ui.validation_bridge import (
    build_validation_report,
    build_auto_repair_plan,
    validation_report_to_text,
    auto_repair_plan_to_text,
)
from app.ui.prompt_templates import build_gemini_json_fileops_prompt
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
        backend_label='전자정부프레임워크 (Spring Boot)',
        frontend_key='react',
        frontend_label='react',
        code_engine_key='ollama',
        code_engine_label='Ollama',
        design_style_key='simple',
        design_style_label='심플',
        database_key='mysql',
        database_label='MySQL',
        output_dir='.',
        extra_requirements=REQ,
    )
    analysis = build_analysis_from_config(cfg).to_dict()
    backend = build_backend_plan(analysis)
    react = build_react_plan(analysis, backend)
    validation_report = build_validation_report(analysis, backend_plan=backend, react_plan=react, frontend_key='react')
    repair_plan = build_auto_repair_plan(validation_report)
    prompt = build_gemini_json_fileops_prompt(
        cfg,
        analysis_result=analysis,
        backend_plan=backend,
        react_plan=react,
        validation_report=validation_report,
        repair_plan=repair_plan,
    )
    out = {
        'has_validation_block': '[GLOBAL VALIDATION REPORT - SOURCE OF TRUTH]' in prompt,
        'has_repair_block': '[AUTO REPAIR PLAN - SOURCE OF TRUTH]' in prompt,
        'validation_preview': validation_report_to_text(validation_report).splitlines()[:4],
        'repair_preview': auto_repair_plan_to_text(repair_plan).splitlines()[:4],
    }
    Path('tests/smoke_test_validation_integration_output.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    assert out['has_validation_block'] is True
    assert out['has_repair_block'] is True


if __name__ == '__main__':
    main()
