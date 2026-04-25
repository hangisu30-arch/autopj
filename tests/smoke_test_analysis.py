from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.engine.analysis import AnalysisContext, AnalysisEngine


def run_case(name: str, frontend: str, requirements: str, schema_text: str) -> dict:
    ctx = AnalysisContext.from_inputs(
        project_root=str(ROOT / "demo_project"),
        frontend_mode=frontend,
        database_type="mysql",
        requirements_text=requirements,
        schema_text=schema_text,
    )
    engine = AnalysisEngine()
    result = engine.run(ctx)
    return result.to_dict()


def main() -> None:
    member_schema = """
    CREATE TABLE member (
        member_id VARCHAR(50) NOT NULL,
        member_name VARCHAR(100) NOT NULL,
        email VARCHAR(100),
        PRIMARY KEY (member_id)
    );
    """

    login_schema = """
    CREATE TABLE user_account (
        user_id VARCHAR(50) NOT NULL,
        password VARCHAR(100) NOT NULL,
        PRIMARY KEY (user_id)
    );
    """

    board_schema = """
    CREATE TABLE board (
        board_id BIGINT NOT NULL,
        title VARCHAR(200) NOT NULL,
        content TEXT,
        reg_date DATETIME,
        PRIMARY KEY (board_id)
    );
    """

    results = {
        "member_crud": run_case(
            "member_crud",
            "react",
            "회원 관리 목록/상세/등록/수정/삭제 화면과 REST API 생성",
            member_schema,
        ),
        "login_auth": run_case(
            "login_auth",
            "jsp",
            "로그인 화면, 로그인 처리, 로그아웃 기능 생성",
            login_schema,
        ),
        "board_crud": run_case(
            "board_crud",
            "react",
            "게시판 목록/상세/등록 화면과 API 생성",
            board_schema,
        ),
    }

    out_path = ROOT / "tests" / "smoke_test_output.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    assert results["member_crud"]["domains"][0]["feature_kind"] == "crud"
    assert results["login_auth"]["domains"][0]["feature_kind"] == "auth"
    assert "generic_list" in results["login_auth"]["domains"][0]["forbidden_artifacts"]
    assert results["board_crud"]["domains"][0]["feature_kind"] == "crud"

    print(f"Smoke test passed: {out_path}")


if __name__ == "__main__":
    main()
