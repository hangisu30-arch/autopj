from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.engine.analysis.ir_support import get_domain_ir, get_primary_pattern
from app.engine.backend import validate_backend_plan
from app.adapters.jsp import validate_jsp_plan
from app.adapters.react import validate_react_plan
from app.adapters.vue import validate_vue_plan
from app.adapters.nexacro import validate_nexacro_plan
from app.validation.error_classifier import classify_validation_errors


CRUD_FRONTEND_MARKERS = {
    'jsp': {'list_jsp', 'detail_jsp', 'form_jsp'},
    'react': {'page_list', 'page_detail', 'page_form'},
    'vue': {'view_list', 'view_detail', 'view_form'},
    'nexacro': {'form'},
}
CRUD_BACKEND_MARKERS = {'vo', 'mapper', 'mapper_xml', 'service', 'service_impl', 'controller'}
CRUD_PAGES = {'list', 'detail', 'form'}
CRUD_ENDPOINT_TOKENS = ('get /api/', 'post /api/', 'put /api/', 'delete /api/')
ENTRY_ONLY_DOMAINS = {'index', 'home', 'main', 'landing', 'root'}


def _domain_semantic_errors(domain: Dict[str, Any], frontend_mode: str) -> List[str]:
    errors: List[str] = []
    name = domain.get('name') or domain.get('domain_name') or 'domain'
    feature_kind = (domain.get('feature_kind') or 'crud').strip().lower()
    primary_pattern = get_primary_pattern(domain)
    files = domain.get('file_generation_plan') or {}
    front = set(files.get('frontend') or [])
    back = set(files.get('backend') or [])
    pages = {str(x).strip().lower() for x in (domain.get('pages') or []) if str(x).strip()}
    endpoints = [str(x).strip().lower() for x in (domain.get('api_endpoints') or []) if str(x).strip()]
    ir = get_domain_ir(domain)
    main_entry = ir.get('mainEntry') or {}
    validation_rules = ir.get('validationRules') or {}
    data_model = ir.get('dataModel') or {}

    crud_front_markers = CRUD_FRONTEND_MARKERS.get(frontend_mode, set())
    has_crud_front = bool(front & crud_front_markers)
    has_crud_back = bool(back & CRUD_BACKEND_MARKERS)
    has_crud_pages = bool(pages & CRUD_PAGES)
    has_crud_endpoints = any(any(token in ep for token in CRUD_ENDPOINT_TOKENS) for ep in endpoints)

    if feature_kind == 'upload' and (has_crud_front or has_crud_back or has_crud_pages or has_crud_endpoints):
        errors.append(f'{name}: feature_kind upload conflicts with CRUD pages/artifacts')
    if feature_kind == 'auth' and (has_crud_pages or has_crud_front or has_crud_endpoints):
        errors.append(f'{name}: auth feature_kind conflicts with CRUD pages/artifacts')
    if name.lower() in ENTRY_ONLY_DOMAINS:
        if has_crud_back or has_crud_pages or has_crud_front or has_crud_endpoints:
            errors.append(f'{name}: entry-only domain must not generate CRUD/service/vo artifacts')
        route = (main_entry.get('route') or '').lower()
        if route and route not in {'/', '/index', '/index.do', '/home', '/home.do'} and 'redirect:' not in route:
            errors.append(f'{name}: entry-only domain must keep landing route only')
    if primary_pattern == 'calendar':
        route = (main_entry.get('route') or '').lower()
        main_jsp = (main_entry.get('jsp') or main_entry.get('page') or main_entry.get('form') or '').lower()
        if 'calendar' not in route and 'calendar' not in main_jsp:
            errors.append(f'{name}: calendar primaryPattern missing calendar main entry')
        if 'calendar' not in pages:
            errors.append(f'{name}: calendar primaryPattern missing calendar page in legacy plan')
    hidden_fields = set(validation_rules.get('formHiddenFields') or [])
    for field in data_model.get('fields') or []:
        if field.get('name') in hidden_fields and field.get('visibleInForm'):
            errors.append(f"{name}: hidden form field leaked into dataModel -> {field.get('name')}")
    return errors


def _check_analysis(analysis_result: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(analysis_result, dict):
        return ['analysis_result must be a dict']

    project = analysis_result.get('project') or {}
    base_package = (project.get('base_package') or '').strip()
    frontend_mode = (project.get('frontend_mode') or '').strip().lower()
    domains = analysis_result.get('domains') or []
    ir_version = (analysis_result.get('ir_version') or '').strip()

    if not base_package.startswith('egovframework.'):
        errors.append('base_package must start with egovframework.')
    if not ir_version:
        errors.append('analysis_result missing ir_version')
    if not isinstance(domains, list) or not domains:
        errors.append('analysis domains must be a non-empty list')
        return errors

    for domain in domains:
        name = domain.get('name') or 'domain'
        feature_kind = (domain.get('feature_kind') or 'crud').strip().lower()
        files = domain.get('file_generation_plan') or {}
        forbidden = set(domain.get('forbidden_artifacts') or [])
        front = set(files.get('frontend') or [])
        ir = get_domain_ir(domain)
        classification = ir.get('classification') or {}
        main_entry = ir.get('mainEntry') or {}
        data_model = ir.get('dataModel') or {}
        backend_artifacts = ir.get('backendArtifacts') or {}
        frontend_artifacts = ir.get('frontendArtifacts') or {}

        if not ir:
            errors.append(f'{name}: missing domain.ir block')
        else:
            if not classification.get('primaryPattern'):
                errors.append(f'{name}: IR classification.primaryPattern is required')
            if not main_entry:
                errors.append(f'{name}: IR mainEntry is required')
            if not data_model.get('fields'):
                errors.append(f'{name}: IR dataModel.fields must not be empty')
            if not backend_artifacts:
                errors.append(f'{name}: IR backendArtifacts must not be empty')
            if not frontend_artifacts and frontend_mode:
                errors.append(f'{name}: IR frontendArtifacts must not be empty')

        if feature_kind == 'auth':
            if not {'generic_list', 'generic_detail', 'generic_delete'}.issubset(forbidden):
                errors.append(f'{name}: auth domain missing forbidden CRUD artifacts')
        if frontend_mode == 'react':
            if any(x.endswith('_jsp') for x in front):
                errors.append(f'{name}: JSP artifact leaked into react analysis plan')
        if frontend_mode == 'jsp':
            if any('page_' in x or 'api' in x or 'view_' in x for x in front):
                errors.append(f'{name}: non-jsp artifact leaked into jsp analysis plan')
        if frontend_mode == 'vue':
            if any(x.endswith('_jsp') or 'page_' in x for x in front):
                errors.append(f'{name}: non-vue artifact leaked into vue analysis plan')
        if frontend_mode == 'nexacro':
            if any(x.endswith('_jsp') or 'page_' in x or 'view_' in x or x in {'api', 'route'} for x in front):
                errors.append(f'{name}: non-nexacro artifact leaked into nexacro analysis plan')

        errors.extend(_domain_semantic_errors(domain, frontend_mode))
    return errors


def validate_generation_context(
    analysis_result: Dict[str, Any],
    backend_plan: Optional[Dict[str, Any]] = None,
    jsp_plan: Optional[Dict[str, Any]] = None,
    react_plan: Optional[Dict[str, Any]] = None,
    vue_plan: Optional[Dict[str, Any]] = None,
    nexacro_plan: Optional[Dict[str, Any]] = None,
    frontend_key: str = '',
) -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []
    all_errors: List[str] = []
    frontend_key = (frontend_key or '').strip().lower()

    analysis_errors = _check_analysis(analysis_result)
    checks.append({'name': 'analysis', 'ok': not analysis_errors, 'errors': analysis_errors})
    all_errors.extend(analysis_errors)

    if backend_plan is not None:
        ok, errors = validate_backend_plan(backend_plan)
        checks.append({'name': 'backend_plan', 'ok': ok, 'errors': errors})
        all_errors.extend(errors)

    if frontend_key == 'jsp' and jsp_plan is not None:
        ok, errors = validate_jsp_plan(jsp_plan)
        checks.append({'name': 'jsp_plan', 'ok': ok, 'errors': errors})
        all_errors.extend(errors)

    if frontend_key == 'react' and react_plan is not None:
        ok, errors = validate_react_plan(react_plan)
        checks.append({'name': 'react_plan', 'ok': ok, 'errors': errors})
        all_errors.extend(errors)

    if frontend_key == 'vue' and vue_plan is not None:
        ok, errors = validate_vue_plan(vue_plan)
        checks.append({'name': 'vue_plan', 'ok': ok, 'errors': errors})
        all_errors.extend(errors)

    if frontend_key == 'nexacro' and nexacro_plan is not None:
        ok, errors = validate_nexacro_plan(nexacro_plan)
        checks.append({'name': 'nexacro_plan', 'ok': ok, 'errors': errors})
        all_errors.extend(errors)

    classified = classify_validation_errors(all_errors)
    repairable_count = sum(1 for item in classified if item.get('repairable'))
    return {
        'ok': len(all_errors) == 0,
        'frontend_key': frontend_key,
        'checks': checks,
        'errors': all_errors,
        'classified_errors': classified,
        'repairable_error_count': repairable_count,
        'non_repairable_error_count': len(classified) - repairable_count,
        'summary': {
            'total_checks': len(checks),
            'failed_checks': sum(1 for c in checks if not c.get('ok')),
            'total_errors': len(all_errors),
        },
    }
