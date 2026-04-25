from pathlib import Path
import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


def test_batch_worker_surfaces_post_validation_failure(monkeypatch, tmp_path: Path):
    try:
        from PyQt6.QtWidgets import QApplication
    except ModuleNotFoundError:
        source = Path('app/ui/main_window.py').read_text(encoding='utf-8')
        assert 'self._log("[POST-VALIDATION] FAILED\\n" + post_tb)' in source
        assert 'raise RuntimeError(f"post_generation_validation_failed: {post_e}\\n{post_tb}")' in source
        return

    from app.ui.main_window import OllamaBatchWorker
    from app.ui.state import ProjectConfig
    import app.ui.main_window as mw

    app = QApplication.instance() or QApplication([])

    monkeypatch.setattr(mw, 'extract_json_array_text', lambda text: '[]')
    monkeypatch.setattr(mw, 'template_file_ops', lambda cfg: [])
    monkeypatch.setattr(mw, 'apply_file_ops', lambda ops, out_dir, overwrite=False: {'written': []})
    monkeypatch.setattr(mw, 'apply_file_ops_with_execution_core', lambda ops, out_dir, cfg, overwrite=False: {'written': []})
    monkeypatch.setattr(mw, '_should_use_execution_core_apply', lambda cfg: False)
    monkeypatch.setattr(mw, 'validate_and_repair_generated_files', lambda **kwargs: (_ for _ in ()).throw(RuntimeError('boom')))

    cfg = ProjectConfig()
    cfg.project_name = 'test'
    cfg.frontend_key = 'jsp'
    cfg.backend_key = 'spring'

    worker = OllamaBatchWorker(cfg=cfg, gemini_text='[]', out_dir=str(tmp_path), overwrite=True)
    logs = []
    failed = []
    done = []
    worker.log_sig.connect(logs.append)
    worker.failed_sig.connect(failed.append)
    worker.done_sig.connect(done.append)

    worker.run()

    assert not done
    assert failed
    assert any('[POST-VALIDATION] FAILED' in msg for msg in logs)
    report_text = (tmp_path / 'apply_report.json').read_text(encoding='utf-8')
    assert 'post_generation_validation_failed: boom' in report_text

    app.quit()
