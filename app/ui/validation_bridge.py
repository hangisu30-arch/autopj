from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.validation import validate_generation_context, build_repair_plan, repair_plan_to_prompt_text


def build_validation_report(
    analysis_result: Dict[str, Any],
    backend_plan: Dict[str, Any] | None = None,
    jsp_plan: Dict[str, Any] | None = None,
    react_plan: Dict[str, Any] | None = None,
    vue_plan: Dict[str, Any] | None = None,
    nexacro_plan: Dict[str, Any] | None = None,
    frontend_key: str = '',
) -> Dict[str, Any]:
    return validate_generation_context(
        analysis_result=analysis_result,
        backend_plan=backend_plan,
        jsp_plan=jsp_plan,
        react_plan=react_plan,
        vue_plan=vue_plan,
        nexacro_plan=nexacro_plan,
        frontend_key=frontend_key,
    )


def validation_report_to_text(report: Dict[str, Any] | None) -> str:
    if not report:
        return ''
    lines = ['[GLOBAL VALIDATION REPORT - SOURCE OF TRUTH]']
    lines.append(f"- ok: {report.get('ok')}")
    lines.append(f"- frontend_key: {report.get('frontend_key') or '(none)'}")
    summary = report.get('summary') or {}
    lines.append(f"- total_checks: {summary.get('total_checks', 0)}")
    lines.append(f"- failed_checks: {summary.get('failed_checks', 0)}")
    lines.append(f"- total_errors: {summary.get('total_errors', 0)}")
    checks = report.get('checks') or []
    for check in checks:
        lines.append(f"  - {check.get('name')}: ok={check.get('ok')}, errors={len(check.get('errors') or [])}")
    for item in (report.get('classified_errors') or [])[:10]:
        lines.append(
            f"  - error_code={item.get('code')}, target={item.get('target')}, repairable={item.get('repairable')}, message={item.get('message')}"
        )
    return "\n".join(lines)


def build_auto_repair_plan(validation_report: Dict[str, Any]) -> Dict[str, Any]:
    return build_repair_plan(validation_report)


def auto_repair_plan_to_text(repair_plan: Dict[str, Any] | None) -> str:
    return repair_plan_to_prompt_text(repair_plan)


def save_validation_report(report: Dict[str, Any], output_dir: str) -> Optional[str]:
    out = (output_dir or '').strip()
    if not out:
        return None
    debug_dir = Path(out) / '.autopj_debug'
    debug_dir.mkdir(parents=True, exist_ok=True)
    path = debug_dir / 'validation_report.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(path)


def save_auto_repair_plan(repair_plan: Dict[str, Any], output_dir: str) -> Optional[str]:
    out = (output_dir or '').strip()
    if not out:
        return None
    debug_dir = Path(out) / '.autopj_debug'
    debug_dir.mkdir(parents=True, exist_ok=True)
    path = debug_dir / 'repair_plan.json'
    path.write_text(json.dumps(repair_plan, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(path)
