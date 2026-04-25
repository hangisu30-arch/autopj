from __future__ import annotations

import json
from pathlib import Path

from app.engine.analysis import AnalysisContext, AnalysisEngine
from app.ui.backend_bridge import build_backend_plan
from app.ui.react_bridge import build_react_plan


def main() -> None:
    ctx = AnalysisContext.from_inputs(
        project_root=r"C:/workspace/autotest01",
        frontend_mode="react",
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
    result = AnalysisEngine().run(ctx).to_dict()
    backend_plan = build_backend_plan(result)
    react_plan = build_react_plan(result, backend_plan)

    domains = react_plan.get("domains") or []
    assert domains, "domains must not be empty"
    first = domains[0]
    artifacts = {a.get("artifact_type") for a in first.get("artifacts") or []}
    assert {"page_list", "page_detail", "page_form", "api_service"}.issubset(artifacts)
    assert react_plan["route_registry_path"] == "frontend/react/src/routes/index.jsx"

    out = Path(__file__).resolve().parent / "smoke_test_react_engine_output.json"
    out.write_text(json.dumps(react_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
