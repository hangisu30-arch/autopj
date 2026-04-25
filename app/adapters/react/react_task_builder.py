from __future__ import annotations

from typing import Any, Dict, List

from app.engine.analysis.ir_support import get_access_policy, get_auth_sensitive_fields, get_frontend_artifacts, get_main_entry, get_primary_pattern, get_ui_policy, get_domain_meta, get_allowed_ui_fields, get_forbidden_ui_fields, get_generation_metadata_fields
from .react_contracts import ReactArtifact, ReactDomainPlan, ReactPlanResult


class ReactTaskBuilder:
    def build(self, analysis_result: Dict[str, Any], backend_plan: Dict[str, Any] | None = None) -> ReactPlanResult:
        project = analysis_result.get('project') or {}
        frontend_mode = (project.get('frontend_mode') or '').strip().lower()
        result = ReactPlanResult(
            project_name=project.get('project_name') or 'project',
            frontend_mode=frontend_mode,
            scaffold_files=[
                'frontend/react/package.json', 'frontend/react/vite.config.js', 'frontend/react/index.html',
                'frontend/react/src/main.jsx', 'frontend/react/src/App.jsx', 'frontend/react/src/routes/index.jsx',
                'frontend/react/src/constants/routes.js', 'frontend/react/src/api/client.js',
            ],
            domains=[],
            warnings=[],
        )

        if frontend_mode != 'react':
            result.warnings.append('frontend_mode is not react; react plan intentionally empty')
            return result

        for domain in analysis_result.get('domains') or []:
            domain_meta = get_domain_meta(domain)
            domain_name = (domain_meta.get('canonicalCamel') or domain.get('name') or 'domain').strip()
            entity_name = (domain_meta.get('canonicalPascal') or domain.get('entity_name') or domain_name.title()).strip()
            feature_kind = (domain.get('feature_kind') or 'crud').strip().lower()
            primary_pattern = get_primary_pattern(domain)
            ir_front = get_frontend_artifacts(domain)
            ir_main = get_main_entry(domain)
            access_policy = get_access_policy(domain)
            ui_policy = get_ui_policy(domain)

            page_dir = f'frontend/react/src/pages/{domain_name}'
            service_path = ir_front.get('apiService') or f'frontend/react/src/api/services/{domain_name}.js'
            route_key = _route_constant_key(domain_name)

            if feature_kind == 'auth':
                route_base_path = '/login'
                login_path = ir_main.get('page') or f'{page_dir}/LoginPage.jsx'
                artifacts = [
                    ReactArtifact('login_page', login_path, f'{entity_name} login page', route_path=route_base_path, component_name='LoginPage', import_path=f'@/pages/{domain_name}/LoginPage'),
                    ReactArtifact('auth_api', service_path, f'{entity_name} auth API service'),
                    ReactArtifact('route_guard', 'frontend/react/src/routes/RouteGuard.jsx', 'Shared authenticated route guard component', component_name='RouteGuard', import_path='@/routes/RouteGuard'),
                ]
                forbidden = ['page_list', 'page_detail', 'page_form', 'generic_crud_service']
            else:
                route_base_path = ir_main.get('route') or f'/{domain_name}'
                main_page = ir_front.get('mainPage') or f'{page_dir}/{entity_name}ListPage.jsx'
                detail_page = ir_front.get('detailPage') or f'{page_dir}/{entity_name}DetailPage.jsx'
                form_page = ir_front.get('formPage') or f'{page_dir}/{entity_name}FormPage.jsx'
                main_purpose = f'{entity_name} calendar main page' if primary_pattern == 'calendar' else f'{entity_name} list page'
                main_component = main_page.rsplit('/', 1)[-1].replace('.jsx', '')
                detail_component = detail_page.rsplit('/', 1)[-1].replace('.jsx', '')
                form_component = form_page.rsplit('/', 1)[-1].replace('.jsx', '')
                artifacts = [
                    ReactArtifact('page_list', main_page, main_purpose, route_path=route_base_path, component_name=main_component, import_path=f'@/pages/{domain_name}/{main_component}'),
                    ReactArtifact('page_form', form_page, f'{entity_name} create/edit form page', route_path=f'{route_base_path}/create and {route_base_path}/edit/:id', component_name=form_component, import_path=f'@/pages/{domain_name}/{form_component}'),
                    ReactArtifact('page_detail', detail_page, f'{entity_name} detail page', route_path=f'{route_base_path}/:id', component_name=detail_component, import_path=f'@/pages/{domain_name}/{detail_component}'),
                    ReactArtifact('api_service', service_path, f'{entity_name} REST API service'),
                ]
                forbidden = []

            result.domains.append(
                ReactDomainPlan(
                    domain_name=domain_name,
                    entity_name=entity_name,
                    feature_kind=feature_kind,
                    api_prefix=f"/api/{domain_name if feature_kind != 'auth' else 'auth'}",
                    page_dir=page_dir,
                    service_path=service_path,
                    route_constant_key=route_key,
                    route_base_path=route_base_path,
                    artifacts=artifacts,
                    forbidden_artifacts=forbidden,
                    access_mode=access_policy.get('mode') or 'shared',
                    owner_field_candidates=list(access_policy.get('ownerFieldCandidates') or ui_policy.get('ownerFieldCandidates') or []),
                    role_field_candidates=list(access_policy.get('roleFieldCandidates') or ui_policy.get('roleFieldCandidates') or []),
                    auth_sensitive_fields=get_auth_sensitive_fields(domain),
                )
            )

        return result


def _route_constant_key(domain_name: str) -> str:
    cleaned = ''.join(ch if ch.isalnum() else '_' for ch in (domain_name or 'domain')).upper().strip('_')
    return cleaned or 'DOMAIN'
