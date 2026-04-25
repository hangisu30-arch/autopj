from types import SimpleNamespace

from app.io.execution_core_apply import (
    _augment_schema_map_with_auth,
    _autopj_input_type,
    _autopj_select_options,
    _build_header_jsp,
    _build_leftnav_jsp,
)
from app.validation.generated_project_validator import validate_generated_project
from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH, FEATURE_KIND_CRUD


def test_auth_management_request_enriches_shared_member_schema_and_login_table():
    member_schema = schema_for(
        'Member',
        inferred_fields=[('memberId', 'member_id', 'String'), ('name', 'name', 'String')],
        table='tb_member',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )
    cfg = SimpleNamespace(
        login_feature_enabled=True,
        auth_unified_auth=False,
        auth_cert_login=False,
        auth_jwt_login=False,
        extra_requirements='회원가입 + 일반 로그인 + 관리자 승인 + 관리자 메뉴가 포함된 회원관리 시스템. 승인 후 로그인.',
    )
    out = _augment_schema_map_with_auth({'Member': member_schema}, [], cfg)
    assert 'Member' in out and 'Login' in out
    member = out['Member']
    cols = {col for _prop, col, _jt in member.fields}
    assert {'login_id', 'password', 'approval_status', 'role_cd', 'use_yn', 'reg_dt'}.issubset(cols)
    assert getattr(member, 'approval_required', False) is True
    assert getattr(member, 'admin_required', False) is True
    assert out['Login'].table == 'tb_member'


def test_auth_mapper_and_controller_apply_approval_gate_when_fields_exist():
    schema = schema_for(
        'Login',
        inferred_fields=[
            ('memberId', 'member_id', 'String'),
            ('loginId', 'login_id', 'String'),
            ('password', 'password', 'String'),
            ('approvalStatus', 'approval_status', 'String'),
            ('useYn', 'use_yn', 'String'),
            ('roleCd', 'role_cd', 'String'),
        ],
        table='tb_member',
        feature_kind=FEATURE_KIND_AUTH,
        strict_fields=True,
    )
    mapper_xml = builtin_file('mapper/LoginMapper.xml', 'egovframework.test', schema)
    controller = builtin_file('java/controller/LoginController.java', 'egovframework.test', schema)
    assert "AND approval_status = 'APPROVED'" in mapper_xml
    assert "AND use_yn = 'Y'" in mapper_xml
    assert '관리자 승인 후 로그인할 수 있습니다.' in controller
    assert 'session.setAttribute("roleCd"' in controller


def test_admin_nav_links_are_guarded_and_exposed_when_schema_requires_admin():
    schema = schema_for(
        'Member',
        inferred_fields=[
            ('memberId', 'member_id', 'String'),
            ('loginId', 'login_id', 'String'),
            ('password', 'password', 'String'),
            ('approvalStatus', 'approval_status', 'String'),
            ('useYn', 'use_yn', 'String'),
            ('roleCd', 'role_cd', 'String'),
        ],
        table='tb_member',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )
    schema.routes.update({'approval': '/member/approval/list.do', 'admin': '/member/admin/list.do'})
    schema.views.update({'approval': 'member/memberApprovalList', 'admin': 'member/memberAdminList'})
    schema.approval_required = True
    schema.admin_required = True
    header = _build_header_jsp({'Member': schema}, preferred_entity='Member', project_title='test')
    leftnav = _build_leftnav_jsp({'Member': schema}, preferred_entity='Member')
    merged = header + leftnav
    assert '/member/approval/list.do' in merged
    assert '/member/admin/list.do' in merged
    assert 'sessionScope.isAdmin' in merged


def test_audit_temporal_fields_are_date_and_approval_is_select():
    assert _autopj_input_type('regDt', 'String') == 'date'
    assert _autopj_input_type('modDt', 'String') == 'date'
    assert _autopj_select_options('approvalStatus', 'approval_status', 'String') == [
        ('PENDING', '대기'),
        ('APPROVED', '승인'),
        ('REJECTED', '반려'),
    ]


def test_validator_requires_select_for_auth_choice_controls(tmp_path):
    project_root = tmp_path / 'project'
    view = project_root / 'src/main/webapp/WEB-INF/views/member/memberForm.jsp'
    view.parent.mkdir(parents=True, exist_ok=True)
    view.write_text(
        '<form><input type="text" name="approvalStatus"/><input type="text" name="useYn"/><input type="date" name="regDt"/></form>',
        encoding='utf-8',
    )
    cfg = SimpleNamespace(
        frontend_key='jsp',
        database_key='mysql',
        database_type='mysql',
        extra_requirements='회원관리',
        effective_extra_requirements=lambda: '회원관리',
        auth_unified_auth=False,
        auth_cert_login=False,
        auth_jwt_login=False,
    )
    report = validate_generated_project(project_root, cfg, include_runtime=False)
    issue_types = [issue.get('type') for issue in report.get('static_issues') or []]
    assert 'auth_choice_control_mismatch' in issue_types
