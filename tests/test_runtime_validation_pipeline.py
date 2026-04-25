from pathlib import Path

from app.ui.state import ProjectConfig
from app.validation.post_generation_repair import validate_and_repair_generated_files
from app.validation.runtime_smoke import parse_backend_log_errors, should_run_runtime_validation


def test_parse_backend_log_errors_detects_compile_and_startup_failures():
    log = """
    [ERROR] /src/main/java/demo/Sample.java:[12,8] cannot find symbol
    org.springframework.beans.factory.UnsatisfiedDependencyException: Error creating bean
    org.apache.jasper.JasperException: /WEB-INF/views/demo/demoList.jsp not found
    """
    errors = parse_backend_log_errors(log)
    codes = {item["code"] for item in errors}
    assert "cannot_find_symbol" in codes
    assert "unsatisfied_dependency" in codes
    assert "jasper_exception" in codes


def test_should_run_runtime_validation_requires_build_files(tmp_path: Path):
    assert should_run_runtime_validation(tmp_path, backend_key="egov_spring") is False
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")
    assert should_run_runtime_validation(tmp_path, backend_key="egov_spring") is True


def test_post_generation_repair_fails_when_runtime_compile_fails(tmp_path: Path, monkeypatch):
    rel = "src/main/java/egovframework/demo/sample/service/ThingService.java"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("package egovframework.demo.sample.service;\n\npublic interface ThingService {}\n", encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")

    report = {"created": [rel], "overwritten": [], "errors": [], "patched": {}}
    file_ops = [{"path": rel, "purpose": "service", "content": "spec text"}]
    cfg = ProjectConfig(project_name="demo", frontend_key="jsp", database_key="sqlite", backend_key="egov_spring")

    def fake_runtime(project_root: Path, backend_key: str = "", compile_timeout_seconds: int = 300, startup_timeout_seconds: int = 120):
        return {
            "ok": False,
            "status": "failed",
            "compile": {
                "status": "failed",
                "command": "mvn -q -DskipTests compile",
                "errors": [{"code": "cannot_find_symbol", "message": "Java compile error: missing symbol", "snippet": "cannot find symbol"}],
            },
            "startup": {"status": "skipped"},
            "endpoint_smoke": {"status": "skipped"},
        }

    monkeypatch.setattr("app.validation.post_generation_repair.run_spring_boot_runtime_validation", fake_runtime)

    result = validate_and_repair_generated_files(
        project_root=tmp_path,
        cfg=cfg,
        report=report,
        file_ops=file_ops,
        regenerate_callback=None,
        use_execution_core=False,
        max_regen_attempts=0,
    )

    assert result["ok"] is False
    assert result["remaining_invalid_count"] >= 1
    assert any(item["reason"] == "backend compile validation failed" for item in result["remaining_invalid_files"])
    runtime_report_path = tmp_path / ".autopj_debug" / "runtime_smoke.json"
    assert runtime_report_path.exists()
    assert "cannot_find_symbol" in runtime_report_path.read_text(encoding="utf-8")
