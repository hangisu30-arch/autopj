from pathlib import Path

from app.validation.backend_compile_repair import regenerate_compile_failure_targets


class _Cfg:
    project_name = 'test'


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_compile_repair_handles_regen_placeholder_exception_without_crashing(tmp_path: Path):
    rel = 'src/main/java/egovframework/test/foo/Bar.java'
    _write(tmp_path / rel, 'package egovframework.test.foo; public class Bar {}')

    manifest = {
        rel: {
            'source_path': rel,
            'purpose': 'generated',
            'spec': '임의 파일',
        }
    }
    runtime_report = {
        'compile': {
            'status': 'failed',
            'errors': [
                {'path': rel, 'code': 'cannot_find_symbol', 'message': 'cannot find symbol'},
            ],
        },
        'startup': {'status': 'skipped'},
        'endpoint_smoke': {'status': 'skipped'},
    }

    def _regen(*args, **kwargs):
        raise ValueError("content contains placeholder '...'")

    result = regenerate_compile_failure_targets(
        project_root=tmp_path,
        cfg=_Cfg(),
        manifest=manifest,
        runtime_report=runtime_report,
        regenerate_callback=_regen,
        apply_callback=lambda *args, **kwargs: {},
        use_execution_core=False,
        frontend_key='jsp',
        max_attempts=1,
    )

    assert result['attempted'] is True
    assert rel in result['targets']
    skipped = {item['path']: item['reason'] for item in result['skipped']}
    assert rel in skipped
    assert "content contains placeholder '...'" in skipped[rel]
