from __future__ import annotations

from typing import Any, Dict, List, Tuple


def validate_nexacro_plan(plan: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(plan, dict):
        return False, ['nexacro plan must be a dict']

    frontend_mode = (plan.get('frontend_mode') or '').strip().lower()
    app_root = (plan.get('app_root') or '').strip()
    if frontend_mode and frontend_mode != 'nexacro':
        errors.append(f'invalid nexacro frontend_mode: {frontend_mode}')
    if app_root and not app_root.startswith('frontend/nexacro'):
        errors.append('nexacro app_root must start with frontend/nexacro')

    for key in ['service_url_map_path', 'application_config_path', 'environment_path']:
        val = (plan.get(key) or '').strip()
        if val and not val.startswith('frontend/nexacro'):
            errors.append(f'invalid nexacro root for {key}: {val}')

    seen_paths = set()
    for domain in plan.get('domains') or []:
        domain_name = (domain.get('domain_name') or '').strip() or 'domain'
        feature_kind = (domain.get('feature_kind') or 'crud').strip().lower()
        form_dir = (domain.get('form_dir') or '').strip()
        service_script_path = (domain.get('service_script_path') or '').strip()
        dataset_prefix = (domain.get('dataset_prefix') or '').strip()
        artifacts = domain.get('artifacts') or []
        forbidden = set(domain.get('forbidden_artifacts') or [])

        if form_dir and not form_dir.startswith('frontend/nexacro/'):
            errors.append(f'{domain_name}: invalid form_dir: {form_dir}')
        if service_script_path and not service_script_path.startswith('frontend/nexacro/'):
            errors.append(f'{domain_name}: invalid service_script_path: {service_script_path}')
        if service_script_path and not service_script_path.endswith('.xjs'):
            errors.append(f'{domain_name}: invalid service_script_path extension: {service_script_path}')
        if dataset_prefix and not dataset_prefix.startswith('ds'):
            errors.append(f'{domain_name}: invalid dataset_prefix: {dataset_prefix}')

        artifact_types = {a.get('artifact_type') for a in artifacts}
        if feature_kind == 'auth':
            required = {'login_form', 'transaction_script', 'dataset_schema'}
            if not required.issubset(artifact_types):
                errors.append(f'{domain_name}: missing auth nexacro artifacts')
            if not {'list_form', 'detail_form', 'edit_form'}.issubset(forbidden):
                errors.append(f'{domain_name}: auth domain missing forbidden nexacro CRUD artifacts')
        else:
            required = {'list_form', 'detail_form', 'edit_form', 'transaction_script', 'dataset_schema'}
            if not required.issubset(artifact_types):
                errors.append(f'{domain_name}: missing nexacro artifacts')

        for artifact in artifacts:
            target = (artifact.get('target_path') or '').strip()
            artifact_type = (artifact.get('artifact_type') or '').strip()
            if not target.startswith('frontend/nexacro/'):
                errors.append(f'{domain_name}: invalid nexacro artifact root: {target}')
            if artifact_type.endswith('_form') and not target.endswith('.xfdl'):
                errors.append(f'{domain_name}: form artifact must end with .xfdl: {target}')
            if artifact_type == 'transaction_script' and not target.endswith('.xjs'):
                errors.append(f'{domain_name}: transaction script must end with .xjs: {target}')
            if artifact_type.startswith('dataset_') and not target.endswith('.json'):
                errors.append(f'{domain_name}: dataset artifact must end with .json: {target}')
            if target in seen_paths:
                errors.append(f'duplicate path detected in nexacro plan: {target}')
            seen_paths.add(target)
            if '/src/' in target or 'WEB-INF/views' in target:
                errors.append(f'{domain_name}: jsp/react/vue path leaked into nexacro plan: {target}')

    return len(errors) == 0, errors
