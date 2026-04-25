from __future__ import annotations

import json
from pathlib import Path

from app.ui.analysis_bridge import build_analysis_from_config
from app.ui.backend_bridge import build_backend_plan
from app.ui.jsp_bridge import build_jsp_plan
from app.ui.prompt_templates import build_gemini_json_fileops_prompt
from app.ui.state import ProjectConfig


def main() -> None:
    cfg = ProjectConfig(
        project_name="autotest01",
        frontend_key="jsp",
        frontend_label="jsp",
        backend_key="egov_spring",
        backend_label="전자정부프레임워크 (Spring Boot)",
        database_key="mysql",
        database_label="MySQL",
        output_dir="./out_autotest01",
        extra_requirements="""
        회원 관리: 목록/상세/등록/수정/삭제 화면과 MVC Controller 생성
        CREATE TABLE member (
            member_id VARCHAR(50) NOT NULL,
            member_name VARCHAR(100) NOT NULL,
            email VARCHAR(100),
            PRIMARY KEY (member_id)
        );
        """,
    ).normalize()

    analysis_result = build_analysis_from_config(cfg).to_dict()
    backend_plan = build_backend_plan(analysis_result)
    jsp_plan = build_jsp_plan(analysis_result, backend_plan)
    prompt = build_gemini_json_fileops_prompt(
        cfg,
        analysis_result=analysis_result,
        backend_plan=backend_plan,
        jsp_plan=jsp_plan,
    )

    assert "[JSP GENERATION PLAN - SOURCE OF TRUTH]" in prompt
    assert "src/main/webapp/WEB-INF/views/member/memberList.jsp" in prompt
    assert 'return "member/memberList"' in prompt

    out = {
        "analysis_result": analysis_result,
        "backend_plan": backend_plan,
        "jsp_plan": jsp_plan,
        "prompt_contains_jsp_plan": True,
    }
    out_path = Path("tests/smoke_test_jsp_integration_output.json")
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK: smoke_test_jsp_integration")


if __name__ == "__main__":
    main()
