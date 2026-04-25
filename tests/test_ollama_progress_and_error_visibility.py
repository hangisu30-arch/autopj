from __future__ import annotations

import json
from types import SimpleNamespace

import app.ui.ollama_client as client


class DummyResponse:
    def __init__(self, status_code=200, lines=None, text=''):
        self.status_code = status_code
        self._lines = lines or []
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_lines(self, decode_unicode=True):
        yield from self._lines


def test_stream_generate_counts_thinking_as_progress(monkeypatch):
    chunks = []
    lines = [
        json.dumps({"thinking": "step1"}),
        json.dumps({"response": "CREATE TABLE x", "done": False}),
        json.dumps({"done": True}),
    ]

    def fake_post(url, json=None, stream=True, timeout=None):
        assert json["model"] == "qwen2.5-coder:14b"
        return DummyResponse(status_code=200, lines=lines)

    monkeypatch.delenv("AI_PG_OLLAMA_MODEL", raising=False)
    monkeypatch.setattr(client.requests, "post", fake_post)

    text = client._stream_generate("prompt", on_chunk=chunks.append)
    assert text == "CREATE TABLE x"
    assert chunks == ["step1", "CREATE TABLE x"]


def test_stream_generate_includes_body_and_model_on_http_error(monkeypatch):
    def fake_post(url, json=None, stream=True, timeout=None):
        return DummyResponse(status_code=404, text='{"error":"model not found"}')

    monkeypatch.setenv("AI_PG_OLLAMA_MODEL", "qwen2.5-coder:14b")
    monkeypatch.setattr(client.requests, "post", fake_post)

    try:
        client._stream_generate("prompt")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        msg = str(e)
        assert "model=qwen2.5-coder:14b" in msg
        assert 'body={"error":"model not found"}' in msg
        assert "url=http://localhost:11434/api/generate" in msg
