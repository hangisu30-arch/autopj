from pathlib import Path

from app.ui.generated_content_validator import validate_generated_content
from app.validation.generated_project_validator import _scan_search_fields_cover_all_columns
from app.validation.post_generation_repair import _runtime_degraded, _runtime_improved


def test_generation_metadata_not_required_in_search_fields(tmp_path: Path):
    root = tmp_path
    (root / "src/main/java/demo").mkdir(parents=True, exist_ok=True)
    (root / "src/main/webapp/WEB-INF/views/memberSchedule").mkdir(parents=True, exist_ok=True)
    (root / "src/main/java/demo/MemberScheduleVO.java").write_text(
        "public class MemberScheduleVO {\n private String memberNo;\n private String scheduleTitle;\n private String db;\n private String schemaName;\n public String getMemberNo(){return memberNo;}\n public String getScheduleTitle(){return scheduleTitle;}\n public String getDb(){return db;}\n public String getSchemaName(){return schemaName;}\n}\n",
        encoding="utf-8",
    )
    (root / "src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleList.jsp").write_text(
        '<form><input name="memberNo"/><input name="scheduleTitle"/></form>', encoding="utf-8"
    )
    issues = _scan_search_fields_cover_all_columns(root)
    assert not issues


def test_generation_metadata_validator_requires_binding_context_not_plain_text():
    ok, _ = validate_generated_content(
        'src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleList.jsp',
        '<html><body><p>dashboard view</p></body></html>',
        frontend_key='jsp',
    )
    assert ok


def test_runtime_improved_helper():
    before = {'compile': {'status': 'ok'}, 'startup': {'status': 'ok'}, 'endpoint_smoke': {'status': 'failed'}}
    after_same = {'compile': {'status': 'ok'}, 'startup': {'status': 'ok'}, 'endpoint_smoke': {'status': 'failed'}}
    after_worse = {'compile': {'status': 'failed'}, 'startup': {'status': 'skipped'}, 'endpoint_smoke': {'status': 'skipped'}}
    assert not _runtime_improved(before, after_same)
    assert _runtime_degraded(before, after_worse)
