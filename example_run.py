from __future__ import annotations

from app.engine.analysis import AnalysisContext, AnalysisEngine


ctx = AnalysisContext.from_inputs(
    project_root=r"C:\eGovFrameDev-4.3.1-64bit\workspace-egov\autotest01",
    frontend_mode="react",
    database_type="mysql",
    requirements_text="회원 관리: 목록/상세/등록/수정/삭제 화면과 REST API 생성",
    schema_text="""
    CREATE TABLE member (
        member_id VARCHAR(50) NOT NULL,
        member_name VARCHAR(100) NOT NULL,
        email VARCHAR(100),
        PRIMARY KEY (member_id)
    );
    """,
)

engine = AnalysisEngine()
result = engine.run(ctx)
print(result.to_dict())
engine.dump_json(result, "analysis_result.json")
print("analysis_result.json generated")
