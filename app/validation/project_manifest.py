from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


_HTTP_METHOD_ANNOTATIONS = ("GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping", "RequestMapping")


def _normalize_rel_path(path: str) -> str:
    return (path or "").replace("\\", "/").lstrip("./")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return path.read_text(encoding="utf-8", errors="ignore")


def _iter_report_paths(report: Optional[Dict[str, Any]]) -> List[str]:
    rels: List[str] = []
    seen = set()
    if not report:
        return rels
    for key in ("created", "overwritten"):
        for raw in report.get(key) or []:
            rel = _normalize_rel_path(str(raw))
            if rel and rel not in seen:
                seen.add(rel)
                rels.append(rel)
    return rels


def _collect_existing_files(project_root: Path) -> List[str]:
    files: List[str] = []
    for path in project_root.rglob("*"):
        if path.is_file() and ".autopj_debug" not in path.parts:
            files.append(_normalize_rel_path(str(path.relative_to(project_root))))
    return sorted(files)


def _class_level_request_path(body: str) -> str:
    m = re.search(r"@RequestMapping\(\s*(?:value\s*=\s*)?\{?\s*\"([^\"]+)\"", body)
    if not m:
        return ""
    return (m.group(1) or "").strip()


def _discover_routes(project_root: Path) -> List[Dict[str, str]]:
    routes: List[Dict[str, str]] = []
    java_root = project_root / "src/main/java"
    if not java_root.exists():
        return routes

    for controller in java_root.rglob("*Controller.java"):
        body = _read_text(controller)
        rel = _normalize_rel_path(str(controller.relative_to(project_root)))
        base = _class_level_request_path(body)
        for ann in _HTTP_METHOD_ANNOTATIONS:
            pattern = re.compile(
                rf"@{ann}\(\s*(?:value\s*=\s*)?\{{?\s*\"([^\"]+)\"",
                re.MULTILINE,
            )
            for match in pattern.finditer(body):
                route = (match.group(1) or "").strip()
                full = f"{base.rstrip('/')}/{route.lstrip('/')}" if base else route
                full = re.sub(r"//+", "/", full)
                full = full if full.startswith("/") else f"/{full}"
                method = ann.replace("Mapping", "").upper()
                if method == "REQUEST":
                    method = "ANY"
                routes.append({"controller": rel, "method": method, "path": full})
    return sorted(routes, key=lambda x: (x.get("path") or "", x.get("method") or ""))


def build_generation_manifest(
    project_root: Path,
    cfg: Any,
    report: Optional[Dict[str, Any]] = None,
    file_ops: Optional[List[Dict[str, Any]]] = None,
    use_execution_core: Optional[bool] = None,
) -> Dict[str, Any]:
    root = Path(project_root)
    generated_files = _iter_report_paths(report)
    file_specs: Dict[str, Dict[str, str]] = {}
    for item in file_ops or []:
        raw_path = _normalize_rel_path(str(item.get("path") or ""))
        if not raw_path:
            continue
        file_specs[raw_path] = {
            "purpose": str(item.get("purpose") or "generated"),
            "spec": str(item.get("content") or ""),
        }

    manifest = {
        "project_name": getattr(cfg, "project_name", "") or "",
        "frontend_key": getattr(cfg, "frontend_key", "") or "",
        "database_key": getattr(cfg, "database_key", "") or "",
        "generated_files": generated_files,
        "actual_existing_files": _collect_existing_files(root),
        "file_specs": file_specs,
        "routes": _discover_routes(root),
    }
    return manifest


def write_generation_manifest(
    project_root: Path,
    cfg: Any,
    report: Optional[Dict[str, Any]] = None,
    file_ops: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    manifest = build_generation_manifest(project_root, cfg, report=report, file_ops=file_ops)
    debug_dir = Path(project_root) / ".autopj_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / "generation_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest
