from pathlib import Path

from app.ui.state import ProjectConfig
from app.validation import post_generation_repair as pgr


def test_refresh_final_validation_reruns_when_final_deep_repair_changed(tmp_path: Path, monkeypatch):
    calls = {"validate": 0}

    monkeypatch.setattr(pgr, '_repair_index_redirect_assets', lambda *args, **kwargs: [])
    monkeypatch.setattr(pgr, '_reconcile_manifest_paths', lambda root, manifest: dict(manifest))
    monkeypatch.setattr(pgr, '_reconcile_rel_paths', lambda root, rel_paths: list(rel_paths))
    monkeypatch.setattr(pgr, '_prune_stale_auth_rel_paths', lambda root, rel_paths: list(rel_paths))

    def _fake_validate(root, cfg, manifest=None, include_runtime=False):
        calls['validate'] += 1
        return {'static_issue_count': 0, 'static_issues': []}

    monkeypatch.setattr(pgr, 'validate_generated_project', _fake_validate)

    manifest, rel_paths, deep_validation_after, entry_changed = pgr._refresh_final_validation_after_last_mile_repairs(
        root=tmp_path,
        cfg=ProjectConfig(project_name='test', frontend_key='jsp'),
        manifest={'files': []},
        file_ops=[],
        rel_paths=['src/main/webapp/WEB-INF/views/member/memberList.jsp'],
        frontend_key='jsp',
        deep_validation_after={'static_issue_count': 2, 'static_issues': [{'type': 'route_param_mismatch'}]},
        final_deep_repair={'changed_count': 1, 'changed': [{'path': 'src/main/java/egovframework/test/member/web/MemberController.java'}]},
    )

    assert calls['validate'] == 1
    assert deep_validation_after['static_issue_count'] == 0
    assert entry_changed == []
    assert rel_paths == ['src/main/webapp/WEB-INF/views/member/memberList.jsp']
    assert manifest == {'files': []}



def test_refresh_final_validation_reruns_when_entry_bundle_normalized(tmp_path: Path, monkeypatch):
    calls = {"validate": 0}

    monkeypatch.setattr(
        pgr,
        '_repair_index_redirect_assets',
        lambda *args, **kwargs: ['src/main/webapp/index.jsp', 'src/main/resources/static/index.html'],
    )
    monkeypatch.setattr(pgr, '_reconcile_manifest_paths', lambda root, manifest: dict(manifest, refreshed=True))
    monkeypatch.setattr(pgr, '_reconcile_rel_paths', lambda root, rel_paths: list(rel_paths) + ['src/main/webapp/index.jsp'])
    monkeypatch.setattr(pgr, '_prune_stale_auth_rel_paths', lambda root, rel_paths: list(dict.fromkeys(rel_paths)))

    def _fake_validate(root, cfg, manifest=None, include_runtime=False):
        calls['validate'] += 1
        return {'static_issue_count': 0, 'static_issues': [], 'marker': 'refreshed'}

    monkeypatch.setattr(pgr, 'validate_generated_project', _fake_validate)

    manifest, rel_paths, deep_validation_after, entry_changed = pgr._refresh_final_validation_after_last_mile_repairs(
        root=tmp_path,
        cfg=ProjectConfig(project_name='test', frontend_key='jsp'),
        manifest={'files': []},
        file_ops=[],
        rel_paths=['src/main/webapp/WEB-INF/views/login/login.jsp'],
        frontend_key='jsp',
        deep_validation_after={'static_issue_count': 0, 'static_issues': []},
        final_deep_repair={'changed_count': 0, 'changed': []},
    )

    assert calls['validate'] == 1
    assert entry_changed == ['src/main/webapp/index.jsp', 'src/main/resources/static/index.html']
    assert deep_validation_after['marker'] == 'refreshed'
    assert manifest['refreshed'] is True
    assert 'src/main/webapp/index.jsp' in rel_paths
