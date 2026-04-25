from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

from app.engine.analysis import AnalysisContext, AnalysisEngine
from app.engine.analysis.analysis_result import AnalysisResult
from app.ui.state import ProjectConfig

_CREATE_TABLE_BLOCK_RE = re.compile(
    r"create\s+table\s+(?:if\s+not\s+exists\s+)?[`\"]?[A-Za-z_][A-Za-z0-9_]*[`\"]?\s*\((?:.|\n)*?\);",
    re.IGNORECASE,
)
_SIMPLE_COLUMN_RE = re.compile(
    r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*(?::|\s)\s*(?:varchar|char|text|clob|int|integer|bigint|number|decimal|numeric|date|datetime|timestamp)\b",
    re.IGNORECASE,
)


def extract_schema_text(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if not text:
        return ""

    ddl_blocks = [m.group(0).strip() for m in _CREATE_TABLE_BLOCK_RE.finditer(text)]
    if ddl_blocks:
        return "\n\n".join(ddl_blocks)

    simple_lines = []
    for line in text.splitlines():
        stripped = line.strip().rstrip(",")
        if not stripped:
            continue
        if _SIMPLE_COLUMN_RE.match(stripped):
            simple_lines.append(stripped)
    return "\n".join(simple_lines)


def build_analysis_from_config(cfg: ProjectConfig, project_root_hint: str = "") -> AnalysisResult:
    project_root = (cfg.output_dir or project_root_hint or f"./{cfg.project_name or 'project'}").strip()
    effective_requirements = cfg.effective_extra_requirements() if hasattr(cfg, "effective_extra_requirements") else (cfg.extra_requirements or "")
    ctx = AnalysisContext.from_inputs(
        project_root=project_root,
        project_name=cfg.project_name,
        frontend_mode=cfg.frontend_key,
        database_type=cfg.database_key,
        requirements_text=effective_requirements,
        schema_text=extract_schema_text(effective_requirements),
    )
    engine = AnalysisEngine()
    return engine.run(ctx)


def analysis_result_to_prompt_text(analysis_result: Dict[str, Any] | AnalysisResult | None) -> str:
    if analysis_result is None:
        return ""
    if isinstance(analysis_result, AnalysisResult):
        data = analysis_result.to_dict()
    else:
        data = analysis_result

    project = data.get("project") or {}
    domains = data.get("domains") or []
    if not isinstance(domains, list):
        domains = []

    lines = [
        "[COMMON ANALYSIS RESULT - SOURCE OF TRUTH]",
        f"- project_name: {project.get('project_name') or '(unknown)'}",
        f"- base_package: {project.get('base_package') or '(unknown)'}",
        f"- backend_mode: {project.get('backend_mode') or '(unknown)'}",
        f"- frontend_mode: {project.get('frontend_mode') or '(unknown)'}",
        f"- database_type: {project.get('database_type') or '(unknown)'}",
        f"- ir_version: {data.get('ir_version') or '(missing)'}",
    ]

    generation_policy = data.get("generation_policy") or {}
    if generation_policy:
        lines.append("- generation_policy:")
        for key, value in generation_policy.items():
            lines.append(f"  - {key}: {value}")

    if not domains:
        lines.append("- domains: (none detected)")
        return "\n".join(lines)

    lines.append("- domains:")
    for domain in domains:
        name = domain.get("name") or "domain"
        feature_kind = domain.get("feature_kind") or "unknown"
        feature_types = ", ".join(domain.get("feature_types") or []) or "(none)"
        source_table = domain.get("source_table") or name
        pk = domain.get("primary_key") or ""
        pages = ", ".join(domain.get("pages") or []) or "(none)"
        backend_files = ", ".join((domain.get("file_generation_plan") or {}).get("backend") or []) or "(none)"
        frontend_files = ", ".join((domain.get("file_generation_plan") or {}).get("frontend") or []) or "(none)"
        forbidden = ", ".join(domain.get("forbidden_artifacts") or [])
        ir = domain.get("ir") or {}
        contracts = domain.get("contracts") or (ir.get("contracts") if isinstance(ir, dict) else {}) or {}
        manifest = domain.get("artifact_manifest") or {}
        classification = ir.get("classification") or {}
        main_entry = ir.get("mainEntry") or {}
        capabilities = ", ".join(ir.get("capabilities") or []) or "(none)"
        hidden = ", ".join((ir.get("validationRules") or {}).get("formHiddenFields") or []) or "(none)"
        lines.append(
            f"  - {name}: feature_kind={feature_kind}, feature_types={feature_types}, primaryPattern={classification.get('primaryPattern') or '(none)'}, table={source_table}, primary_key={pk or '(none)'}, pages={pages}"
        )
        lines.append(f"    backend_files={backend_files}")
        lines.append(f"    frontend_files={frontend_files}")
        lines.append(f"    main_entry={main_entry.get('route') or '(none)'}")
        lines.append(f"    capabilities={capabilities}")
        lines.append(f"    form_hidden_fields={hidden}")
        if contracts:
            lines.append(f"    contracts={json.dumps(contracts, ensure_ascii=False, sort_keys=True)}")
        if manifest:
            lines.append(f"    artifact_manifest={json.dumps(manifest, ensure_ascii=False, sort_keys=True)}")
        fields = domain.get('fields') or []
        if fields:
            lines.append("    fields:")
            for field in fields:
                lines.append(
                    "      - "
                    f"name={field.get('name')}, column={field.get('column')}, java_type={field.get('java_type') or field.get('javaType')}, "
                    f"db_type={field.get('db_type') or field.get('dbType')}, pk={field.get('pk')}, role={field.get('role') or 'business'}"
                )
        if forbidden:
            lines.append(f"    forbidden={forbidden}")

    lines.append("- Authoritative generation order: business domain -> business table/columns -> SQL/Mapper -> backend -> frontend.")
    lines.append("- If domain fields are listed above, those columns are authoritative and must be reused unchanged in DDL, SQL, VO, Mapper XML, Controller binding, and screen fields.")
    lines.append("- Query XML is the primary authority for column alignment. Actual DB table columns and VO fields must match Mapper XML columns exactly.")
    lines.append("- If a search UI exists, it must expose all columns from the queried table as searchable fields. Do not omit table columns from search conditions.")
    lines.append("- Never invent extra columns such as *_name, title, status_cd, reg_dt unless they already exist in the domain field list or are explicitly required.")
    lines.append("- You MUST follow this analysis result and IR when planning file specs.")
    lines.append("- Prefer domain.ir.classification / mainEntry / frontendArtifacts over generic CRUD fallbacks.")
    lines.append("- Do not invent extra tables, columns, or pages outside this analysis unless explicitly required.")
    return "\n".join(lines)


def save_analysis_result(analysis_result: Dict[str, Any] | AnalysisResult, output_dir: str) -> Optional[str]:
    out = (output_dir or "").strip()
    if not out:
        return None
    if isinstance(analysis_result, AnalysisResult):
        data = analysis_result.to_dict()
    else:
        data = analysis_result

    root = Path(out)
    debug_dir = root / ".autopj_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    path = debug_dir / "analysis_result.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
