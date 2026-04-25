from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from execution_core.builtin_crud import builtin_file, schema_for


def _safe_segment(text: str, default: str = "app") -> str:
    value = re.sub(r"[^A-Za-z0-9_]+", "", text or "").strip("_")
    return value or default


def _project_base_package(project_name: str) -> str:
    segment = _safe_segment(project_name, "example").lower()
    return f"egovframework.{segment}"


def builtin_shortcut_content(path: str, project_name: str = "") -> str:
    norm = (path or "").replace("\\", "/").strip()
    if not norm:
        return ""

    filename = Path(norm).name
    if filename != "MyBatisConfig.java":
        return ""

    base_package = _project_base_package(project_name)
    schema = schema_for("Item")
    content = builtin_file("java/config/MyBatisConfig.java", base_package, schema)
    return content or ""
