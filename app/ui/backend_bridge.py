from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.engine.backend import BackendTaskBuilder, backend_plan_to_prompt_text, validate_backend_plan
from app.engine.analysis.analysis_result import AnalysisResult


def build_backend_plan(analysis_result: Dict[str, Any] | AnalysisResult) -> Dict[str, Any]:
    if isinstance(analysis_result, AnalysisResult):
        analysis_dict = analysis_result.to_dict()
    else:
        analysis_dict = analysis_result

    plan = BackendTaskBuilder().build(analysis_dict).to_dict()
    ok, errors = validate_backend_plan(plan)
    if not ok:
        raise ValueError("; ".join(errors))
    return plan


def backend_plan_to_text(backend_plan: Dict[str, Any] | None) -> str:
    return backend_plan_to_prompt_text(backend_plan)


def save_backend_plan(backend_plan: Dict[str, Any], output_dir: str) -> Optional[str]:
    out = (output_dir or "").strip()
    if not out:
        return None
    root = Path(out)
    debug_dir = root / ".autopj_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    path = debug_dir / "backend_plan.json"
    path.write_text(json.dumps(backend_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
