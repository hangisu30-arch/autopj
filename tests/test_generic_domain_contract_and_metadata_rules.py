from pathlib import Path

from app.engine.analysis.analysis_result import DomainAnalysis, FieldInfo
from app.engine.analysis.ir_builder import IRBuilder
from app.ui.generated_content_validator import validate_generated_content
from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import auto_repair_generated_project


REQ = """
회원별 일정관리를 생성한다.
사용자와 관리자 모드를 분리한다.
사용자는 본인이 입력한 내용만 확인 가능하고 관리자는 전체 사용자 내용을 확인해야 한다.
기존 로그인 테이블을 재활용한다.
"""


def test_ir_emits_canonical_domain_meta_and_ui_contract():
    domain = DomainAnalysis(
        name="member_schedule",
        entity_name="MemberSchedule",
        feature_kind="schedule",
        feature_types=["schedule", "crud"],
        auth_required=True,
        source_table="member_schedule",
        primary_key="scheduleId",
        primary_key_column="schedule_id",
        fields=[
            FieldInfo(name="scheduleId", column="schedule_id", java_type="String", pk=True, display=True),
            FieldInfo(name="statusCd", column="status_cd", java_type="String", display=True),
            FieldInfo(name="priorityCd", column="priority_cd", java_type="String", display=True),
            FieldInfo(name="locationText", column="location_text", java_type="String", display=True),
            FieldInfo(name="schemaName", column="schema_name", java_type="String", display=True),
            FieldInfo(name="loginPassword", column="login_password", java_type="String", display=False),
        ],
    )
    domain = IRBuilder().apply(domain, frontend_mode="jsp", requirements_text=REQ)
    meta = domain.ir["domainMeta"]
    ui = domain.contracts["uiPolicy"]

    assert meta["canonicalSnake"] == "member_schedule"
    assert meta["canonicalCamel"] == "memberSchedule"
    assert meta["viewDir"] == "memberSchedule"
    assert "statusCd" in ui["allowedUiFields"]
    assert "priorityCd" in ui["allowedUiFields"]
    assert "locationText" in ui["allowedUiFields"]
    assert "schemaName" in ui["forbiddenUiFields"]
    assert "loginPassword" in ui["forbiddenUiFields"]
    assert ui["calendarContract"]["mainView"] == "memberSchedule/memberScheduleCalendar"


def test_generation_metadata_ui_validator_blocks_jsp_react_vue():
    for path, body, frontend in [
        ("src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleDetail.jsp", '<span>${memberScheduleVO.schemaName}</span>', "jsp"),
        ("frontend/react/src/pages/memberSchedule/MemberScheduleDetailPage.jsx", 'export default function Page(){ return <div>{detail.schemaName}</div> }', "react"),
        ("frontend/vue/src/views/memberSchedule/MemberScheduleDetail.vue", '<template><div>{{ detail.schemaName }}</div></template>', "vue"),
    ]:
        ok, reason = validate_generated_content(path, body, frontend_key=frontend)
        assert not ok and 'generation metadata' in reason


def test_calendar_controller_support_uses_canonical_domain_matching(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/memberSchedule/web/MemberScheduleController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.memberSchedule.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.ui.Model;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller @RequestMapping("/memberSchedule") public class MemberScheduleController {\n'
        '  @GetMapping("/calendar.do") public String calendar(Model model) { return "memberSchedule/memberScheduleCalendar"; }\n'
        '}\n',
        encoding='utf-8',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/member_schedule/member_scheduleCalendar.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<html><body>legacy alias</body></html>', encoding='utf-8')

    report = validate_generated_project(tmp_path, type('Cfg', (), {'frontend_key': 'jsp'})(), include_runtime=False)
    msgs = [item['message'] for item in report.get('static_issues') or []]
    assert not any('calendar view exists but controller missing for member_schedule' in msg for msg in msgs)


def test_jsp_property_repair_removes_generation_metadata_refs(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleForm.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<input name="schemaName" value="${memberScheduleVO.schemaName}"/>\n'
        '<input name="statusCd" value="${memberScheduleVO.statusCd}"/>\n',
        encoding='utf-8',
    )
    vo = tmp_path / 'src/main/java/egovframework/test/memberSchedule/service/MemberScheduleVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        'package egovframework.test.memberSchedule.service; public class MemberScheduleVO { private String statusCd; public String getStatusCd(){return statusCd;} public void setStatusCd(String v){this.statusCd=v;} }',
        encoding='utf-8',
    )
    issue = {
        'type': 'jsp_vo_property_mismatch',
        'repairable': True,
        'path': str(jsp.relative_to(tmp_path)).replace('\\', '/'),
        'details': {
            'available_props': ['statusCd'],
            'mapper_props': ['statusCd'],
            'missing_props': ['schemaName'],
            'missing_props_by_var': {'memberScheduleVO': ['schemaName']},
            'suggested_replacements': {},
        },
    }
    repair = auto_repair_generated_project(tmp_path, {'static_issues': [issue]})
    assert repair['changed_count'] == 1
    body = jsp.read_text(encoding='utf-8')
    assert 'schemaName' not in body
    assert 'statusCd' in body
