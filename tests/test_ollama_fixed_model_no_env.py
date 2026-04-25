import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _reload(module_name: str):
    if module_name in sys.modules:
        del sys.modules[module_name]
    return importlib.import_module(module_name)


def test_app_ui_ollama_client_ignores_env(monkeypatch):
    monkeypatch.setenv("AI_PG_OLLAMA_MODEL", "llama3")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9999")
    mod = _reload("app.ui.ollama_client")
    assert mod.OLLAMA_MODEL == "qwen2.5-coder:14b"
    assert mod.OLLAMA_BASE_URL == "http://localhost:11434"
    assert mod.OLLAMA_GENERATE_URL == "http://localhost:11434/api/generate"


def test_gemini_ui_source_uses_fixed_model_and_url():
    source = (ROOT / "gemini_ui.py").read_text(encoding="utf-8")
    assert 'OLLAMA_BASE_URL = "http://localhost:11434"' in source
    assert 'OLLAMA_MODEL = "qwen2.5-coder:14b"' in source
    assert 'AI_PG_OLLAMA_MODEL' not in source.split('OLLAMA_MODEL = "qwen2.5-coder:14b"', 1)[1]
