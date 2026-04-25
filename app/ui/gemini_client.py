# path: app/ui/gemini_client.py
from __future__ import annotations

from dataclasses import dataclass
import re


# ✅ 하드코딩 키(사용자가 원하면 여기 값만 교체)
GEMINI_API_KEY = "AIzaSyBD8u2cJWPg8ycscliEfyh6lOH3jqvN5IY"
GEMINI_MODEL = "gemini-3-flash-preview"


@dataclass
class GeminiCallResult:
    ok: bool
    text: str = ""
    error: str = ""


def _parse_retry_after_seconds(msg: str) -> int | None:
    """Gemini 429 메시지에서 retry 시간을 최대한 추출."""
    if not msg:
        return None
    m = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", msg, re.IGNORECASE)
    if m:
        try:
            return int(float(m.group(1)))
        except Exception:
            return None
    m = re.search(r"retryDelay'\s*:\s*'([0-9]+)s'", msg)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            return None
    return None


def call_gemini(prompt: str) -> GeminiCallResult:
    """Gemini 호출 (503/429 대응 + 모델 fallback)."""
    import os
    import time

    try:
        from google import genai
    except Exception as e:
        return GeminiCallResult(ok=False, error=f"google genai import failed: {e}")

    primary = os.getenv("AI_PG_GEMINI_MODEL") or GEMINI_MODEL
    fb_env = os.getenv("AI_PG_GEMINI_FALLBACK_MODELS", "").strip()
    if fb_env:
        fallbacks = [x.strip() for x in fb_env.split(",") if x.strip()]
    else:
        fallbacks = [
            "gemini-3.1-flash-lite-preview",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ]

    models = []
    for m in [primary] + fallbacks:
        if m and m not in models:
            models.append(m)

    last_err = ""
    client = genai.Client(api_key=GEMINI_API_KEY)

    for model in models:
        for attempt in range(1, 4):
            try:
                resp = client.models.generate_content(model=model, contents=prompt)
                text = (getattr(resp, "text", None) or "").strip()
                if not text:
                    last_err = f"empty response from model={model}"
                    continue
                return GeminiCallResult(ok=True, text=text)
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                last_err = f"model={model} attempt={attempt} err={msg}"

                retry_after = _parse_retry_after_seconds(msg)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "Quota exceeded" in msg:
                    wait_s = retry_after if retry_after is not None else min(8, 2 ** attempt)
                    time.sleep(wait_s)
                    continue
                if "503" in msg or "UNAVAILABLE" in msg or "high demand" in msg.lower():
                    wait_s = min(10, 2 ** attempt)
                    time.sleep(wait_s)
                    continue
                break

    return GeminiCallResult(ok=False, error=last_err or "Gemini call failed")
