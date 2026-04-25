from __future__ import annotations

import json
import tempfile
from pathlib import Path

from app.ui.analysis_bridge import build_analysis_from_config, save_analysis_result
from app.ui.prompt_templates import build_gemini_json_fileops_prompt
from app.ui.state import ProjectConfig


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        cfg = ProjectConfig(
            project_name="autotest01",
            frontend_key="react",
            frontend_label="react",
            backend_key="egov_spring",
            backend_label="전자정부프레임워크 (Spring Boot)",
            database_key="mysql",
            database_label="MySQL",
            output_dir=td,
            extra_requirements="""
회원 관리 목록/상세/등록/수정/삭제 화면과 REST API 생성

CREATE TABLE member (
    member_id VARCHAR(50) NOT NULL,
    member_name VARCHAR(100) NOT NULL,
    email VARCHAR(100),
    PRIMARY KEY (member_id)
);
""",
        )

        result = build_analysis_from_config(cfg)
        data = result.to_dict()
        assert data["project"]["base_package"] == "egovframework.autotest01"
        assert data["domains"], "domains must not be empty"
        assert data["domains"][0]["feature_kind"] == "crud"
        assert "page_list" in data["domains"][0]["file_generation_plan"]["frontend"]

        prompt = build_gemini_json_fileops_prompt(cfg, analysis_result=data)
        assert "[COMMON ANALYSIS RESULT - SOURCE OF TRUTH]" in prompt
        assert "feature_kind=crud" in prompt

        saved = save_analysis_result(data, td)
        assert saved and Path(saved).exists()

        output_path = Path(td) / "analysis_integration_output.json"
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(str(output_path))


if __name__ == "__main__":
    main()
