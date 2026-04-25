from execution_core.builtin_crud import _extract_explicit_table_name, _entity_name_from_sources
from app.io.execution_core_apply import _normalize_out_path, _infer_module_segment


def test_extract_explicit_table_name_accepts_same_line_bullet():
    text = "테이블명: - `TB_MEMBER` 테이블 설명(comment): - 회원 정보 관리 테이블"
    assert _extract_explicit_table_name(text) == "tb_member"


def test_entity_name_from_sources_strips_tb_prefix_for_java_entity():
    text = """테이블명:
- TB_MEMBER
"""
    assert _entity_name_from_sources("", text) == "Member"


def test_boot_application_path_stays_at_root_base_package_even_with_tb_prompt_tokens():
    rel = _normalize_out_path(
        "java/EgovBootApplication.java",
        base_package="egovframework.test",
        preferred_entity="TB_MEMBER",
        content="",
        extra_text="테이블명: TB_MEMBER 컬럼명: login_id"
    )
    assert rel == "src/main/java/egovframework/test/EgovBootApplication.java"


def test_infer_module_segment_strips_tb_prefix_tokens_generically():
    seg = _infer_module_segment(
        "egovframework.test",
        rel_path="java/service/vo/ItemVO.java",
        content="",
        extra_text="테이블명: TB_MEMBER"
    )
    assert seg == "member"
