from pathlib import Path

from app.ui.state import ProjectConfig
from app.validation.generated_project_validator import _scan_search_fields_cover_all_columns
from app.validation.post_generation_repair import _run_smoke_repair_handoff


def test_search_fields_check_ignores_generation_metadata(tmp_path: Path):
    vo = tmp_path / 'src/main/java/demo/memberSchedule/service/MemberScheduleVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        'package demo;\n'
        'public class MemberScheduleVO {\n'
        '  private String memberNo;\n'
        '  private String scheduleTitle;\n'
        '  private String db;\n'
        '  private String schemaName;\n'
        '}\n',
        encoding='utf-8',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/memberSchedule/memberScheduleList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<form method="get">\n'
        '  <input name="memberNo" />\n'
        '  <input name="scheduleTitle" />\n'
        '  <button type="submit">search</button>\n'
        '</form>\n',
        encoding='utf-8',
    )

    issues = _scan_search_fields_cover_all_columns(tmp_path)
    assert issues == []


def test_smoke_repair_reverts_when_it_degrades_compile(tmp_path: Path, monkeypatch):
    target = tmp_path / 'src/main/java/demo/web/HomeController.java'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('class HomeController {}\n', encoding='utf-8')
    cfg = ProjectConfig(project_name='demo', frontend_key='jsp', database_key='mysql', backend_key='egov_spring')
    baseline = {
        'compile': {'status': 'ok', 'errors': []},
        'startup': {'status': 'ok', 'errors': []},
        'endpoint_smoke': {'status': 'failed', 'results': [{'route': '/x', 'ok': False}]},
    }
    degraded = {
        'compile': {'status': 'failed', 'errors': [{'path': str(target.relative_to(tmp_path)), 'message': 'boom'}]},
        'startup': {'status': 'skipped', 'errors': []},
        'endpoint_smoke': {'status': 'skipped', 'results': []},
    }

    def fake_repair_index_redirect_assets(root, cfg, file_ops, rel_paths):
        target.write_text('broken\n', encoding='utf-8')
        return [str(target.relative_to(tmp_path)).replace('\\', '/')]

    monkeypatch.setattr('app.validation.post_generation_repair._repair_index_redirect_assets', fake_repair_index_redirect_assets)
    monkeypatch.setattr('app.validation.post_generation_repair._repair_timed_out_calendar_endpoints', lambda *a, **k: [])
    monkeypatch.setattr('app.validation.post_generation_repair._repair_timed_out_edit_endpoints', lambda *a, **k: [])
    monkeypatch.setattr('app.validation.post_generation_repair._repair_timed_out_auth_endpoints', lambda *a, **k: [])
    monkeypatch.setattr('app.validation.post_generation_repair.run_spring_boot_runtime_validation', lambda *a, **k: degraded)

    after_runtime, smoke_round = _run_smoke_repair_handoff(
        root=tmp_path,
        cfg=cfg,
        file_ops=[],
        rel_paths=[str(target.relative_to(tmp_path)).replace('\\', '/')],
        runtime_validation=baseline,
        round_no=1,
        before_runtime=baseline,
    )

    assert after_runtime is baseline
    assert 'HomeController' in target.read_text(encoding='utf-8')
    assert any('degraded compile/startup' in (item.get('reason') or '') for item in (smoke_round.get('skipped') or []))
