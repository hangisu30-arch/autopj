from execution_core.builtin_crud import Schema, builtin_file


def _schema(fields):
    return Schema(
        entity="TbMember",
        entity_var="tbMember",
        table="tb_member",
        id_prop="memberId",
        id_column="member_id",
        fields=fields,
        routes={"list": "/tbMember/list.do", "login": "/login/login.do", "main": "/main.do"},
        views={"list": "tbMember/tbMemberList", "login": "login/login", "main": "main/index"},
        feature_kind="AUTH",
    )


def test_builtin_file_auth_controller_without_unified_auth_and_without_approval_field_crashes_no_more():
    schema = _schema([("memberId", "member_id", "String"), ("memberPw", "member_pw", "String")])
    logical = "java/controller/TbMemberController.java"
    built = builtin_file(logical, "egovframework.test", schema)
    assert "class TbMemberController" in built
    assert "private boolean _isApproved(TbMemberVO user)" in built
    assert "return true;" in built


def test_builtin_file_auth_controller_without_unified_auth_with_approval_field_uses_getter():
    schema = _schema([
        ("memberId", "member_id", "String"),
        ("memberPw", "member_pw", "String"),
        ("approvalStatus", "approval_status", "String"),
    ])
    logical = "java/controller/TbMemberController.java"
    built = builtin_file(logical, "egovframework.test", schema)
    assert "getApprovalStatus()" in built
    assert '"APPROVED".equals(approvalValue)' in built
