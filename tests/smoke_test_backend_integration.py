from __future__ import annotations

import tempfile
from pathlib import Path

from app.ui.analysis_bridge import build_analysis_from_config
from app.ui.backend_bridge import build_backend_plan, save_backend_plan
from app.ui.prompt_templates import build_gemini_json_fileops_prompt
from app.ui.state import ProjectConfig


def test_backend_integration_smoke() -> None:
    cfg = ProjectConfig(
        project_name="autotest01",
        backend_key="egov_spring",
        backend_label="전자정부프레임워크 (Spring Boot)",
        frontend_key="jsp",
        frontend_label="jsp",
        database_key="mysql",
        database_label="MySQL",
        output_dir=".",
        extra_requirements=(
            "로그인 화면, 로그인 처리, 로그아웃\n\n"
            "user_id:varchar\n"
            "password:varchar"
        ),
    )

    analysis_result = build_analysis_from_config(cfg).to_dict()
    backend_plan = build_backend_plan(analysis_result)
    assert backend_plan["domains"][0]["controller_mode"] == "mvc_controller"
    prompt = build_gemini_json_fileops_prompt(cfg, analysis_result=analysis_result, backend_plan=backend_plan)
    assert "[COMMON BACKEND GENERATION PLAN - SOURCE OF TRUTH]" in prompt
    assert "controller_mode=mvc_controller" in prompt

    with tempfile.TemporaryDirectory() as td:
        saved = save_backend_plan(backend_plan, td)
        assert saved is not None
        assert Path(saved).exists()


if __name__ == "__main__":
    test_backend_integration_smoke()
    print("[OK] smoke_test_backend_integration")
