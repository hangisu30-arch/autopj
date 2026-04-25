from pathlib import Path

from app.ui.state import ProjectConfig
from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair
from app.validation.post_generation_repair import validate_and_repair_generated_files


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_mapper_namespace_repair_keeps_valid_xml_namespace(tmp_path: Path):
    mapper_java = tmp_path / "src/main/java/egovframework/testt/schedule/service/mapper/ScheduleMapper.java"
    mapper_xml = tmp_path / "src/main/resources/egovframework/mapper/views/ScheduleMapper.xml"
    _write(mapper_java, "package egovframework.testt.schedule.service.mapper; public interface ScheduleMapper {}")
    _write(mapper_xml, '<mapper namespace="egovframework.testt.schedule.service.mapper.ScheduleMapper\x03scheduleMap"></mapper>')

    report = {
        "issues": [
            {
                "code": "mapper_namespace_mismatch",
                "path": "src/main/resources/egovframework/mapper/views/ScheduleMapper.xml",
                "repairable": True,
                "details": {},
            }
        ]
    }
    result = apply_generated_project_auto_repair(tmp_path, report)
    assert result["changed_count"] == 1
    repaired = mapper_xml.read_text(encoding="utf-8")
    assert '\x03' not in repaired
    mapper_java_after = next(tmp_path.rglob('ScheduleMapper.java'))
    mapper_java_body = mapper_java_after.read_text(encoding="utf-8")
    expected_pkg = mapper_java_body.split("package ", 1)[1].split(";", 1)[0].strip()
    assert f'namespace="{expected_pkg}.ScheduleMapper"' in repaired


def test_validator_ignores_generic_views_calendar_directory(tmp_path: Path):
    _write(tmp_path / "pom.xml", "<project/>")
    _write(
        tmp_path / "src/main/webapp/WEB-INF/views/views/viewsCalendar.jsp",
        "<%@ page contentType=\"text/html; charset=UTF-8\" %><div>generic</div>",
    )

    cfg = ProjectConfig(project_name="demo", frontend_key="jsp", backend_key="egov_spring", database_key="mysql")
    report = validate_generated_project(tmp_path, cfg=cfg, manifest={}, run_runtime=False)
    msgs = [item["message"] for item in report["issues"]]
    assert not any("calendar view exists but controller missing for views" in msg for msg in msgs)


def test_post_generation_repair_materializes_legacy_layout_aliases(tmp_path: Path):
    _write(tmp_path / "src/main/webapp/WEB-INF/views/common/layout.jsp", '\n'.join([
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>',
        '<%@ include file="/WEB-INF/views/common/_header.jsp" %>',
        '<%@ include file="/WEB-INF/views/common/_menu.jsp" %>',
        '<div>layout</div>',
    ]))

    cfg = ProjectConfig(project_name="demo", frontend_key="jsp", backend_key="egov_spring", database_key="mysql")
    report = {"files": [], "invalid": []}
    repaired = validate_and_repair_generated_files(tmp_path, cfg, report, [], regenerate_callback=None, use_execution_core=False)
    assert repaired["remaining_invalid_files"] == []
    assert (tmp_path / "src/main/webapp/WEB-INF/views/common/_header.jsp").exists()
    assert (tmp_path / "src/main/webapp/WEB-INF/views/common/_menu.jsp").exists()
