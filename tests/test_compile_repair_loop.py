from pathlib import Path

from app.ui.state import ProjectConfig
from app.validation.backend_compile_repair import collect_compile_repair_targets
from app.validation.compile_error_parser import parse_compile_errors
from app.validation.post_generation_repair import validate_and_repair_generated_files


def test_parse_compile_errors_detects_maven_wrapper_bootstrap_failure():
    log = """
    Invoke-WebRequest : 경로에 잘못된 문자가 있습니다.
    [mvnw.cmd] Maven 배포본 다운로드에 실패했습니다.
    """
    errors = parse_compile_errors(log)
    codes = {item["code"] for item in errors}
    assert "maven_wrapper_bootstrap" in codes or "maven_wrapper_download" in codes
    assert any((item.get("path") or "") == "mvnw.cmd" for item in errors)


def test_collect_compile_repair_targets_includes_wrapper_files_for_bootstrap_failure(tmp_path: Path):
    (tmp_path / "mvnw.cmd").write_text("broken", encoding="utf-8")
    (tmp_path / "mvnw").write_text("#!/bin/sh\n", encoding="utf-8")
    props = tmp_path / ".mvn/wrapper/maven-wrapper.properties"
    props.parent.mkdir(parents=True, exist_ok=True)
    props.write_text("distributionUrl=x\n", encoding="utf-8")
    runtime_report = {
        "compile": {
            "status": "failed",
            "errors": [{"code": "maven_wrapper_bootstrap", "path": "mvnw.cmd", "message": "bootstrap failed"}],
            "raw_output": "Invoke-WebRequest : 경로에 잘못된 문자가 있습니다.",
        }
    }
    targets = collect_compile_repair_targets(runtime_report, manifest={}, project_root=tmp_path)
    assert "mvnw.cmd" in targets
    assert ".mvn/wrapper/maven-wrapper.properties" in targets


def test_post_generation_repair_runs_second_compile_repair_loop_for_wrapper_failure(tmp_path: Path, monkeypatch):
    rel = "src/main/java/egovframework/demo/sample/service/ThingService.java"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("package egovframework.demo.sample.service;\npublic interface ThingService {}\n", encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project/>\n", encoding="utf-8")
    (tmp_path / "mvnw").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "mvnw.cmd").write_text("broken wrapper\n", encoding="utf-8")
    props = tmp_path / ".mvn/wrapper/maven-wrapper.properties"
    props.parent.mkdir(parents=True, exist_ok=True)
    props.write_text("distributionUrl=broken\n", encoding="utf-8")

    responses = [
        {
            "ok": False,
            "status": "failed",
            "compile": {
                "status": "failed",
                "command": "mvnw.cmd -q -DskipTests compile",
                "raw_output": "Invoke-WebRequest : 경로에 잘못된 문자가 있습니다.\n[mvnw.cmd] Maven 배포본 다운로드에 실패했습니다.",
                "errors": [{"code": "maven_wrapper_bootstrap", "path": "mvnw.cmd", "message": "Maven wrapper bootstrap failed"}],
            },
            "startup": {"status": "skipped"},
            "endpoint_smoke": {"status": "skipped"},
        },
        {
            "ok": True,
            "status": "ok",
            "compile": {"status": "ok", "command": "mvnw.cmd -q -DskipTests compile", "errors": []},
            "startup": {"status": "skipped"},
            "endpoint_smoke": {"status": "skipped"},
        },
    ]

    def fake_runtime(project_root: Path, backend_key: str = "", compile_timeout_seconds: int = 300, startup_timeout_seconds: int = 120):
        return responses.pop(0)

    monkeypatch.setattr("app.validation.post_generation_repair.run_spring_boot_runtime_validation", fake_runtime)
    monkeypatch.setattr(
        "app.validation.post_generation_repair.validate_generated_project",
        lambda project_root, cfg, manifest=None, include_runtime=False: {"ok": True, "static_issue_count": 0, "static_issues": []},
    )

    report = {"created": [rel], "overwritten": [], "errors": [], "patched": {}}
    file_ops = [{"path": rel, "purpose": "service", "content": "spec text"}]
    cfg = ProjectConfig(project_name="demo", frontend_key="jsp", database_key="sqlite", backend_key="egov_spring")

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
    assert result["runtime_validation"]["compile"]["status"] == "ok"
    assert len(result["compile_repair_rounds"]) == 1
    assert any(item["path"] == "mvnw.cmd" for item in result["compile_repair_rounds"][0]["changed"])
    wrapper_body = (tmp_path / "mvnw.cmd").read_text(encoding="utf-8")
    assert "$env:MVNW_DIST_URL" in wrapper_body
