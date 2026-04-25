from __future__ import annotations

from pathlib import Path

from app.engine.analysis import AnalysisContext, AnalysisEngine
from app.ui.backend_bridge import build_backend_plan
from app.ui.prompt_templates import build_gemini_json_fileops_prompt
from app.ui.react_bridge import build_react_plan
from app.ui.state import ProjectConfig


def main() -> None:
    cfg = ProjectConfig(
        project_name="autotest01",
        frontend_key="react",
        frontend_label="react",
        backend_key="egov_spring",
        backend_label="전자정부프레임워크 (Spring Boot)",
        code_engine_key="ollama",
        code_engine_label="Ollama",
        design_style_key="simple",
        design_style_label="심플",
        database_key="mysql",
        database_label="MySQL",
        output_dir="",
        extra_requirements="회원 관리 목록/상세/등록/수정/삭제 화면 및 REST API",
    )
    ctx = AnalysisContext.from_inputs(
        project_root=r"C:/workspace/autotest01",
        frontend_mode="react",
        database_type="mysql",
        requirements_text=cfg.extra_requirements,
        schema_text="""
        CREATE TABLE member (
            member_id VARCHAR(50) NOT NULL,
            member_name VARCHAR(100) NOT NULL,
            email VARCHAR(100),
            PRIMARY KEY (member_id)
        );
        """,
        project_name=cfg.project_name,
    )
    analysis_result = AnalysisEngine().run(ctx).to_dict()
    backend_plan = build_backend_plan(analysis_result)
    react_plan = build_react_plan(analysis_result, backend_plan)
    prompt = build_gemini_json_fileops_prompt(
        cfg,
        analysis_result=analysis_result,
        backend_plan=backend_plan,
        react_plan=react_plan,
    )

    assert "[REACT GENERATION PLAN - SOURCE OF TRUTH]" in prompt
    assert "frontend/react/src/routes/index.jsx" in prompt
    assert "frontend/react/src/constants/routes.js" in prompt

    out = Path(__file__).resolve().parent / "smoke_test_react_integration_output.txt"
    out.write_text(prompt, encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
