from pathlib import Path

from app.validation.backend_compile_repair import _local_contract_repair


class DummyCfg:
    project_name = "test"


def test_local_contract_repair_refreshes_webmvcconfig_with_builtin_fallback(tmp_path: Path):
    p = tmp_path / "src/main/java/egovframework/test/config/WebMvcConfig.java"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("package egovframework.test.config;\n\npublic class WebMvcConfig {\n    MissingType field;\n}\n", encoding="utf-8")

    changed = _local_contract_repair(tmp_path, DummyCfg(), {}, ["src/main/java/egovframework/test/config/WebMvcConfig.java"], {"compile": {"errors": [{"code": "cannot_find_symbol", "path": "src/main/java/egovframework/test/config/WebMvcConfig.java"}]}})

    body = p.read_text(encoding="utf-8")
    assert "public class WebMvcConfig" in body
    assert "MissingType" not in body
    assert any((item.get("path") == "src/main/java/egovframework/test/config/WebMvcConfig.java") for item in changed)
