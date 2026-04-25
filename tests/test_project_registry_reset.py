from __future__ import annotations

import os
from pathlib import Path

from app.ui import project_registry as pr


def test_clear_registry_and_summary(tmp_path: Path, monkeypatch):
    registry_file = tmp_path / 'project_registry.json'
    monkeypatch.setenv(pr.REGISTRY_ENV_KEY, str(registry_file))

    project_dir = tmp_path / 'sample_project'
    (project_dir / 'src').mkdir(parents=True)
    (project_dir / 'pom.xml').write_text('<project/>', encoding='utf-8')

    class Cfg:
        project_name = 'sample'
        backend_key = 'egov_spring'
        frontend_key = 'jsp'
        database_key = 'mysql'
        operation_mode = 'create'
        selected_project_id = ''
        extra_requirements = 'demo prompt'

    entry = pr.register_project(project_dir, cfg=Cfg(), report={'generated': 3})
    assert entry is not None
    summary = pr.registry_summary()
    assert summary['count'] == 1
    assert summary['available'] == 1

    pr.clear_registry()
    assert pr.load_registry() == []
    summary_after = pr.registry_summary()
    assert summary_after['count'] == 0
    assert summary_after['available'] == 0


def test_remove_registered_project(tmp_path: Path, monkeypatch):
    registry_file = tmp_path / 'project_registry.json'
    monkeypatch.setenv(pr.REGISTRY_ENV_KEY, str(registry_file))

    class Cfg:
        backend_key = 'egov_spring'
        frontend_key = 'jsp'
        database_key = 'mysql'
        operation_mode = 'create'
        selected_project_id = ''
        extra_requirements = ''
        def __init__(self, name: str):
            self.project_name = name

    ids = []
    for name in ('alpha', 'beta'):
        root = tmp_path / name
        (root / 'src').mkdir(parents=True)
        (root / 'pom.xml').write_text('<project/>', encoding='utf-8')
        entry = pr.register_project(root, cfg=Cfg(name), report={'generated': 1})
        ids.append(entry['id'])

    assert pr.remove_registered_project(ids[0]) is True
    remaining = pr.load_registry()
    assert len(remaining) == 1
    assert remaining[0]['id'] == ids[1]
    assert pr.remove_registered_project('') is False
