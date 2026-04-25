from __future__ import annotations

import tempfile
from pathlib import Path

from app.ui.analysis_bridge import build_analysis_from_config
from app.ui.backend_bridge import build_backend_plan, backend_plan_to_text, save_backend_plan
from app.ui.state import ProjectConfig


def test_backend_engine_smoke() -> None:
    cfg = ProjectConfig(
        project_name="autotest01",
        backend_key="egov_spring",
        backend_label="전자정부프레임워크 (Spring Boot)",
        frontend_key="react",
        frontend_label="react",
        database_key="mysql",
        database_label="MySQL",
        output_dir=".",
        extra_requirements=(
            "회원 관리 목록/상세/등록/수정/삭제 화면과 API 생성\n\n"
            "CREATE TABLE member (\n"
            "  member_id VARCHAR(50) NOT NULL,\n"
            "  member_name VARCHAR(100) NOT NULL,\n"
            "  email VARCHAR(100),\n"
            "  PRIMARY KEY (member_id)\n"
            ");"
        ),
    )

    result = build_analysis_from_config(cfg).to_dict()
    plan = build_backend_plan(result)
    assert plan["base_package"].startswith("egovframework.")
    assert plan["domains"][0]["controller_mode"] == "rest_controller"
    artifact_types = {artifact["artifact_type"] for artifact in plan["domains"][0]["artifacts"]}
    assert {"vo", "mapper", "mapper_xml", "service", "service_impl", "controller"}.issubset(artifact_types)

    text = backend_plan_to_text(plan)
    assert "[COMMON BACKEND GENERATION PLAN - SOURCE OF TRUTH]" in text

    with tempfile.TemporaryDirectory() as td:
        saved = save_backend_plan(plan, td)
        assert saved is not None
        assert Path(saved).exists()


if __name__ == "__main__":
    test_backend_engine_smoke()
    print("[OK] smoke_test_backend_engine")
