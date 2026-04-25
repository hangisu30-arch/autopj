from pathlib import Path

from app.ui.post_validation_logging import post_validation_failure_message
from app.validation.post_generation_repair import _startup_failure_signature
from app.validation.runtime_smoke import _augment_startup_failure_result, write_runtime_report


def test_startup_failure_message_includes_runtime_diagnostics():
    post_validation = {
        "remaining_invalid_count": 1,
        "runtime_validation": {
            "compile": {"status": "ok", "errors": []},
            "startup": {
                "status": "failed",
                "root_cause": "Caused by: duplicate column name 'role_cd'",
                "failure_signature": "sql_error|duplicate column name '#role_cd'",
                "log_path": ".autopj_debug/startup_raw.log",
                "errors": [],
            },
            "endpoint_smoke": {"status": "skipped"},
        },
    }
    msg = post_validation_failure_message(post_validation)
    assert "startup_root_cause=Caused by: duplicate column name 'role_cd'" in msg
    assert "startup_signature=sql_error|duplicate column name '#role_cd'" in msg
    assert "startup_log=.autopj_debug/startup_raw.log" in msg


def test_augment_startup_failure_result_persists_debug_files(tmp_path: Path):
    result = {
        "status": "failed",
        "errors": [{"code": "sql_error", "message": "SQL or schema mismatch detected", "snippet": "Caused by: duplicate column name 'role_cd'"}],
        "log_tail": "Application run failed\nCaused by: duplicate column name 'role_cd'\nclass path resource [schema.sql]",
    }
    augmented = _augment_startup_failure_result(tmp_path, result, result["log_tail"], result["errors"])
    assert augmented["root_cause"]
    assert augmented["failure_signature"].startswith("sql_error|")
    assert augmented["log_path"] == ".autopj_debug/startup_raw.log"
    assert (tmp_path / ".autopj_debug" / "startup_raw.log").exists()
    assert (tmp_path / ".autopj_debug" / "startup_errors.json").exists()
    assert "schema.sql" in (augmented.get("related_paths") or [])[0]


def test_write_runtime_report_writes_startup_error_payload(tmp_path: Path):
    report = {
        "compile": {"status": "ok", "errors": []},
        "startup": {
            "status": "failed",
            "log_tail": "Application run failed",
            "root_cause": "Application run failed",
            "failure_signature": "application_run_failed|application run failed",
            "related_paths": ["schema.sql"],
            "errors": [{"code": "application_run_failed", "message": "Spring Boot startup failed", "snippet": "Application run failed"}],
        },
        "endpoint_smoke": {"status": "skipped"},
    }
    write_runtime_report(tmp_path, report)
    debug_dir = tmp_path / ".autopj_debug"
    assert (debug_dir / "runtime_smoke.json").exists()
    assert (debug_dir / "startup_raw.log").exists()
    assert (debug_dir / "startup_errors.json").exists()


def test_startup_failure_signature_prefers_explicit_signature():
    runtime_validation = {
        "startup": {
            "status": "failed",
            "failure_signature": "sql_error|duplicate column name '#role_cd'",
            "root_cause": "Caused by: duplicate column name 'role_cd'",
        }
    }
    assert _startup_failure_signature(runtime_validation) == "sql_error|duplicate column name '#role_cd'"
