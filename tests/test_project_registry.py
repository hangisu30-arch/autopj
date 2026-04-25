from __future__ import annotations

from pathlib import Path

from app.ui.project_registry import (
    find_registered_project_by_path,
    list_registered_projects,
    register_project,
    validate_registered_project,
)
from app.ui.state import ProjectConfig


def test_register_project_and_lookup(tmp_path, monkeypatch):
    registry_path = tmp_path / "project_registry.json"
    monkeypatch.setenv("AUTOPJ_PROJECT_REGISTRY_PATH", str(registry_path))
    project_root = tmp_path / "demo-project"
    (project_root / "src" / "main" / "java").mkdir(parents=True)
    (project_root / "pom.xml").write_text("<project/>", encoding="utf-8")

    cfg = ProjectConfig(project_name="demo", backend_key="egov_spring", frontend_key="jsp", database_key="mysql")
    entry = register_project(project_root, cfg=cfg, report={"generated": 12})

    assert entry is not None
    assert entry["project_name"] == "demo"
    items = list_registered_projects()
    assert len(items) == 1
    found = find_registered_project_by_path(project_root)
    assert found is not None
    ok, validated, message = validate_registered_project(entry["id"])
    assert ok is True
    assert validated is not None
    assert message == "ok"


def test_register_project_updates_existing_entry(tmp_path, monkeypatch):
    registry_path = tmp_path / "project_registry.json"
    monkeypatch.setenv("AUTOPJ_PROJECT_REGISTRY_PATH", str(registry_path))
    project_root = tmp_path / "demo-project"
    (project_root / "src").mkdir(parents=True)
    (project_root / "pom.xml").write_text("<project/>", encoding="utf-8")

    cfg1 = ProjectConfig(project_name="demo-a", backend_key="egov_spring", frontend_key="jsp")
    first = register_project(project_root, cfg=cfg1, report={"generated": 3})
    cfg2 = ProjectConfig(project_name="demo-b", backend_key="egov_spring", frontend_key="react", operation_mode="modify")
    second = register_project(project_root, cfg=cfg2, report={"generated": 8})

    items = list_registered_projects()
    assert len(items) == 1
    assert first is not None and second is not None
    assert first["id"] == second["id"]
    assert items[0]["project_name"] == "demo-b"
    assert items[0]["frontend_key"] == "react"
    assert items[0]["last_generated_file_count"] == 8
