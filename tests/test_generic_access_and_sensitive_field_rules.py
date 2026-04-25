from app.engine.analysis.analysis_result import DomainAnalysis, FieldInfo, ProjectAnalysis, AnalysisResult
from app.engine.analysis.ir_builder import IRBuilder
from app.adapters.jsp.jsp_task_builder import JspTaskBuilder
from app.adapters.react.react_task_builder import ReactTaskBuilder
from app.adapters.vue.vue_task_builder import VueTaskBuilder
from app.engine.backend.backend_task_builder import BackendTaskBuilder
from app.ui.generated_content_validator import validate_generated_content


REQ = """
회원별 일정관리를 생성한다.
사용자와 관리자 모드를 분리한다.
사용자는 본인이 입력한 내용만 확인 가능하고 관리자는 전체 사용자 내용을 확인해야 한다.
기존 로그인 테이블을 재활용한다.
"""


def _domain() -> DomainAnalysis:
    domain = DomainAnalysis(
        name="memberSchedule",
        entity_name="MemberSchedule",
        feature_kind="schedule",
        feature_types=["schedule", "crud"],
        auth_required=True,
        source_table="member_schedule",
        primary_key="scheduleId",
        primary_key_column="schedule_id",
        fields=[
            FieldInfo(name="scheduleId", column="schedule_id", java_type="String", pk=True, display=True),
            FieldInfo(name="memberNo", column="member_no", java_type="String", display=False),
            FieldInfo(name="roleCd", column="role_cd", java_type="String", display=False),
            FieldInfo(name="scheduleTitle", column="schedule_title", java_type="String", display=True),
            FieldInfo(name="loginPassword", column="login_password", java_type="String", display=False),
            FieldInfo(name="startDatetime", column="start_datetime", java_type="String", display=True),
            FieldInfo(name="endDatetime", column="end_datetime", java_type="String", display=True),
        ],
    )
    return IRBuilder().apply(domain, frontend_mode="jsp", requirements_text=REQ)


def test_ir_marks_sensitive_fields_and_access_mode():
    domain = _domain()
    data_model = domain.ir["dataModel"]
    contracts = domain.contracts

    field_map = {field["name"]: field for field in data_model["fields"]}
    assert field_map["loginPassword"]["authSensitive"] is True
    assert field_map["loginPassword"]["visibleInForm"] is False
    assert field_map["loginPassword"]["visibleInList"] is False
    assert "loginPassword" in data_model["authSensitiveFields"]

    access = contracts["access"]
    assert access["mode"] == "owner_admin_split"
    assert "memberNo" in access["ownerFieldCandidates"]
    assert "roleCd" in access["roleFieldCandidates"]


def test_frontend_and_backend_plans_carry_generic_access_metadata():
    base_domain = _domain().to_dict()

    jsp_analysis = AnalysisResult(
        project=ProjectAnalysis("/tmp/project", "demo", "egovframework.demo", "egov_spring", "jsp", "mysql"),
        requirements_text=REQ,
        schema_text="",
        domains=[_domain()],
    ).to_dict()
    react_analysis = AnalysisResult(
        project=ProjectAnalysis("/tmp/project", "demo", "egovframework.demo", "egov_spring", "react", "mysql"),
        requirements_text=REQ,
        schema_text="",
        domains=[_domain()],
    ).to_dict()
    vue_analysis = AnalysisResult(
        project=ProjectAnalysis("/tmp/project", "demo", "egovframework.demo", "egov_spring", "vue", "mysql"),
        requirements_text=REQ,
        schema_text="",
        domains=[_domain()],
    ).to_dict()

    jsp_plan = JspTaskBuilder().build(jsp_analysis).to_dict()
    react_plan = ReactTaskBuilder().build(react_analysis).to_dict()
    vue_plan = VueTaskBuilder().build(vue_analysis).to_dict()
    backend_plan = BackendTaskBuilder().build(jsp_analysis).to_dict()

    for plan in (jsp_plan, react_plan, vue_plan, backend_plan):
        domain = plan["domains"][0]
        assert domain["access_mode"] == "owner_admin_split"
        assert "memberNo" in domain["owner_field_candidates"]
        assert "roleCd" in domain["role_field_candidates"]
        assert "loginPassword" in domain["auth_sensitive_fields"]


def test_non_auth_ui_validator_blocks_password_leaks_for_jsp_react_vue():
    ok, reason = validate_generated_content(
        "src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleList.jsp",
        '<input type="text" name="password" value="${memberScheduleVO.password}"/>',
        frontend_key="jsp",
    )
    assert not ok and "auth-sensitive" in reason

    ok, reason = validate_generated_content(
        "frontend/react/src/pages/memberSchedule/MemberScheduleListPage.jsx",
        'export default function Page(){ return <input value={form.password} /> }',
        frontend_key="react",
    )
    assert not ok and "auth-sensitive" in reason

    ok, reason = validate_generated_content(
        "frontend/vue/src/views/memberSchedule/MemberScheduleList.vue",
        '<template><input v-model="form.password" /></template>',
        frontend_key="vue",
    )
    assert not ok and "auth-sensitive" in reason

    ok, reason = validate_generated_content(
        "frontend/react/src/pages/login/LoginPage.jsx",
        'export default function Login(){ return <input value={form.password} /> }',
        frontend_key="react",
    )
    assert ok, reason
