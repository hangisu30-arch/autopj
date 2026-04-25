from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.adapters.nexacro import NexacroTaskBuilder, nexacro_plan_to_prompt_text, validate_nexacro_plan


def build_nexacro_plan(analysis_result: Dict[str, Any], backend_plan: Dict[str, Any] | None = None) -> Dict[str, Any]:
    plan = NexacroTaskBuilder().build(analysis_result, backend_plan=backend_plan).to_dict()
    ok, errors = validate_nexacro_plan(plan)
    if not ok:
        raise ValueError('; '.join(errors))
    return plan


def nexacro_plan_to_text(nexacro_plan: Dict[str, Any] | None) -> str:
    return nexacro_plan_to_prompt_text(nexacro_plan)


def save_nexacro_plan(nexacro_plan: Dict[str, Any], output_dir: str) -> Optional[str]:
    out = (output_dir or '').strip()
    if not out:
        return None
    root = Path(out)
    debug_dir = root / '.autopj_debug'
    debug_dir.mkdir(parents=True, exist_ok=True)
    path = debug_dir / 'nexacro_plan.json'
    path.write_text(json.dumps(nexacro_plan, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(path)
