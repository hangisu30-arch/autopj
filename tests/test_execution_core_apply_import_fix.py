from pathlib import Path

from app.io.execution_core_apply import apply_file_ops_with_execution_core
from app.ui.state import ProjectConfig


def test_apply_runs_java_import_fixer_and_reports_changes(tmp_path: Path):
    wrong_model = tmp_path / "src/main/java/egovframework/demo/custom/model/Thing.java"
    wrong_service = tmp_path / "src/main/java/egovframework/demo/custom/service/ThingService.java"
    wrong_model.parent.mkdir(parents=True, exist_ok=True)
    wrong_service.parent.mkdir(parents=True, exist_ok=True)
    wrong_model.write_text(
        "package egovframework.demo.custom.model;\n\npublic class Thing {}\n",
        encoding="utf-8",
    )
    wrong_service.write_text(
        "package egovframework.demo.custom.service;\n\nimport egovframework.demo.custom.Thing;\n\npublic interface ThingService {\n    Thing get();\n}\n",
        encoding="utf-8",
    )

    cfg = ProjectConfig(project_name="demo", frontend_key="jsp", database_key="sqlite")
    report = apply_file_ops_with_execution_core([], tmp_path, cfg, overwrite=True)

    service = wrong_service.read_text(encoding="utf-8")
    assert "import egovframework.demo.custom.model.Thing;" in service
    patched = report.get("patched") or {}
    fixer = patched.get("java_import_fixer") or {}
    assert fixer.get("changed_count", 0) >= 1
