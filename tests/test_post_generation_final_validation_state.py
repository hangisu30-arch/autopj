from pathlib import Path

from app.ui.state import ProjectConfig
from app.validation.post_generation_repair import validate_and_repair_generated_files


def test_final_invalid_is_recomputed_after_repairs(tmp_path: Path, monkeypatch):
    rel = "src/main/java/egovframework/demo/sample/service/ThingService.java"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("package egovframework.demo.sample.service;\npublic interface ThingService {}\n", encoding="utf-8")

    report = {"created": [rel], "overwritten": [], "errors": [], "patched": {}}
    file_ops = [{"path": rel, "purpose": "service", "content": "spec text"}]
    cfg = ProjectConfig(project_name="demo", frontend_key="react", database_key="sqlite")

    calls = {"count": 0}

    def fake_validate_paths(project_root: Path, rel_paths, frontend_key: str):
        calls["count"] += 1
        if calls["count"] < 3:
            return [{"path": rel, "reason": "stale validation failure"}]
        return []

    monkeypatch.setattr("app.validation.post_generation_repair._validate_paths", fake_validate_paths)
    monkeypatch.setattr(
        "app.validation.post_generation_repair.validate_generated_project",
        lambda project_root, cfg, manifest=None, include_runtime=False: {"ok": True, "static_issue_count": 0, "static_issues": []},
    )
    monkeypatch.setattr(
        "app.validation.post_generation_repair.run_spring_boot_runtime_validation",
        lambda project_root, backend_key="", compile_timeout_seconds=300, startup_timeout_seconds=120: {
            "ok": True,
            "status": "ok",
            "compile": {"status": "ok", "errors": []},
            "startup": {"status": "ok", "errors": []},
            "endpoint_smoke": {"status": "ok", "results": []},
        },
    )

    result = validate_and_repair_generated_files(
        project_root=tmp_path,
        cfg=cfg,
        report=report,
        file_ops=file_ops,
        regenerate_callback=None,
        use_execution_core=False,
        max_regen_attempts=0,
    )

    assert result["ok"] is True
    assert result["remaining_invalid_count"] == 0
    assert result["remaining_invalid_files"] == []
    assert calls["count"] >= 3


def test_final_deep_repair_reruns_compile_repair_loop(tmp_path: Path, monkeypatch):
    rel = "src/main/java/egovframework/demo/sample/service/ThingService.java"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("package egovframework.demo.sample.service;\npublic interface ThingService {}\n", encoding="utf-8")

    report = {"created": [rel], "overwritten": [], "errors": [], "patched": {}}
    file_ops = [{"path": rel, "purpose": "service", "content": "spec text"}]
    cfg = ProjectConfig(project_name="demo", frontend_key="react", database_key="sqlite", backend_key="egov_spring")

    validate_states = iter([
        {"ok": True, "static_issue_count": 0, "static_issues": []},  # deep_validation_before
        {"ok": False, "static_issue_count": 1, "static_issues": [{"path": rel, "message": "compile regressed"}]},  # deep_validation_after
        {"ok": True, "static_issue_count": 0, "static_issues": []},  # after final deep repair
        {"ok": True, "static_issue_count": 0, "static_issues": []},  # final recompute
        {"ok": True, "static_issue_count": 0, "static_issues": []},  # final recompute extra guard
        {"ok": True, "static_issue_count": 0, "static_issues": []},  # compatibility extra guard
    ])

    monkeypatch.setattr(
        "app.validation.post_generation_repair.validate_generated_project",
        lambda project_root, cfg, manifest=None, include_runtime=False: next(validate_states),
    )

    runtime_states = iter([
        {
            "ok": False,
            "status": "failed",
            "compile": {"status": "failed", "errors": [{"path": rel, "message": "cannot find symbol"}]},
            "startup": {"status": "skipped"},
            "endpoint_smoke": {"status": "skipped"},
        }
    ])

    monkeypatch.setattr(
        "app.validation.post_generation_repair.run_spring_boot_runtime_validation",
        lambda project_root, backend_key="", compile_timeout_seconds=300, startup_timeout_seconds=120: next(runtime_states),
    )

    repair_calls = {"count": 0}

    def fake_compile_repair_loop(**kwargs):
        repair_calls["count"] += 1
        if repair_calls["count"] == 1:
            return {
                "ok": True,
                "status": "ok",
                "compile": {"status": "ok", "errors": []},
                "startup": {"status": "ok", "errors": []},
                "endpoint_smoke": {"status": "ok", "results": []},
            }, []
        return {
            "ok": True,
            "status": "ok",
            "compile": {"status": "ok", "errors": []},
            "startup": {"status": "ok", "errors": []},
            "endpoint_smoke": {"status": "ok", "results": []},
        }, [{
            "round": 1,
            "attempted": True,
            "targets": [rel],
            "changed": [{"path": rel, "reason": "compile repaired after final deep repair"}],
            "skipped": [],
            "before": {"compile_status": "failed"},
            "after": {"compile_status": "ok"},
        }]

    monkeypatch.setattr("app.validation.post_generation_repair._run_compile_repair_loop", fake_compile_repair_loop)
    monkeypatch.setattr(
        "app.validation.post_generation_repair.apply_generated_project_auto_repair",
        lambda project_root, validation_report: {"changed": [{"path": rel, "reason": "final deep repair"}], "skipped": [], "changed_count": 1},
    )

    result = validate_and_repair_generated_files(
        project_root=tmp_path,
        cfg=cfg,
        report=report,
        file_ops=file_ops,
        regenerate_callback=None,
        use_execution_core=False,
        max_regen_attempts=0,
    )

    assert repair_calls["count"] == 2
    assert result["ok"] is True
    assert result["runtime_validation"]["compile"]["status"] == "ok"
    assert len(result["compile_repair_rounds"]) == 1
    assert result["compile_repair_rounds"][0]["changed"][0]["path"] == rel
