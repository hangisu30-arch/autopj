
from pathlib import Path

from app.validation.generated_project_validator import _scan_search_fields_cover_all_columns
from app.validation.project_auto_repair import _repair_search_fields_incomplete
from app.validation.post_generation_repair import _runtime_degraded


def test_search_field_validator_excludes_generation_metadata(tmp_path: Path):
    (tmp_path / "src/main/java/demo").mkdir(parents=True)
    (tmp_path / "src/main/webapp/WEB-INF/views/memberSchedule").mkdir(parents=True)
    vo = tmp_path / "src/main/java/demo/MemberScheduleVO.java"
    vo.write_text(
        "package demo; public class MemberScheduleVO { private String memberNo; private String scheduleTitle; private String db; private String schemaName; }",
        encoding="utf-8",
    )
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleList.jsp"
    jsp.write_text('<form><input name="memberNo"/><input name="scheduleTitle"/></form>', encoding='utf-8')
    issues = _scan_search_fields_cover_all_columns(tmp_path)
    assert issues == []


def test_search_field_repair_does_not_add_generation_metadata(tmp_path: Path):
    jsp = tmp_path / "list.jsp"
    jsp.write_text('<form></form>', encoding='utf-8')
    issue = {
        'details': {'missing_fields': ['memberNo', 'db', 'schemaName', 'scheduleTitle']}
    }
    assert _repair_search_fields_incomplete(jsp, issue, tmp_path)
    body = jsp.read_text(encoding='utf-8')
    assert 'name="memberNo"' in body
    assert 'name="scheduleTitle"' in body
    assert 'name="db"' not in body
    assert 'name="schemaName"' not in body


def test_runtime_degraded_detects_smoke_breaking_compile():
    before = {'compile': {'status': 'ok'}, 'startup': {'status': 'ok'}, 'endpoint_smoke': {'status': 'failed'}}
    after = {'compile': {'status': 'failed'}, 'startup': {'status': 'skipped'}, 'endpoint_smoke': {'status': 'skipped'}}
    assert _runtime_degraded(before, after) is True
