# path: app/io/file_writer.py
from __future__ import annotations

from pathlib import Path
import stat


def _mark_executable_if_needed(target: Path) -> None:
    try:
        if target.name != "mvnw":
            return
        mode = target.stat().st_mode
        target.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass


def apply_file_ops(file_ops: list[dict], out_dir: Path, overwrite: bool = True) -> dict:
    report = {
        "created": [],
        "overwritten": [],
        "skipped": [],
        "errors": [],
    }

    for item in file_ops:
        path = item.get("path", "").strip()
        content = item.get("content", "")
        if not path or ".." in path or path.startswith("/") or ":" in path:
            report["errors"].append({"path": path, "reason": "invalid_path"})
            continue

        target = out_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists():
            if overwrite:
                target.write_text(content, encoding="utf-8")
                _mark_executable_if_needed(target)
                report["overwritten"].append(path)
            else:
                report["skipped"].append(path)
        else:
            target.write_text(content, encoding="utf-8")
            _mark_executable_if_needed(target)
            report["created"].append(path)

    return report
