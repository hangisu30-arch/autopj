from execution_core.builtin_crud import Schema, builtin_file
from app.io.execution_core_apply import _autopj_input_type, _autopj_select_options, _build_header_jsp, _build_leftnav_jsp


def _schema():
    return Schema(
        entity="TbMember",
        entity_var="tbMember",
        table="tb_member",
        id_prop="memberId",
        id_column="member_id",
        fields=[
            ("memberId", "member_id", "String"),
            ("approvalStatus", "approval_status", "String"),
            ("useYn", "use_yn", "String"),
            ("regDt", "reg_dt", "String"),
            ("modDt", "mod_dt", "String"),
        ],
        routes={"list": "/tbMember/list.do"},
        views={"list": "tbMember/tbMemberList"},
        approval_required=True,
        admin_required=True,
    )


def test_audit_dt_inputs_are_date_only():
    assert _autopj_input_type("regDt", "String") == "date"
    assert _autopj_input_type("modDt", "String") == "date"


def test_approval_status_uses_select_options():
    assert _autopj_select_options("approvalStatus", "approval_status", "String") == [("PENDING", "대기"), ("APPROVED", "승인"), ("REJECTED", "반려")]


def test_header_and_leftnav_include_admin_and_approval_routes():
    schema = _schema()
    header = _build_header_jsp({"TbMember": schema}, preferred_entity="TbMember", project_title="test")
    leftnav = _build_leftnav_jsp({"TbMember": schema}, preferred_entity="TbMember")
    assert "/tbMember/approval/list.do" in header or "/tbMember/approval/list.do" in leftnav
    assert "/tbMember/admin/list.do" in header or "/tbMember/admin/list.do" in leftnav


def test_builtin_jsp_form_renders_date_and_approval_select():
    schema = _schema()
    body = builtin_file("jsp/TbMemberForm.jsp", "egovframework.test", schema)
    assert 'name="regDt"' in body and 'type="date"' in body
    assert 'name="modDt"' in body and 'type="date"' in body
    assert 'name="approvalStatus"' in body and '<select name="approvalStatus"' in body
