import json
from pathlib import Path

from app.ui.state import ProjectConfig
from app.validation.post_generation_repair import validate_and_repair_generated_files


def test_post_generation_repair_includes_manifest_and_runtime_validation(monkeypatch, tmp_path: Path):
    rel = "src/main/java/egovframework/demo/sample/service/ThingService.java"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "package egovframework.demo.sample.service;\npublic interface ThingService {}\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "app.validation.post_generation_repair.validate_generated_project",
        lambda project_root, cfg, manifest=None, include_runtime=True: {
            "ok": True,
            "static_issue_count": 0,
            "static_issues": [],
            "runtime": {"ok": True, "compile": {"status": "skipped"}, "startup": {"status": "skipped"}, "endpoint_smoke": {"status": "skipped"}},
        },
    )
    monkeypatch.setattr(
        "app.validation.post_generation_repair.auto_repair_generated_project",
        lambda project_root, validation_report: {"changed": [], "skipped": [], "changed_count": 0},
    )

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

    assert "generation_manifest" in result
    assert "generated_project_validation" in result
    debug_path = tmp_path / ".autopj_debug/post_generation_validation.json"
    assert debug_path.exists()
    saved = json.loads(debug_path.read_text(encoding="utf-8"))
    assert "generation_manifest" in saved
    assert "generated_project_validation" in saved
