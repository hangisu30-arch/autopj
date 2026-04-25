from app.io.execution_core_apply import _normalize_out_path
from execution_core.builtin_crud import schema_for, builtin_file


def test_normalize_out_path_rewrites_tb_member_admin_controller_and_jsp_paths():
    java_rel = _normalize_out_path(
        "src/main/java/egovframework/test/tbMemberAdmin/web/TbMemberAdminController.java",
        base_package="egovframework.test",
        preferred_entity="TbMemberAdmin",
        extra_text="테이블명: TB_MEMBER_ADMIN",
    )
    jsp_rel = _normalize_out_path(
        "src/main/webapp/WEB-INF/views/tbMemberAdmin/tbMemberAdminList.jsp",
        base_package="egovframework.test",
        preferred_entity="TbMemberAdmin",
        extra_text="테이블명: TB_MEMBER_ADMIN",
    )
    assert java_rel.endswith("/memberAdmin/web/MemberAdminController.java")
    assert jsp_rel == "src/main/webapp/WEB-INF/views/memberAdmin/memberAdminList.jsp"


def test_builtin_file_uses_logical_member_auth_class_names_even_when_logical_path_is_tb_prefixed():
    schema = schema_for("TbMemberAuth", table="tb_member_auth")
    controller = builtin_file("java/controller/TbMemberAuthController.java", "egovframework.test", schema)
    assert controller is not None
    assert "class MemberAuthController" in controller
    assert 'return "memberAuth/memberAuthList";' in controller
