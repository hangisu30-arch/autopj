from __future__ import annotations

import json
from pathlib import Path

from app.engine.analysis import AnalysisContext, AnalysisEngine
from app.ui.backend_bridge import build_backend_plan
from app.ui.jsp_bridge import build_jsp_plan


def main() -> None:
    ctx = AnalysisContext.from_inputs(
        project_root=r"C:\workspace\autotest01",
        project_name="autotest01",
        frontend_mode="jsp",
        database_type="mysql",
        requirements_text="회원 관리: 목록/상세/등록/수정/삭제 화면과 MVC Controller 생성",
        schema_text="""
        CREATE TABLE member (
            member_id VARCHAR(50) NOT NULL,
            member_name VARCHAR(100) NOT NULL,
            email VARCHAR(100),
            PRIMARY KEY (member_id)
        );
        """,
    )
    analysis_result = AnalysisEngine().run(ctx).to_dict()
    backend_plan = build_backend_plan(analysis_result)
    jsp_plan = build_jsp_plan(analysis_result, backend_plan)

    domain = jsp_plan["domains"][0]
    assert jsp_plan["frontend_mode"] == "jsp"
    assert domain["domain_name"] == "member"
    assert domain["controller_class_name"].endswith("Controller")
    artifact_types = {v["artifact_type"] for v in domain["views"]}
    assert artifact_types == {"list_jsp", "detail_jsp", "form_jsp"}
    view_names = {v["view_name"] for v in domain["views"]}
    assert "member/memberList" in view_names
    assert "member/memberDetail" in view_names
    assert "member/memberForm" in view_names

    out_path = Path("tests/smoke_test_jsp_engine_output.json")
    out_path.write_text(json.dumps(jsp_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OK: smoke_test_jsp_engine")


if __name__ == "__main__":
    main()
