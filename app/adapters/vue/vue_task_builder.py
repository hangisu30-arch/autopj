from __future__ import annotations

from typing import Any, Dict

from app.engine.analysis.ir_support import get_access_policy, get_auth_sensitive_fields, get_frontend_artifacts, get_main_entry, get_primary_pattern, get_ui_policy, get_domain_meta, get_allowed_ui_fields, get_forbidden_ui_fields, get_generation_metadata_fields
from .vue_contracts import VueArtifact, VueDomainPlan, VuePlanResult


class VueTaskBuilder:
    def build(self, analysis_result: Dict[str, Any], backend_plan: Dict[str, Any] | None = None) -> VuePlanResult:
        project = analysis_result.get('project') or {}
        frontend_mode = (project.get('frontend_mode') or '').strip().lower()
        result = VuePlanResult(
            project_name=project.get('project_name') or 'project',
            frontend_mode=frontend_mode,
            scaffold_files=[
                'frontend/vue/package.json', 'frontend/vue/vite.config.js', 'frontend/vue/index.html',
                'frontend/vue/src/main.js', 'frontend/vue/src/App.vue', 'frontend/vue/src/router/index.js',
                'frontend/vue/src/constants/routes.js', 'frontend/vue/src/api/client.js', 'frontend/vue/src/stores/index.js',
            ],
            domains=[],
            warnings=[],
        )

        if frontend_mode != 'vue':
            result.warnings.append('frontend_mode is not vue; vue plan intentionally empty')
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

            view_dir = f'frontend/vue/src/views/{domain_name}'
            service_path = ir_front.get('apiService') or f'frontend/vue/src/api/{domain_name}Api.js'
            store_path = 'frontend/vue/src/stores/index.js'
            router_name = _route_name(domain_name)

            if feature_kind == 'auth':
                route_base_path = '/login'
                login_path = ir_main.get('page') or f'{view_dir}/LoginView.vue'
                artifacts = [
                    VueArtifact('login_view', login_path, f'{entity_name} login view', route_path=route_base_path, component_name='LoginView', import_path=f'@/views/{domain_name}/LoginView.vue'),
                    VueArtifact('auth_api', service_path, f'{entity_name} auth API service'),
                    VueArtifact('route_guard', 'frontend/vue/src/router/guards.js', 'Shared authenticated route guard helpers'),
                ]
                forbidden = ['view_list', 'view_detail', 'view_form', 'generic_crud_service', 'domain_store']
            else:
                route_base_path = ir_main.get('route') or f'/{domain_name}'
                main_view = ir_front.get('mainPage') or f'{view_dir}/{entity_name}List.vue'
                detail_view = ir_front.get('detailPage') or f'{view_dir}/{entity_name}Detail.vue'
                form_view = ir_front.get('formPage') or f'{view_dir}/{entity_name}Form.vue'
                main_purpose = f'{entity_name} calendar main view' if primary_pattern == 'calendar' else f'{entity_name} list view'
                main_component = main_view.rsplit('/', 1)[-1].replace('.vue', '')
                detail_component = detail_view.rsplit('/', 1)[-1].replace('.vue', '')
                form_component = form_view.rsplit('/', 1)[-1].replace('.vue', '')
                artifacts = [
                    VueArtifact('view_list', main_view, main_purpose, route_path=route_base_path, component_name=main_component, import_path=f'@/views/{domain_name}/{main_component}.vue'),
                    VueArtifact('view_form', form_view, f'{entity_name} create/edit form view', route_path=f'{route_base_path}/create and {route_base_path}/edit/:id', component_name=form_component, import_path=f'@/views/{domain_name}/{form_component}.vue'),
                    VueArtifact('view_detail', detail_view, f'{entity_name} detail view', route_path=f'{route_base_path}/detail/:id', component_name=detail_component, import_path=f'@/views/{domain_name}/{detail_component}.vue'),
                    VueArtifact('api_service', service_path, f'{entity_name} REST API service'),
                ]
                forbidden = ['domain_store']

            result.domains.append(
                VueDomainPlan(
                    domain_name=domain_name,
                    entity_name=entity_name,
                    feature_kind=feature_kind,
                    api_prefix=f"/api/{domain_name if feature_kind != 'auth' else 'auth'}",
                    view_dir=view_dir,
                    service_path=service_path,
                    store_path=store_path,
                    router_name=router_name,
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


def _route_name(domain_name: str) -> str:
    cleaned = ''.join(ch if ch.isalnum() else '-' for ch in (domain_name or 'domain')).strip('-')
    parts = [p for p in cleaned.split('-') if p]
    return ''.join(p[:1].upper() + p[1:] for p in parts) or 'Domain'
