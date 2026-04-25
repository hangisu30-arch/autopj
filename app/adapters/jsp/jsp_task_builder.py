from __future__ import annotations

from typing import Any, Dict, List

from app.engine.analysis.ir_support import get_access_policy, get_auth_sensitive_fields, get_frontend_artifacts, get_main_entry, get_primary_pattern, get_ui_policy, get_domain_meta, get_allowed_ui_fields, get_forbidden_ui_fields, get_generation_metadata_fields, jsp_view_name_from_path
from .jsp_contracts import JspDomainPlan, JspPlanResult, JspViewArtifact


class JspTaskBuilder:
    def build(self, analysis_result: Dict[str, Any], backend_plan: Dict[str, Any] | None = None) -> JspPlanResult:
        project = analysis_result.get('project') or {}
        frontend_mode = (project.get('frontend_mode') or '').strip().lower()
        result = JspPlanResult(
            project_name=project.get('project_name') or 'project',
            base_package=project.get('base_package') or 'egovframework.project',
            frontend_mode=frontend_mode,
            domains=[],
            warnings=[],
        )

        if frontend_mode != 'jsp':
            result.warnings.append('frontend_mode is not jsp; jsp plan intentionally empty')
            return result

        backend_domain_map = {(d.get('domain_name') or '').strip(): d for d in (backend_plan or {}).get('domains') or []}

        for domain in analysis_result.get('domains') or []:
            domain_meta = get_domain_meta(domain)
            domain_name = (domain_meta.get('canonicalCamel') or domain.get('name') or 'domain').strip()
            entity_name = (domain_meta.get('canonicalPascal') or domain.get('entity_name') or domain_name.title()).strip()
            feature_kind = (domain.get('feature_kind') or 'crud').strip().lower()
            primary_pattern = get_primary_pattern(domain)
            naming = domain.get('naming') or {}
            ir_front = get_frontend_artifacts(domain)
            ir_main = get_main_entry(domain)
            backend_domain = backend_domain_map.get(domain_name, {})
            access_policy = get_access_policy(domain)
            ui_policy = get_ui_policy(domain)

            controller_class_name = _find_controller_name(backend_domain) or naming.get('controller_class_name') or f'{entity_name}Controller'
            controller_package = _find_controller_package(backend_domain) or naming.get('web_package') or f'{result.base_package}.{domain_name}.web'
            model_attr = _model_attribute_name(entity_name)
            base_view_dir = f'src/main/webapp/WEB-INF/views/{domain_name}'

            if feature_kind == 'auth':
                login_path = ir_front.get('mainJsp') or f'{base_view_dir}/login.jsp'
                views = [
                    JspViewArtifact(
                        artifact_type='login_jsp',
                        target_path=login_path,
                        view_name=jsp_view_name_from_path(login_path),
                        purpose=f'{entity_name} login page',
                    )
                ]
                forbidden = ['list', 'detail', 'form', 'delete']
            else:
                main_path = ir_front.get('mainJsp') or (ir_main.get('jsp') and 'src/main/webapp' + ir_main.get('jsp')) or f'{base_view_dir}/{domain_name}List.jsp'
                detail_path = ir_front.get('detailJsp') or f'{base_view_dir}/{domain_name}Detail.jsp'
                form_path = ir_front.get('formJsp') or f'{base_view_dir}/{domain_name}Form.jsp'
                main_purpose = f'{entity_name} calendar main page' if primary_pattern == 'calendar' else f'{entity_name} list page'
                views = [
                    JspViewArtifact(
                        artifact_type='list_jsp',
                        target_path=main_path,
                        view_name=jsp_view_name_from_path(main_path),
                        purpose=main_purpose,
                    ),
                    JspViewArtifact(
                        artifact_type='detail_jsp',
                        target_path=detail_path,
                        view_name=jsp_view_name_from_path(detail_path),
                        purpose=f'{entity_name} detail page',
                    ),
                    JspViewArtifact(
                        artifact_type='form_jsp',
                        target_path=form_path,
                        view_name=jsp_view_name_from_path(form_path),
                        purpose=f'{entity_name} create/update form page',
                    ),
                ]
                forbidden = []

            result.domains.append(
                JspDomainPlan(
                    domain_name=domain_name,
                    entity_name=entity_name,
                    feature_kind=feature_kind,
                    controller_class_name=controller_class_name,
                    controller_package=controller_package,
                    source_table=domain.get('source_table') or domain_name,
                    primary_key=domain.get('primary_key') or '',
                    model_attribute_name=model_attr,
                    base_view_dir=base_view_dir,
                    views=views,
                    forbidden_views=forbidden,
                    access_mode=access_policy.get('mode') or 'shared',
                    owner_field_candidates=list(access_policy.get('ownerFieldCandidates') or ui_policy.get('ownerFieldCandidates') or []),
                    role_field_candidates=list(access_policy.get('roleFieldCandidates') or ui_policy.get('roleFieldCandidates') or []),
                    auth_sensitive_fields=get_auth_sensitive_fields(domain),
                )
            )

        return result


def _find_controller_name(backend_domain: Dict[str, Any]) -> str:
    for artifact in backend_domain.get('artifacts') or []:
        if artifact.get('artifact_type') == 'controller':
            return (artifact.get('class_name') or '').strip()
    return ''


def _find_controller_package(backend_domain: Dict[str, Any]) -> str:
    for artifact in backend_domain.get('artifacts') or []:
        if artifact.get('artifact_type') == 'controller':
            return (artifact.get('package') or '').strip()
    return ''


def _model_attribute_name(entity_name: str) -> str:
    cleaned = (entity_name or 'Item').strip()
    if not cleaned:
        return 'item'
    if cleaned.isupper():
        return cleaned.lower()
    return cleaned[:1].lower() + cleaned[1:]
