from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from app.adapters.vue import VueTaskBuilder, vue_plan_to_prompt_text, validate_vue_plan


def build_vue_plan(analysis_result: Dict[str, Any], backend_plan: Dict[str, Any] | None = None) -> Dict[str, Any]:
    plan = VueTaskBuilder().build(analysis_result, backend_plan=backend_plan).to_dict()
    ok, errors = validate_vue_plan(plan)
    if not ok:
        raise ValueError('; '.join(errors))
    return plan


def vue_plan_to_text(vue_plan: Dict[str, Any] | None) -> str:
    return vue_plan_to_prompt_text(vue_plan)


def save_vue_plan(vue_plan: Dict[str, Any], output_dir: str) -> Optional[str]:
    out = (output_dir or '').strip()
    if not out:
        return None
    root = Path(out)
    debug_dir = root / '.autopj_debug'
    debug_dir.mkdir(parents=True, exist_ok=True)
    path = debug_dir / 'vue_plan.json'
    path.write_text(json.dumps(vue_plan, ensure_ascii=False, indent=2), encoding='utf-8')
    return str(path)
