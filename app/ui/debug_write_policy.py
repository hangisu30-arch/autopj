from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

_TRUTHY = {"1", "true", "yes", "on", "y"}
_FALSY = {"0", "false", "no", "off", "n"}


def _as_bool(value: str | None, default: bool = False) -> bool:
    raw = (value or '').strip().lower()
    if not raw:
        return default
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    return default


def should_write_debug_artifacts(default: bool = False) -> bool:
    for key in ('AUTOPJ_WRITE_DEBUG_ARTIFACTS', 'AI_PG_WRITE_DEBUG_ARTIFACTS'):
        raw = os.getenv(key)
        if raw is not None and str(raw).strip() != '':
            return _as_bool(str(raw), default)
    return default


def ensure_debug_dir(project_root: str | Path, *, default: bool = False) -> Optional[Path]:
    if not should_write_debug_artifacts(default=default):
        return None
    root = Path(project_root)
    debug_dir = root / '.autopj_debug'
    debug_dir.mkdir(parents=True, exist_ok=True)
    return debug_dir


def write_debug_json(project_root: str | Path, filename: str, payload: Any, *, default: bool = False) -> Optional[Path]:
    debug_dir = ensure_debug_dir(project_root, default=default)
    if debug_dir is None:
        return None
    path = debug_dir / filename
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def write_debug_text(project_root: str | Path, filename: str, text: str, *, default: bool = False) -> Optional[Path]:
    debug_dir = ensure_debug_dir(project_root, default=default)
    if debug_dir is None:
        return None
    path = debug_dir / filename
    path.write_text(text or '', encoding='utf-8', errors='ignore')
    return path


def write_project_json(path: str | Path, payload: Any, *, default: bool = False) -> Optional[Path]:
    if not should_write_debug_artifacts(default=default):
        return None
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return out
