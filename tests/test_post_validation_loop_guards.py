from pathlib import Path
from types import SimpleNamespace

from app.validation import post_generation_repair as pgr


def _write(path: Path, text: str = 'x') -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_reconcile_rel_paths_prefers_existing_config_helper(tmp_path: Path):
    actual = tmp_path / 'src/main/java/egovframework/test/config/WebMvcConfig.java'
    _write(actual, 'package egovframework.test.config; public class WebMvcConfig {}')

    rels = pgr._reconcile_rel_paths(
        tmp_path,
        ['src/main/java/egovframework/test/generic/WebMvcConfig.java'],
    )

    assert rels == ['src/main/java/egovframework/test/config/WebMvcConfig.java']



def test_compile_repair_loop_guard_stops_repeated_same_signature(tmp_path: Path, monkeypatch):
    cfg = SimpleNamespace(backend_key='springboot')
    manifest = {'src/main/java/demo/Foo.java': {'source_path': 'src/main/java/demo/Foo.java', 'purpose': 'generated', 'spec': 'class Foo {}'}}

    runtime_a = {
        'status': 'failed',
        'compile': {
            'status': 'failed',
            'command': 'mvn compile',
            'errors': [
                {'code': 'compile_error', 'path': 'src/main/java/demo/Foo.java', 'message': 'cannot find symbol A'}
            ],
        },
        'startup': {'status': 'skipped'},
        'endpoint_smoke': {'status': 'skipped'},
    }
    runtime_b = {
        'status': 'failed',
        'compile': {
            'status': 'failed',
            'command': 'mvn compile',
            'errors': [
                {'code': 'compile_error', 'path': 'src/main/java/demo/Foo.java', 'message': 'cannot find symbol B'}
            ],
        },
        'startup': {'status': 'skipped'},
        'endpoint_smoke': {'status': 'skipped'},
    }
    sequence = [runtime_a, runtime_b, runtime_a]

    def _runtime(*args, **kwargs):
        return sequence.pop(0) if sequence else runtime_a

    monkeypatch.setattr(pgr, 'run_spring_boot_runtime_validation', _runtime)
    monkeypatch.setattr(pgr, 'collect_compile_repair_targets', lambda runtime, manifest, project_root=None: ['src/main/java/demo/Foo.java'])
    monkeypatch.setattr(
        pgr,
        'regenerate_compile_failure_targets',
        lambda **kwargs: {
            'attempted': True,
            'targets': ['src/main/java/demo/Foo.java'],
            'changed': [{'path': 'src/main/java/demo/Foo.java', 'reason': 'simulated'}],
            'skipped': [],
        },
    )

    runtime_validation, rounds = pgr._run_compile_repair_loop(
        root=tmp_path,
        cfg=cfg,
        manifest=manifest,
        regenerate_callback=None,
        use_exec=False,
        frontend_key='jsp',
        max_regen_attempts=1,
        max_rounds=4,
    )

    assert runtime_validation['compile']['status'] == 'failed'
    assert len(rounds) == 3
    assert rounds[-1]['terminal_failure'] == 'compile_repair_loop_guard'
    assert rounds[-1]['targets'] == ['src/main/java/demo/Foo.java']


def test_startup_followup_loop_guard_stops_repeated_same_fingerprint(tmp_path: Path, monkeypatch):
    cfg = SimpleNamespace(backend_key='springboot')
    manifest = {}
    runtime_failed = {
        'status': 'failed',
        'compile': {'status': 'ok', 'errors': []},
        'startup': {'status': 'failed', 'errors': [
            {'code': 'ambiguous_request_mapping', 'path': 'src/main/java/demo/SignupController.java', 'message': 'Spring request mapping conflict detected', 'route': '/login/actionLogin.do'}
        ]},
        'endpoint_smoke': {'status': 'skipped', 'results': []},
    }

    calls = {'count': 0}

    def fake_startup_handoff(root, cfg, runtime_validation, round_no, before_runtime=None):
        calls['count'] += 1
        return runtime_failed, {
            'round': round_no,
            'attempted': True,
            'targets': ['src/main/java/demo/SignupController.java'],
            'changed': [{'path': 'src/main/java/demo/SignupController.java'}],
            'skipped': [],
            'before': pgr._runtime_snapshot(before_runtime or runtime_validation),
            'after': pgr._runtime_snapshot(runtime_failed),
            'terminal_failure': '',
        }

    monkeypatch.setattr(pgr, '_run_startup_repair_handoff', fake_startup_handoff)

    current_runtime, compile_rounds, startup_rounds, smoke_rounds = pgr._run_runtime_followup_loops(
        root=tmp_path,
        cfg=cfg,
        manifest=manifest,
        file_ops=[],
        rel_paths=[],
        regenerate_callback=None,
        use_exec=False,
        frontend_key='jsp',
        max_regen_attempts=0,
        runtime_validation=runtime_failed,
        allow_smoke=False,
    )

    assert current_runtime['startup']['status'] == 'failed'
    assert compile_rounds == []
    assert smoke_rounds == []
    assert len(startup_rounds) == 2
    assert startup_rounds[0]['changed']
    assert startup_rounds[1]['terminal_failure'] == 'startup_repair_loop_guard'
    assert calls['count'] == 1


def test_runtime_followup_stops_after_compile_failure_unchanged(tmp_path: Path, monkeypatch):
    cfg = SimpleNamespace(backend_key='springboot')
    manifest = {'src/main/java/demo/Foo.java': {'source_path': 'src/main/java/demo/Foo.java', 'purpose': 'generated', 'spec': 'class Foo {}'}}
    runtime_failed = {
        'status': 'failed',
        'compile': {
            'status': 'failed',
            'command': 'mvn compile',
            'errors': [
                {'code': 'compile_error', 'path': 'src/main/java/demo/Foo.java', 'message': 'cannot find symbol A'}
            ],
        },
        'startup': {'status': 'skipped', 'errors': []},
        'endpoint_smoke': {'status': 'skipped', 'results': []},
    }

    calls = {'count': 0}

    def fake_compile_loop(**kwargs):
        calls['count'] += 1
        return runtime_failed, [{
            'round': 1,
            'attempted': True,
            'targets': ['src/main/java/demo/Foo.java'],
            'changed': [{'path': 'src/main/java/demo/Foo.java', 'reason': 'simulated'}],
            'skipped': [],
            'before': pgr._runtime_snapshot(runtime_failed),
            'after': pgr._runtime_snapshot(runtime_failed),
            'terminal_failure': 'compile_failure_unchanged',
        }]

    monkeypatch.setattr(pgr, '_run_compile_repair_loop', fake_compile_loop)

    current_runtime, compile_rounds, startup_rounds, smoke_rounds = pgr._run_runtime_followup_loops(
        root=tmp_path,
        cfg=cfg,
        manifest=manifest,
        file_ops=[],
        rel_paths=[],
        regenerate_callback=None,
        use_exec=False,
        frontend_key='jsp',
        max_regen_attempts=0,
        runtime_validation=runtime_failed,
        allow_smoke=False,
    )

    assert current_runtime['compile']['status'] == 'failed'
    assert len(compile_rounds) == 1
    assert compile_rounds[-1]['terminal_failure'] == 'compile_failure_unchanged'
    assert startup_rounds == []
    assert smoke_rounds == []
    assert calls['count'] == 1
