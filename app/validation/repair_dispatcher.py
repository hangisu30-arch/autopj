from __future__ import annotations

from typing import Any, Dict, List


def build_repair_plan(validation_report: Dict[str, Any]) -> Dict[str, Any]:
    classified = validation_report.get('classified_errors') or []
    actions: List[Dict[str, Any]] = []
    seen = set()
    for item in classified:
        code = item.get('code') or 'unknown'
        if code in seen:
            continue
        seen.add(code)
        if code == 'base_package_rule':
            actions.append({
                'action_type': 'recompute_analysis_naming',
                'target': 'analysis',
                'reason': item.get('message'),
                'suggested_files': ['app/engine/analysis/naming_rules.py', 'app/engine/analysis/analysis_context.py'],
            })
        elif code in {'backend_missing_artifact', 'controller_mode_mismatch', 'schema_vo_mismatch', 'mapper_namespace_mismatch', 'mybatis_config_invalid', 'mapper_mixed_mode', 'service_signature_import_mismatch', 'boot_scan_mismatch'}:
            actions.append({
                'action_type': 'rebuild_backend_plan',
                'target': 'backend',
                'reason': item.get('message'),
                'suggested_files': ['app/engine/backend/backend_task_builder.py'],
            })
        elif code in {'react_missing_artifact', 'frontend_mixing_jsp_into_react', 'react_path_root_invalid', 'route_missing', 'unsupported_import'}:
            actions.append({
                'action_type': 'rebuild_react_plan',
                'target': 'react',
                'reason': item.get('message'),
                'suggested_files': ['app/adapters/react/react_task_builder.py', 'app/adapters/react/react_validator.py'],
            })
        elif code in {'jsp_missing_artifact', 'jsp_path_root_invalid', 'jsp_controller_too_large', 'controller_binding_mismatch'}:
            actions.append({
                'action_type': 'rebuild_jsp_plan',
                'target': 'jsp',
                'reason': item.get('message'),
                'suggested_files': ['app/adapters/jsp/jsp_task_builder.py', 'app/adapters/jsp/jsp_validator.py'],
            })
        elif code in {'vue_missing_artifact', 'frontend_mixing_jsp_into_vue', 'vue_path_root_invalid', 'vue_analysis_mixing'}:
            actions.append({
                'action_type': 'rebuild_vue_plan',
                'target': 'vue',
                'reason': item.get('message'),
                'suggested_files': ['app/adapters/vue/vue_task_builder.py', 'app/adapters/vue/vue_validator.py'],
            })
        elif code in {'nexacro_missing_artifact', 'frontend_mixing_into_nexacro', 'nexacro_path_root_invalid', 'nexacro_analysis_mixing'}:
            actions.append({
                'action_type': 'rebuild_nexacro_plan',
                'target': 'nexacro',
                'reason': item.get('message'),
                'suggested_files': ['app/adapters/nexacro/nexacro_task_builder.py', 'app/adapters/nexacro/nexacro_validator.py'],
            })
        elif code in {'planner_emitted_code', 'json_parse_failure', 'template_file_leak'}:
            actions.append({
                'action_type': 'retry_planner_with_stricter_prompt',
                'target': 'planner',
                'reason': item.get('message'),
                'suggested_files': ['app/ui/prompt_templates.py', 'app/ui/json_validator.py'],
            })
        elif code == 'feature_kind_mismatch':
            actions.append({
                'action_type': 'recompute_feature_kind_and_revalidate',
                'target': 'analysis',
                'reason': item.get('message'),
                'suggested_files': ['app/engine/analysis/domain_classifier.py', 'app/engine/analysis/artifact_planner.py'],
            })
        elif code in {'duplicate_path', 'auth_crud_mix'}:
            actions.append({
                'action_type': 'repair_targeted_files_only',
                'target': item.get('target') or 'general',
                'reason': item.get('message'),
                'suggested_files': [],
            })

    return {
        'ok': validation_report.get('ok', False),
        'repair_mode': 'targeted' if actions else 'none',
        'actions': actions,
        'notes': [
            'Prefer targeted regeneration over full regeneration.',
            'Auth/login domains must not expand into generic CRUD during repair.',
            'Keep backend/frontend roots separated during repair.',
        ],
    }


def repair_plan_to_prompt_text(repair_plan: Dict[str, Any] | None) -> str:
    if not repair_plan:
        return ''
    actions = repair_plan.get('actions') or []
    lines = ['[AUTO REPAIR PLAN - SOURCE OF TRUTH]']
    lines.append(f"- repair_mode: {repair_plan.get('repair_mode') or 'none'}")
    if not actions:
        lines.append('- actions: (none)')
        return "\n".join(lines)
    lines.append('- actions:')
    for action in actions:
        lines.append(
            f"  - {action.get('action_type')}: target={action.get('target')}, reason={action.get('reason')}"
        )
        sfiles = action.get('suggested_files') or []
        if sfiles:
            lines.append(f"    suggested_files={', '.join(sfiles)}")
    for note in repair_plan.get('notes') or []:
        lines.append(f'- note: {note}')
    return "\n".join(lines)
