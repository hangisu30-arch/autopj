from __future__ import annotations

import os
import re
from typing import Dict, List, Tuple

_CREATE_TABLE_BLOCK_RE = re.compile(
    r"create\s+table\s+(?:if\s+not\s+exists\s+)?[`\"]?[A-Za-z_][A-Za-z0-9_]*[`\"]?\s*\((?:.|\n)*?\);",
    re.IGNORECASE,
)
_ALTER_TABLE_BLOCK_RE = re.compile(
    r"alter\s+table\s+[`\"]?[A-Za-z_][A-Za-z0-9_]*[`\"]?.*?;",
    re.IGNORECASE,
)
_COMMENT_ON_COLUMN_RE = re.compile(
    r"comment\s+on\s+column\s+[`\"]?[A-Za-z_][A-Za-z0-9_]*[`\"]?\.[`\"]?[A-Za-z_][A-Za-z0-9_]*[`\"]?\s+is\s+['\"].*?['\"]\s*;",
    re.IGNORECASE,
)
_STRONG_RULE_RE = re.compile(
    r"(반드시|절대|금지|필수|반영|우선|must|never|forbid|forbidden|do not|should not)",
    re.IGNORECASE,
)
_SCHEMA_HINT_RE = re.compile(
    r"(table|column|schema|mapper|xml|vo|controller|jsp|react|vue|nexacro|login|signup|member|calendar|auth|password|useyn|regdt|createdat|updatedat|테이블|컬럼|스키마|로그인|회원가입|회원|달력|비밀번호|인증)",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


def _env_int(name: str, default: int) -> int:
    try:
        raw = os.getenv(name)
        return int(raw) if raw else default
    except Exception:
        return default


def _normalize(text: str) -> str:
    return str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def compact_prompt_block(text: str, max_chars: int = 4000, label: str = "BLOCK") -> str:
    body = _normalize(text)
    if len(body) <= max_chars:
        return body
    note = f"\n... [{label} COMPACTED {len(body)} -> <= {max_chars}] ...\n"
    usable = max(200, max_chars - len(note))
    head_budget = int(usable * 0.72)
    tail_budget = usable - head_budget

    head = body[:head_budget]
    tail = body[-tail_budget:] if tail_budget > 0 else ""

    if "\n" in head:
        head = head[: head.rfind("\n")]
    if "\n" in tail:
        tail = tail[tail.find("\n") + 1 :]

    compacted = (head + note + tail).strip()
    return compacted[:max_chars].strip()


def _paragraph_score(paragraph: str) -> int:
    text = paragraph.strip()
    if not text:
        return -1
    score = 0
    lowered = text.lower()
    if _STRONG_RULE_RE.search(text):
        score += 100
    if _SCHEMA_HINT_RE.search(text):
        score += 45
    if _BULLET_RE.match(text):
        score += 25
    if "create table" in lowered:
        score += 120
    if "alter table" in lowered or "comment on column" in lowered:
        score += 110
    if len(text) <= 220:
        score += 15
    elif len(text) >= 1200:
        score -= 10
    return score


def compact_requirements_text(text: str, max_chars: int | None = None, soft_limit: int | None = None) -> Tuple[str, Dict[str, int | bool]]:
    body = _normalize(text)
    soft = soft_limit if soft_limit is not None else _env_int("AI_PG_REQUIREMENTS_SOFT_LIMIT", 12000)
    target = max_chars if max_chars is not None else _env_int("AI_PG_REQUIREMENTS_TARGET_LIMIT", 9000)
    meta: Dict[str, int | bool] = {
        "original_chars": len(body),
        "soft_limit": soft,
        "target_chars": target,
        "compacted": False,
        "compacted_chars": len(body),
    }
    if not body:
        return "", meta
    if len(body) <= soft:
        return body, meta

    chosen: List[Tuple[int, str]] = []
    seen = set()
    remainder = body

    def _push(pos: int, chunk: str) -> None:
        key = chunk.strip()
        if not key or key in seen:
            return
        seen.add(key)
        chosen.append((pos, key))

    for regex in (_CREATE_TABLE_BLOCK_RE, _ALTER_TABLE_BLOCK_RE, _COMMENT_ON_COLUMN_RE):
        for m in regex.finditer(body):
            _push(m.start(), m.group(0).strip())
            remainder = remainder.replace(m.group(0), "\n")

    paragraphs: List[Tuple[int, int, str]] = []
    cursor = 0
    for part in re.split(r"\n\s*\n+", remainder):
        chunk = part.strip()
        if not chunk:
            cursor += len(part) + 2
            continue
        idx = body.find(chunk, cursor)
        if idx < 0:
            idx = cursor
        cursor = idx + len(chunk)
        paragraphs.append((idx, _paragraph_score(chunk), chunk))

    for idx, _, chunk in sorted(paragraphs, key=lambda x: (-x[1], x[0])):
        chunk = compact_prompt_block(chunk, max_chars=min(1400, max(400, target // 3)), label="REQUIREMENTS PARAGRAPH")
        _push(idx, chunk)

    chosen.sort(key=lambda x: x[0])
    header = (
        f"[REQUIREMENTS COMPACTED]\n"
        f"- original_chars: {len(body)}\n"
        f"- compacted_for_generation: true\n"
        f"- source_text_preserved_in_ui: true\n"
        f"- high-signal schema/rules only below\n"
    )
    out_parts: List[str] = [header.strip()]
    current_len = sum(len(p) + 2 for p in out_parts)
    for _, chunk in chosen:
        if current_len + len(chunk) + 2 > target:
            continue
        out_parts.append(chunk)
        current_len += len(chunk) + 2
    if len(out_parts) == 1:
        out_parts.append(compact_prompt_block(body, max_chars=max(1000, target - len(header) - 4), label="REQUIREMENTS"))

    compacted = "\n\n".join(out_parts).strip()
    meta["compacted"] = True
    meta["compacted_chars"] = len(compacted)
    return compacted, meta


def requirement_budget_report(text: str) -> Dict[str, int | bool]:
    _, meta = compact_requirements_text(text)
    return meta
