from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


REGISTRY_ENV_KEY = "AUTOPJ_PROJECT_REGISTRY_PATH"
_DEFAULT_REGISTRY_FILE = "project_registry.json"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def registry_path() -> Path:
    override = (os.environ.get(REGISTRY_ENV_KEY) or "").strip()
    if override:
        path = Path(override).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    base_dir = Path.home() / ".autopj"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / _DEFAULT_REGISTRY_FILE


def normalize_project_path(path: str | Path) -> str:
    try:
        return str(Path(path).expanduser().resolve())
    except Exception:
        return str(Path(path).expanduser())


def _short_text(text: str, limit: int = 240) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _structure_markers(project_root: Path) -> list[str]:
    markers: list[str] = []
    checks = [
        "pom.xml",
        "package.json",
        "src/main/java",
        "src/main/resources",
        "src/main/webapp",
        ".autopj_debug",
    ]
    for rel in checks:
        target = project_root / rel
        markers.append(f"{rel}:{'1' if target.exists() else '0'}")
    return markers


def compute_project_fingerprint(project_root: str | Path) -> str:
    root = Path(project_root)
    digest = hashlib.sha1()
    normalized = normalize_project_path(root)
    digest.update(normalized.encode("utf-8", errors="ignore"))
    for marker in _structure_markers(root):
        digest.update(marker.encode("utf-8", errors="ignore"))
    return digest.hexdigest()


def load_registry() -> list[dict[str, Any]]:
    path = registry_path()
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
        obj = json.loads(raw)
    except Exception:
        return []
    if not isinstance(obj, dict):
        return []
    items = obj.get("projects")
    if not isinstance(items, list):
        return []
    result: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            result.append(dict(item))
    return result


def save_registry(entries: list[dict[str, Any]]) -> None:
    path = registry_path()
    payload = {
        "version": 1,
        "saved_at": _now_iso(),
        "projects": entries,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _entry_exists(entry: dict[str, Any]) -> bool:
    project_root = normalize_project_path(entry.get("project_root") or "")
    if not project_root:
        return False
    return Path(project_root).exists()


def list_registered_projects(*, include_missing: bool = False) -> list[dict[str, Any]]:
    entries = load_registry()
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        item = dict(entry)
        item["project_root"] = normalize_project_path(item.get("project_root") or "")
        item["path_exists"] = _entry_exists(item)
        if include_missing or item["path_exists"]:
            normalized.append(item)
    normalized.sort(key=lambda x: (x.get("updated_at") or x.get("created_at") or "", x.get("project_name") or ""), reverse=True)
    return normalized


def get_registered_project(project_id: str) -> dict[str, Any] | None:
    pid = (project_id or "").strip()
    if not pid:
        return None
    for entry in load_registry():
        if (entry.get("id") or "").strip() == pid:
            item = dict(entry)
            item["project_root"] = normalize_project_path(item.get("project_root") or "")
            item["path_exists"] = _entry_exists(item)
            return item
    return None


def find_registered_project_by_path(project_root: str | Path) -> dict[str, Any] | None:
    target = normalize_project_path(project_root)
    if not target:
        return None
    for entry in load_registry():
        if normalize_project_path(entry.get("project_root") or "") == target:
            item = dict(entry)
            item["project_root"] = target
            item["path_exists"] = _entry_exists(item)
            return item
    return None


def project_display_label(entry: dict[str, Any]) -> str:
    name = (entry.get("project_name") or "(이름 없음)").strip()
    backend = (entry.get("backend_key") or "-").strip()
    frontend = (entry.get("frontend_key") or "-").strip()
    path = normalize_project_path(entry.get("project_root") or "")
    status = "사용 가능" if Path(path).exists() else "경로 없음"
    return f"{name} | {backend}/{frontend} | {status} | {path}"


def validate_registered_project(project_id: str) -> tuple[bool, dict[str, Any] | None, str]:
    entry = get_registered_project(project_id)
    if not entry:
        return False, None, "저장된 autopj 프로젝트 목록에서 수정 대상을 선택하세요."
    project_root = Path(entry.get("project_root") or "")
    if not project_root.exists() or not project_root.is_dir():
        return False, entry, f"저장된 프로젝트 경로가 존재하지 않습니다: {project_root}"
    has_expected_structure = any((project_root / rel).exists() for rel in ("pom.xml", "package.json", "src", "src/main"))
    if not has_expected_structure:
        return False, entry, f"저장된 프로젝트 구조를 확인할 수 없습니다: {project_root}"
    return True, entry, "ok"


def register_project(project_root: str | Path, *, cfg=None, report: dict[str, Any] | None = None) -> dict[str, Any] | None:
    normalized_root = normalize_project_path(project_root)
    if not normalized_root:
        return None
    root = Path(normalized_root)
    if not root.exists() or not root.is_dir():
        return None

    entries = load_registry()
    existing_index: int | None = None
    selected_project_id = ""
    if cfg is not None:
        selected_project_id = (getattr(cfg, "selected_project_id", "") or "").strip()
    for idx, entry in enumerate(entries):
        if normalize_project_path(entry.get("project_root") or "") == normalized_root:
            existing_index = idx
            break
        if selected_project_id and (entry.get("id") or "").strip() == selected_project_id:
            existing_index = idx
            break

    now = _now_iso()
    project_name = ""
    if cfg is not None:
        project_name = (getattr(cfg, "project_name", "") or "").strip()
    if not project_name:
        project_name = root.name

    prompt_summary = ""
    if cfg is not None:
        prompt_summary = _short_text(getattr(cfg, "extra_requirements", "") or "")

    changed_files = 0
    if isinstance(report, dict):
        changed_files = int(report.get("generated", 0) or report.get("changed", 0) or 0)

    entry: dict[str, Any]
    if existing_index is None:
        entry = {
            "id": hashlib.sha1(normalized_root.encode("utf-8", errors="ignore")).hexdigest()[:16],
            "created_at": now,
        }
    else:
        entry = dict(entries[existing_index])

    entry.update(
        {
            "project_name": project_name,
            "project_root": normalized_root,
            "updated_at": now,
            "backend_key": (getattr(cfg, "backend_key", "") or entry.get("backend_key") or "").strip() if cfg is not None else (entry.get("backend_key") or ""),
            "frontend_key": (getattr(cfg, "frontend_key", "") or entry.get("frontend_key") or "").strip() if cfg is not None else (entry.get("frontend_key") or ""),
            "database_key": (getattr(cfg, "database_key", "") or entry.get("database_key") or "").strip() if cfg is not None else (entry.get("database_key") or ""),
            "operation_mode_last": (getattr(cfg, "operation_mode", "") or entry.get("operation_mode_last") or "").strip() if cfg is not None else (entry.get("operation_mode_last") or ""),
            "prompt_summary": prompt_summary or entry.get("prompt_summary") or "",
            "fingerprint": compute_project_fingerprint(root),
            "last_generated_file_count": changed_files,
        }
    )
    if "created_at" not in entry or not entry["created_at"]:
        entry["created_at"] = now

    if existing_index is None:
        entries.append(entry)
    else:
        entries[existing_index] = entry
    save_registry(entries)
    result = dict(entry)
    result["path_exists"] = True
    return result


def remove_registered_project(project_id: str) -> bool:
    pid = (project_id or "").strip()
    if not pid:
        return False
    entries = load_registry()
    filtered = [dict(entry) for entry in entries if (entry.get("id") or "").strip() != pid]
    if len(filtered) == len(entries):
        return False
    save_registry(filtered)
    return True


def clear_registry() -> None:
    save_registry([])


def registry_summary() -> dict[str, Any]:
    entries = list_registered_projects(include_missing=True)
    available = sum(1 for entry in entries if entry.get("path_exists"))
    return {
        "count": len(entries),
        "available": available,
        "missing": max(0, len(entries) - available),
        "path": str(registry_path()),
    }
