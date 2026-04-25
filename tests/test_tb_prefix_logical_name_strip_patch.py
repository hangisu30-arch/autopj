from execution_core.builtin_crud import schema_for, _entity_name_from_sources
from app.io.execution_core_apply import _normalize_out_path, _preferred_crud_entity
from app.engine.analysis.naming_rules import build_domain_naming, choose_domain_name


def test_choose_domain_name_strips_tb_prefix_but_keeps_table_source_separate():
    assert choose_domain_name(["TB_MEMBER"]) == "member"
    assert choose_domain_name(["tb_user_auth"]) == "user_auth"


def test_build_domain_naming_uses_logical_entity_without_tb_prefix():
    naming = build_domain_naming("egovframework.test", "TB_MEMBER", "jsp")
    assert naming.entity_name == "Member"
    assert naming.jsp_list_view == "/WEB-INF/views/member/memberList.jsp"


def test_schema_for_strips_tb_prefix_from_java_entity_name_only():
    schema = schema_for("TbMember", table="tb_member")
    assert schema.entity == "Member"
    assert schema.table == "tb_member"


def test_entity_name_from_sources_prefers_logical_name_for_java_entity():
    text = """테이블명:
- TB_MEMBER
"""
    assert _entity_name_from_sources("", text) == "Member"


def test_normalize_out_path_rewrites_tb_prefixed_java_and_jsp_names_to_logical_entity():
    java_rel = _normalize_out_path(
        "java/controller/TbMemberController.java",
        base_package="egovframework.test",
        preferred_entity="TbMember",
        extra_text="테이블명: TB_MEMBER",
    )
    jsp_rel = _normalize_out_path(
        "jsp/tbMember/tbMemberList.jsp",
        base_package="egovframework.test",
        preferred_entity="TbMember",
        extra_text="테이블명: TB_MEMBER",
    )
    assert java_rel.endswith("/member/web/MemberController.java")
    assert jsp_rel == "src/main/webapp/WEB-INF/views/member/memberList.jsp"


def test_preferred_crud_entity_returns_logical_entity_without_tb_prefix():
    file_ops = [
        {"path": "java/service/vo/TbMemberVO.java"},
        {"path": "java/service/TbMemberService.java"},
        {"path": "jsp/tbMember/tbMemberList.jsp"},
    ]
    assert _preferred_crud_entity(file_ops) == "Member"
