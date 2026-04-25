from pathlib import Path

from app.validation.post_generation_repair import validate_and_repair_generated_files
from app.ui.state import ProjectConfig


def test_post_generation_repair_regenerates_invalid_file(tmp_path: Path):
    rel = "src/main/java/egovframework/demo/sample/service/ThingService.java"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("garbage", encoding="utf-8")

    report = {"created": [rel], "overwritten": [], "errors": [], "patched": {}}
    file_ops = [{"path": rel, "purpose": "service", "content": "spec text"}]
    cfg = ProjectConfig(project_name="demo", frontend_key="jsp", database_key="sqlite")

    def regen(path: str, purpose: str, spec: str, reason: str):
        assert path == rel
        assert purpose == "service"
        assert spec == "spec text"
        return {
            "path": rel,
            "purpose": purpose,
            "content": "package egovframework.demo.sample.service;\n\npublic interface ThingService {\n}\n",
        }

    result = validate_and_repair_generated_files(
        project_root=tmp_path,
        cfg=cfg,
        report=report,
        file_ops=file_ops,
        regenerate_callback=regen,
        use_execution_core=False,
        max_regen_attempts=1,
    )

    assert result["initial_invalid_count"] == 1
    assert result["remaining_invalid_count"] == 0
    assert result["repaired_files"]
    assert "package egovframework.demo.sample.service;" in target.read_text(encoding="utf-8")


def test_post_generation_repair_reports_invalid_without_callback(tmp_path: Path):
    rel = "src/main/java/egovframework/demo/sample/service/BadService.java"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("", encoding="utf-8")

    report = {"created": [rel], "overwritten": [], "errors": [], "patched": {}}
    file_ops = [{"path": rel, "purpose": "service", "content": "spec text"}]
    cfg = ProjectConfig(project_name="demo", frontend_key="jsp", database_key="sqlite")

    result = validate_and_repair_generated_files(
        project_root=tmp_path,
        cfg=cfg,
        report=report,
        file_ops=file_ops,
        regenerate_callback=None,
        use_execution_core=False,
        max_regen_attempts=0,
    )

    assert result["initial_invalid_count"] == 1
    assert result["remaining_invalid_count"] == 1
    assert result["skipped_files"][0]["action"] == "no_regen_callback"
