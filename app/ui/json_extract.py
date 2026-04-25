# path: app/ui/json_extract.py
from __future__ import annotations

import json
import re

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
_FIRST_ARRAY_RE = re.compile(r"\[", re.MULTILINE)
_FIRST_OBJ_RE = re.compile(r"\{", re.MULTILINE)


def _extract_first_balanced(s: str, start_idx: int) -> str:
    """Extract the first balanced JSON object/array starting at start_idx.

    Handles strings and escapes to avoid stopping at braces inside strings.
    This is best-effort and assumes JSON-like structure.
    """
    if start_idx < 0 or start_idx >= len(s):
        return (s or "").strip()

    open_ch = s[start_idx]
    close_ch = "]" if open_ch == "[" else "}"

    depth = 0
    in_str = False
    esc = False

    for i in range(start_idx, len(s)):
        ch = s[i]

        if in_str:
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = False
            continue

        if ch == '"':
            in_str = True
            continue

        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return s[start_idx : i + 1].strip()

    return s[start_idx:].strip()


def extract_json_array_text(s: str) -> str:
    """Best-effort extraction of a JSON array from a model response."""
    if not s:
        return ""

    m = _JSON_FENCE_RE.search(s)
    if m:
        candidate = (m.group(1) or "").strip()
        if candidate:
            return candidate

    m2 = _FIRST_ARRAY_RE.search(s)
    if not m2:
        return s.strip()

    return _extract_first_balanced(s, m2.start())


def extract_json_object_or_array_text(s: str) -> str:
    """Best-effort extraction of a JSON object or array from a model response."""
    if not s:
        return ""

    m = _JSON_FENCE_RE.search(s)
    if m:
        candidate = (m.group(1) or "").strip()
        if candidate:
            return candidate

    m2 = _FIRST_ARRAY_RE.search(s)
    if m2:
        return _extract_first_balanced(s, m2.start())

    m3 = _FIRST_OBJ_RE.search(s)
    if m3:
        return _extract_first_balanced(s, m3.start())

    return s.strip()


def maybe_extract_valid_json_text(s: str) -> str:
    """Return the first valid JSON object/array found in a model response, or the original text."""
    text = (s or "").strip()
    if not text:
        return text
    try:
        candidate = extract_json_object_or_array_text(text)
        if not candidate or candidate[:1] not in ("{", "["):
            return text
        idx = text.find(candidate)
        if idx > 0:
            prefix = text[:idx]
            # [수정] 순수 코드/문장 안의 brace는 건드리지 않고, 개행/코드펜스 뒤 JSON만 추출한다.
            if "```" not in prefix and "\n" not in prefix and "\r" not in prefix:
                return text
        json.loads(candidate)
        return candidate
    except Exception:
        pass
    return text
