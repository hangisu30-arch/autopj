from pathlib import Path

from app.io.file_writer import apply_file_ops
from app.ui.json_validator import validate_plan_json
from app.ui.state import ProjectConfig
from app.ui.template_generator import template_file_ops
from execution_core.project_patcher import ensure_maven_wrapper


def test_template_file_ops_include_maven_wrapper_for_egov_backend():
    cfg = ProjectConfig(project_name="demo", backend_key="egov_spring", frontend_key="jsp", database_key="mysql")
    ops = template_file_ops(cfg)
    paths = {item["path"] for item in ops}
    assert "pom.xml" in paths
    assert "mvnw" in paths
    assert "mvnw.cmd" in paths
    assert ".mvn/wrapper/maven-wrapper.properties" in paths
    assert "src/main/resources/application.properties" in paths


def test_validate_plan_json_rejects_wrapper_template_files():
    ok, err = validate_plan_json('[{"path":"mvnw","purpose":"wrapper","content":"spec"}]', frontend_key="jsp")
    assert ok is False
    assert "템플릿 파일" in err


def test_apply_file_ops_marks_mvnw_executable(tmp_path: Path):
    report = apply_file_ops([
        {"path": "mvnw", "content": "#!/bin/sh\necho ok\n"},
    ], tmp_path, overwrite=True)
    assert "mvnw" in report["created"]
    assert (tmp_path / "mvnw").stat().st_mode & 0o111


def test_ensure_maven_wrapper_creates_bootstrap_files(tmp_path: Path):
    created = ensure_maven_wrapper(tmp_path)
    paths = {p.relative_to(tmp_path).as_posix() for p in created}
    assert paths == {"mvnw", "mvnw.cmd", ".mvn/wrapper/maven-wrapper.properties"}
    assert "apache-maven" in (tmp_path / "mvnw").read_text(encoding="utf-8")
    assert "distributionUrl=" in (tmp_path / ".mvn/wrapper/maven-wrapper.properties").read_text(encoding="utf-8")
