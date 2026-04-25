from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.adapters.jsp import JspTaskBuilder, jsp_plan_to_prompt_text, validate_jsp_plan


def build_jsp_plan(analysis_result: Dict[str, Any], backend_plan: Dict[str, Any] | None = None) -> Dict[str, Any]:
    plan = JspTaskBuilder().build(analysis_result, backend_plan=backend_plan).to_dict()
    ok, errors = validate_jsp_plan(plan)
    if not ok:
        raise ValueError("; ".join(errors))
    return plan


def jsp_plan_to_text(jsp_plan: Dict[str, Any] | None) -> str:
    return jsp_plan_to_prompt_text(jsp_plan)


def save_jsp_plan(jsp_plan: Dict[str, Any], output_dir: str) -> Optional[str]:
    out = (output_dir or "").strip()
    if not out:
        return None
    root = Path(out)
    debug_dir = root / ".autopj_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    path = debug_dir / "jsp_plan.json"
    path.write_text(json.dumps(jsp_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
