from pathlib import Path

from app.validation.backend_compile_repair import enforce_generated_project_invariants, regenerate_compile_failure_targets
from app.validation.generated_project_validator import validate_generated_project


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class _Cfg:
    project_name = "demo"


def test_enforce_generated_project_invariants_aligns_java_public_types(tmp_path: Path):
    root = tmp_path
    user_vo = root / "src/main/java/egovframework/test/user/service/vo/UserVO.java"
    _write(user_vo, "package egovframework.test.user.service.vo;\n\npublic class userVO {\n    public userVO() {}\n}\n")
    report = enforce_generated_project_invariants(root)
    body = user_vo.read_text(encoding="utf-8")
    assert "public class UserVO" in body
    assert "public UserVO()" in body
    assert report["changed_count"] >= 1


def test_regenerate_compile_failure_targets_reapplies_invariants_after_regen(tmp_path: Path):
    root = tmp_path
    rel = "src/main/java/egovframework/test/user/web/UserController.java"
    target = root / rel
    _write(target, "package egovframework.test.user.web;\n\npublic class userController {\n    public userController() {}\n}\n")

    runtime_report = {
        "compile": {
            "status": "failed",
            "errors": [
                {"path": rel, "message": "class userController is public, should be declared in a file named UserController.java"}
            ],
            "raw_output": "",
            "log_tail": "",
        },
        "startup": {"status": "skipped"},
        "endpoint_smoke": {"status": "skipped"},
    }
    manifest = {rel: {"source_path": rel, "purpose": "controller", "spec": target.read_text(encoding="utf-8")}}

    def regen_callback(source_path, purpose, spec, reason):
        return {"path": source_path, "content": "package egovframework.test.user.web;\n\npublic class userController {\n    public userController() {}\n}\n"}

    def apply_callback(project_root, cfg, op, use_execution_core):
        _write(Path(project_root) / op["path"], op["content"])
        return {"written_files": [op["path"]]}

    report = regenerate_compile_failure_targets(
        project_root=root,
        cfg=_Cfg(),
        manifest=manifest,
        runtime_report=runtime_report,
        regenerate_callback=regen_callback,
        apply_callback=apply_callback,
        use_execution_core=False,
        frontend_key="jsp",
        max_attempts=1,
    )

    body = target.read_text(encoding="utf-8")
    assert "public class UserController" in body
    assert "public class UserController" in body
    assert "public class userController" not in body
    assert any("aligned" in str(item.get("reason") or "") or "realigned" in str(item.get("reason") or "") for item in report["changed"])


def test_validate_generated_project_ignores_user_calendar_false_positive(tmp_path: Path):
    root = tmp_path
    _write(root / "src/main/webapp/WEB-INF/views/user/userCalendar.jsp", "<div>user</div>")
    report = validate_generated_project(root, _Cfg(), manifest={}, include_runtime=False)
    issues = report.get("static_issues") or []
    assert not any((item.get("type") == "calendar_controller_missing" and "user/userCalendar.jsp" in str(item.get("path") or "")) for item in issues)
