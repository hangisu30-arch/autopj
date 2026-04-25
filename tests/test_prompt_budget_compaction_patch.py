from app.ui.prompt_budget import compact_requirements_text
from app.ui.prompt_templates import build_gemini_json_fileops_prompt
from app.ui.state import ProjectConfig


def test_compact_requirements_text_preserves_high_signal_schema_and_rules():
    ddl = """
CREATE TABLE tb_member (
  member_id VARCHAR(20) PRIMARY KEY,
  login_id VARCHAR(50),
  password VARCHAR(100),
  use_yn CHAR(1),
  created_at DATETIME
);
COMMENT ON COLUMN tb_member.member_id IS '회원 ID';
""".strip()
    strong_rules = "\n".join([
        "- 반드시 calendar 는 생성 금지",
        "- 절대 password 를 list UI 에 노출하지 말 것",
        "- form 은 useYn, createdAt 을 포함해야 한다",
    ])
    filler = "\n".join([f"설명 문장 {i} " + ("가" * 80) for i in range(400)])
    raw = f"{filler}\n\n{ddl}\n\n{strong_rules}\n\n{filler}"

    compacted, meta = compact_requirements_text(raw, max_chars=5000, soft_limit=6000)

    assert meta["compacted"] is True
    assert len(compacted) <= 5000
    assert "CREATE TABLE tb_member" in compacted
    assert "calendar 는 생성 금지" in compacted
    assert "password 를 list UI 에 노출하지 말 것" in compacted


def test_build_prompt_caps_large_user_requirements_and_overall_prompt():
    cfg = ProjectConfig(
        project_name="test",
        frontend_key="jsp",
        frontend_label="jsp",
        backend_key="egov_spring",
        backend_label="전자정부프레임워크 (Spring Boot)",
        database_key="mysql",
        database_label="MySQL",
        extra_requirements=("반드시 로그인/회원가입/회원관리 연계\n" + ("상세 요구사항 " + ("나" * 120) + "\n") * 500),
    )
    cfg.normalize()

    prompt = build_gemini_json_fileops_prompt(cfg)

    assert len(prompt) <= 32000 or "[USER EXTRA REQUIREMENTS COMPACTED" in prompt or "[REQUIREMENTS COMPACTED]" in prompt
    assert "[USER EXTRA REQUIREMENTS]" in prompt
    assert "로그인/회원가입/회원관리" in prompt
