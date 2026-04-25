from pathlib import Path

from app.io.execution_core_apply import _patch_generated_jsp_assets
from app.ui.state import ProjectConfig
from execution_core.builtin_crud import schema_for


def test_patch_generated_jsp_assets_rewrites_detail_and_formats_temporal_display(tmp_path: Path):
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/schedule/scheduleDetail.jsp"
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text("<html><body><p>old detail</p></body></html>", encoding="utf-8")
    schema = schema_for(
        "Schedule",
        [
            ("scheduleId", "schedule_id", "Long"),
            ("title", "title", "String"),
            ("startDatetime", "start_datetime", "java.time.LocalDateTime"),
            ("endDatetime", "end_datetime", "java.time.LocalDateTime"),
            ("content", "content", "String"),
        ],
        table="schedule",
        feature_kind="SCHEDULE",
    )
    cfg = ProjectConfig(project_name="demo", frontend_key="jsp", frontend_label="jsp")
    rel = str(jsp.relative_to(tmp_path)).replace("\\", "/")
    _patch_generated_jsp_assets(tmp_path, [rel], "Schedule", {"Schedule": schema}, cfg)
    body = jsp.read_text(encoding="utf-8")
    assert "autopj-detail-page" in body
    assert "yyyy-mm-dd hh:mm:ss" in body
    assert 'data-autopj-display="datetime"' in body
