from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.adapters.react import ReactTaskBuilder, react_plan_to_prompt_text, validate_react_plan


def build_react_plan(analysis_result: Dict[str, Any], backend_plan: Dict[str, Any] | None = None) -> Dict[str, Any]:
    plan = ReactTaskBuilder().build(analysis_result, backend_plan=backend_plan).to_dict()
    ok, errors = validate_react_plan(plan)
    if not ok:
        raise ValueError('; '.join(errors))
    return plan


def react_plan_to_text(react_plan: Dict[str, Any] | None) -> str:
    return react_plan_to_prompt_text(react_plan)


def save_react_plan(react_plan: Dict[str, Any], output_dir: str) -> Optional[str]:
    out = (output_dir or '').strip()
    if not out:
        return None
    root = Path(out)
    debug_dir = root / '.autopj_debug'
    debug_dir.mkdir(parents=True, exist_ok=True)
    path = debug_dir / 'react_plan.json'
    path.write_text(json.dumps(react_plan, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(path)
