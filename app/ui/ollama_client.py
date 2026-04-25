# path: app/ui/ollama_client.py
from __future__ import annotations

from dataclasses import dataclass
import os
import json
import shutil
import subprocess
import time
from typing import Optional, Tuple, Union

import requests


OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_THINK = False

# Fixed Ollama target.
# Do not read model/base URL from environment variables. Stale IDE/system env
# values can silently override the intended runtime model and cause 404 errors.
OLLAMA_MODEL = "qwen2.5-coder:14b"

# Timeouts
_CONNECT_TIMEOUT_S = float(os.getenv("AI_PG_OLLAMA_CONNECT_TIMEOUT", "5"))
_READ_TIMEOUT_S = float(os.getenv("AI_PG_OLLAMA_READ_TIMEOUT", "1800"))  # 30m


def _is_ollama_alive(timeout_s: float = 1.5) -> bool:
    """Best-effort health check."""
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=timeout_s)
        return r.status_code == 200
    except Exception:
        return False


def _kill_ollama_process_best_effort() -> None:
    """Kill Ollama server process (best effort, Windows-first)."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/IM", "ollama.exe", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            subprocess.run(
                ["pkill", "-f", "ollama"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
    except Exception:
        pass


def _start_ollama_server_best_effort() -> None:
    """Start Ollama server process (best effort)."""
    exe = shutil.which("ollama")
    if not exe:
        raise RuntimeError("'ollama' executable not found in PATH.")

    kwargs = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
        )
    else:
        kwargs["start_new_session"] = True

    subprocess.Popen([exe, "serve"], **kwargs)  # noqa: S603,S607


def ensure_ollama_ready(*, restart_if_running: bool = True, wait_s: float = 20.0) -> None:
    """User-requested behavior:
    - if dead => start
    - if alive => restart (kill then start)
    - wait until it becomes reachable
    """
    alive = _is_ollama_alive()
    if alive and restart_if_running:
        _kill_ollama_process_best_effort()
        time.sleep(0.8)

    if (not alive) or restart_if_running:
        _start_ollama_server_best_effort()

    deadline = time.time() + max(2.0, float(wait_s))
    while time.time() < deadline:
        if _is_ollama_alive(timeout_s=1.5):
            return
        time.sleep(0.6)

    raise TimeoutError("Ollama server did not become ready in time.")


ResponseFormat = Union[str, dict]


def _stream_generate(
    prompt: str,
    on_chunk=None,
    *,
    options: Optional[dict] = None,
    response_format: Optional[ResponseFormat] = None,
) -> str:
    """Call /api/generate with streaming and return the concatenated response text."""

    model = OLLAMA_MODEL
    generate_url = OLLAMA_GENERATE_URL
    payload: dict = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "think": OLLAMA_THINK,
    }
    if options:
        payload["options"] = options
    if response_format is not None:
        payload["format"] = response_format

    timeout: Tuple[float, float] = (_CONNECT_TIMEOUT_S, _READ_TIMEOUT_S)

    chunks: list[str] = []
    with requests.post(generate_url, json=payload, stream=True, timeout=timeout) as r:
        if r.status_code >= 400:
            try:
                body = r.text
            except Exception:
                body = '<unavailable>'
            raise RuntimeError(f"Ollama HTTP {r.status_code} url={generate_url} model={model} body={body}")
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                chunks.append(str(line))
                continue

            thinking_piece = obj.get("thinking")
            if isinstance(thinking_piece, str) and thinking_piece and on_chunk is not None:
                try:
                    on_chunk(thinking_piece)
                except Exception:
                    pass

            resp_piece = obj.get("response")
            if isinstance(resp_piece, str) and resp_piece:
                chunks.append(resp_piece)
                if on_chunk is not None:
                    try:
                        on_chunk(resp_piece)
                    except Exception:
                        pass

            if obj.get("done") is True:
                break

    return "".join(chunks).strip()


@dataclass
class OllamaCallResult:
    ok: bool
    text: str = ""
    error: str = ""


def call_ollama(
    prompt: str,
    on_chunk=None,
    *,
    restart_if_running: bool = True,
    options: Optional[dict] = None,
    response_format: Optional[ResponseFormat] = None,
) -> OllamaCallResult:
    """Ollama 호출.

    - response_format:
      - None: 자유 텍스트
      - "json": JSON 출력 강제
      - dict: JSON schema 출력 강제(지원되는 Ollama 버전에서만)
    """
    try:
        ensure_ollama_ready(restart_if_running=restart_if_running)

        try:
            text = _stream_generate(prompt, on_chunk=on_chunk, options=options, response_format=response_format)
        except Exception as e:
            # schema 미지원 환경 대비: dict -> "json" 폴백
            if isinstance(response_format, dict):
                text = _stream_generate(prompt, on_chunk=on_chunk, options=options, response_format="json")
            else:
                raise e

        if not text:
            return OllamaCallResult(
                ok=False,
                error=(
                    "Ollama returned empty response.\n"
                    f"- Fixed model: {OLLAMA_MODEL}\n"
                    f"- Try: ollama pull {OLLAMA_MODEL}\n"
                    "- Try: ollama ps / ollama list\n"
                ),
            )
        return OllamaCallResult(ok=True, text=text)
    except Exception:
        import traceback

        return OllamaCallResult(ok=False, error=traceback.format_exc())
