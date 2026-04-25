from pathlib import Path

from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import auto_repair_generated_project


def test_jsp_mismatch_repair_enriches_vo_from_mapper_props(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleCalendar.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<span>${memberScheduleVO.statusCd}</span>\n<span>${memberScheduleVO.priorityCd}</span>\n', encoding='utf-8')
    vo = tmp_path / 'src/main/java/egovframework/test/memberSchedule/service/MemberScheduleVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text('package egovframework.test.memberSchedule.service; public class MemberScheduleVO { }', encoding='utf-8')
    issue = {
        'type': 'jsp_vo_property_mismatch',
        'repairable': True,
        'path': str(jsp.relative_to(tmp_path)).replace('\\', '/'),
        'details': {
            'vo_path': str(vo.relative_to(tmp_path)).replace('\\', '/'),
            'available_props': [],
            'mapper_props': ['statusCd', 'priorityCd'],
            'missing_props': ['statusCd', 'priorityCd'],
            'missing_props_by_var': {'memberScheduleVO': ['statusCd', 'priorityCd']},
            'suggested_replacements': {},
        },
    }
    repair = auto_repair_generated_project(tmp_path, {'static_issues': [issue]})
    assert repair['changed_count'] == 1
    vo_body = vo.read_text(encoding='utf-8')
    assert 'private String statusCd;' in vo_body
    assert 'private String priorityCd;' in vo_body


def test_validator_skips_legacy_jsp_alias_when_canonical_view_exists(tmp_path: Path):
    canonical = tmp_path / 'src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleCalendar.jsp'
    alias = tmp_path / 'src/main/webapp/WEB-INF/views/member_schedule/member_scheduleCalendar.jsp'
    vo = tmp_path / 'src/main/java/egovframework/test/memberSchedule/service/MemberScheduleVO.java'
    canonical.parent.mkdir(parents=True, exist_ok=True)
    alias.parent.mkdir(parents=True, exist_ok=True)
    vo.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text('<span>${memberScheduleVO.statusCd}</span>', encoding='utf-8')
    alias.write_text('<span>${memberScheduleVO.missingField}</span>', encoding='utf-8')
    vo.write_text('package egovframework.test.memberSchedule.service; public class MemberScheduleVO { private String statusCd; public String getStatusCd(){return statusCd;} public void setStatusCd(String v){this.statusCd=v;} }', encoding='utf-8')
    report = validate_generated_project(tmp_path, type('Cfg', (), {'frontend_key': 'jsp'})(), include_runtime=False)
    msgs = [item['message'] for item in report.get('static_issues') or []]
    assert not any('missingField' in msg for msg in msgs)
