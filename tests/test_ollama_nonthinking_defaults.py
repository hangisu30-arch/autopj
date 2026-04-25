from pathlib import Path


def test_ollama_client_disables_thinking_by_default():
    text = Path("app/ui/ollama_client.py").read_text(encoding="utf-8")
    assert "OLLAMA_THINK = False" in text
    assert '"think": OLLAMA_THINK' in text


def test_main_window_warmup_does_not_restart_running_ollama():
    text = Path("app/ui/main_window.py").read_text(encoding="utf-8")
    assert 'restart_if_running=False' in text
