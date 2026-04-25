from __future__ import annotations

from typing import Any, Dict

from app.engine.analysis.ir_support import get_frontend_artifacts, get_main_entry, get_primary_pattern
from .nexacro_contracts import NexacroArtifact, NexacroDomainPlan, NexacroPlanResult


class NexacroTaskBuilder:
    def build(self, analysis_result: Dict[str, Any], backend_plan: Dict[str, Any] | None = None) -> NexacroPlanResult:
        project = analysis_result.get('project') or {}
        frontend_mode = (project.get('frontend_mode') or '').strip().lower()
        result = NexacroPlanResult(
            project_name=project.get('project_name') or 'project',
            frontend_mode=frontend_mode,
            scaffold_files=[
                'frontend/nexacro/Application_Desktop.xadl', 'frontend/nexacro/frame/MainFrame.xfdl', 'frontend/nexacro/frame/LeftFrame.xfdl',
                'frontend/nexacro/frame/WorkFrame.xfdl', 'frontend/nexacro/services/service-url-map.json', 'frontend/nexacro/_extlib_/environment.xml',
            ],
            domains=[],
            warnings=[],
        )

        if frontend_mode != 'nexacro':
            result.warnings.append('frontend_mode is not nexacro; nexacro plan intentionally empty')
            return result

        backend_domain_map = {(d.get('domain_name') or '').strip(): d for d in (backend_plan or {}).get('domains') or []}

        for domain in analysis_result.get('domains') or []:
            domain_name = (domain.get('name') or 'domain').strip()
            entity_name = (domain.get('entity_name') or domain_name.title()).strip()
            feature_kind = (domain.get('feature_kind') or 'crud').strip().lower()
            primary_pattern = get_primary_pattern(domain)
            fields = domain.get('fields') or []
            pk_name = (domain.get('primary_key') or 'id').strip() or 'id'
            dataset_prefix = _dataset_prefix(domain_name)
            transaction_service_id = f'{domain_name}.service'
            form_dir = f'frontend/nexacro/{domain_name}'
            ir_front = get_frontend_artifacts(domain)
            ir_main = get_main_entry(domain)
            service_script_path = ir_front.get('serviceScript') or f'{form_dir}/{entity_name}Service.xjs'
            backend_domain = backend_domain_map.get(domain_name, {})
            api_prefix = (backend_domain.get('api_base_path') or f'/api/{domain_name}').strip()

            if feature_kind == 'auth':
                login_path = ir_main.get('form') or f'{form_dir}/LoginForm.xfdl'
                artifacts = [
                    NexacroArtifact('login_form', login_path, f'{entity_name} login screen for Nexacro', dataset_name=f'{dataset_prefix}Login', service_id='auth.login', route_hint='/login'),
                    NexacroArtifact('transaction_script', service_script_path, f'{entity_name} auth transaction wrapper', dataset_name=f'{dataset_prefix}Login', service_id='auth.login'),
                    NexacroArtifact('dataset_schema', f'{form_dir}/{entity_name}LoginDataset.json', f'{entity_name} login dataset metadata', dataset_name=f'{dataset_prefix}Login'),
                ]
                forbidden = ['list_form', 'detail_form', 'edit_form', 'generic_crud_transaction']
            else:
                list_dataset = f'{dataset_prefix}List'
                detail_dataset = f'{dataset_prefix}Detail'
                form_dataset = f'{dataset_prefix}Form'
                main_form = ir_front.get('mainForm') or f'{form_dir}/{entity_name}List.xfdl'
                detail_form = ir_front.get('detailForm') or f'{form_dir}/{entity_name}Detail.xfdl'
                edit_form = ir_front.get('editForm') or f'{form_dir}/{entity_name}Form.xfdl'
                main_purpose = f'{entity_name} calendar form' if primary_pattern == 'calendar' else f'{entity_name} list form'
                artifacts = [
                    NexacroArtifact('list_form', main_form, main_purpose, dataset_name=list_dataset, service_id=f'{domain_name}.list', route_hint=ir_main.get('route') or f'/{domain_name}'),
                    NexacroArtifact('detail_form', detail_form, f'{entity_name} detail form', dataset_name=detail_dataset, service_id=f'{domain_name}.detail', route_hint=f'/{domain_name}/detail'),
                    NexacroArtifact('edit_form', edit_form, f'{entity_name} create and edit form', dataset_name=form_dataset, service_id=f'{domain_name}.save', route_hint=f'/{domain_name}/form'),
                    NexacroArtifact('transaction_script', service_script_path, f'{entity_name} transaction wrapper script', dataset_name=form_dataset, service_id=transaction_service_id),
                    NexacroArtifact('dataset_schema', f'{form_dir}/{entity_name}Dataset.json', f'{entity_name} dataset metadata from schema', dataset_name=form_dataset, service_id=transaction_service_id),
                ]
                if fields:
                    artifacts.append(NexacroArtifact('dataset_columns', f'{form_dir}/{entity_name}Columns.json', f'{entity_name} dataset columns and pk={pk_name}', dataset_name=form_dataset, service_id=transaction_service_id))
                forbidden = []

            result.domains.append(
                NexacroDomainPlan(
                    domain_name=domain_name,
                    entity_name=entity_name,
                    feature_kind=feature_kind,
                    api_prefix=api_prefix,
                    form_dir=form_dir,
                    service_script_path=service_script_path,
                    dataset_prefix=dataset_prefix,
                    transaction_service_id=transaction_service_id,
                    artifacts=artifacts,
                    forbidden_artifacts=forbidden,
                )
            )

        return result


def _dataset_prefix(domain_name: str) -> str:
    token = ''.join(ch for ch in domain_name.title() if ch.isalnum()) or 'Domain'
    return f'ds{token}'
