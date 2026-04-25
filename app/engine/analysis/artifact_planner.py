from __future__ import annotations

from .analysis_result import DomainAnalysis


class ArtifactPlanner:
    def apply(self, domain: DomainAnalysis, frontend_mode: str) -> DomainAnalysis:
        ir = domain.ir or {}
        classification = ir.get('classification') or {}
        contracts = domain.contracts or ir.get('contracts') or {}
        feature_types = [str(item or '').strip().lower() for item in (domain.feature_types or classification.get('featureTypes') or [domain.feature_kind]) if str(item or '').strip()]
        primary_pattern = (classification.get('primaryPattern') or domain.feature_kind or 'crud').strip().lower()
        frontend_mode = (frontend_mode or '').lower().strip()

        if 'auth' in feature_types or primary_pattern == 'auth':
            self._apply_auth_plan(domain, frontend_mode)
        elif primary_pattern == 'calendar':
            self._apply_calendar_plan(domain, frontend_mode, contracts)
        elif 'dashboard' in feature_types or primary_pattern == 'dashboard':
            self._apply_dashboard_plan(domain, frontend_mode, contracts)
        elif 'report' in feature_types:
            self._apply_report_plan(domain, frontend_mode, contracts)
        elif 'readonly' in feature_types:
            self._apply_readonly_plan(domain, frontend_mode, contracts)
        else:
            self._apply_crud_like_plan(domain, frontend_mode, contracts)

        return domain

    def _apply_auth_plan(self, domain: DomainAnalysis, frontend_mode: str) -> None:
        domain.pages = ['login']
        domain.api_endpoints = [
            'POST /api/auth/login',
            'POST /api/auth/logout',
        ]
        domain.forbidden_artifacts = [
            'generic_list', 'generic_detail', 'generic_delete', 'generic_crud_mapper_xml_bundle',
        ]
        domain.file_generation_plan = {
            'backend': ['vo', 'service', 'service_impl', 'controller'],
            'frontend': self._auth_frontend_plan(frontend_mode),
            'common': ['mybatis_config'],
        }
        domain.artifact_manifest = self._manifest(domain, frontend_mode, ['vo', 'service', 'service_impl', 'controller', 'mybatis_config'], self._auth_frontend_plan(frontend_mode))

    def _apply_calendar_plan(self, domain: DomainAnalysis, frontend_mode: str, contracts: dict) -> None:
        base_api = f"/api/{domain.name}"
        pages = ['calendar', 'detail', 'form']
        if contracts.get('search', {}).get('enabled'):
            pages.append('search')
        domain.pages = pages
        domain.api_endpoints = [
            f'GET {base_api}/calendar',
            f'GET {base_api}/date',
            f'GET {base_api}/{{id}}',
            f'POST {base_api}',
            f'PUT {base_api}/{{id}}',
            f'DELETE {base_api}/{{id}}',
        ]
        domain.forbidden_artifacts = ['generic_table_main_screen']
        backend = ['vo', 'mapper', 'mapper_xml', 'service', 'service_impl', 'controller', 'calendar_query']
        frontend = self._schedule_frontend_plan(frontend_mode)
        domain.file_generation_plan = {
            'backend': backend,
            'frontend': frontend,
            'common': ['mybatis_config'],
        }
        domain.artifact_manifest = self._manifest(domain, frontend_mode, backend + ['mybatis_config'], frontend)

    def _apply_dashboard_plan(self, domain: DomainAnalysis, frontend_mode: str, contracts: dict) -> None:
        base_api = f"/api/{domain.name}"
        domain.pages = ['dashboard', 'detail']
        if contracts.get('search', {}).get('enabled'):
            domain.pages.append('search')
        domain.api_endpoints = [f'GET {base_api}', f'GET {base_api}/detail']
        domain.forbidden_artifacts = ['generic_form', 'generic_delete']
        backend = ['vo', 'mapper', 'mapper_xml', 'service', 'service_impl', 'controller', 'dashboard_query']
        frontend = self._dashboard_frontend_plan(frontend_mode)
        domain.file_generation_plan = {
            'backend': backend,
            'frontend': frontend,
            'common': ['mybatis_config'],
        }
        domain.artifact_manifest = self._manifest(domain, frontend_mode, backend + ['mybatis_config'], frontend)

    def _apply_report_plan(self, domain: DomainAnalysis, frontend_mode: str, contracts: dict) -> None:
        base_api = f'/api/{domain.name}'
        domain.pages = ['report', 'detail']
        domain.api_endpoints = [f'GET {base_api}/report', f'GET {base_api}/detail']
        domain.forbidden_artifacts = ['generic_delete']
        backend = ['vo', 'mapper', 'mapper_xml', 'service', 'service_impl', 'controller', 'report_query']
        frontend = self._report_frontend_plan(frontend_mode)
        domain.file_generation_plan = {
            'backend': backend,
            'frontend': frontend,
            'common': ['mybatis_config'],
        }
        domain.artifact_manifest = self._manifest(domain, frontend_mode, backend + ['mybatis_config'], frontend)

    def _apply_readonly_plan(self, domain: DomainAnalysis, frontend_mode: str, contracts: dict) -> None:
        base_api = f'/api/{domain.name}'
        domain.pages = ['list', 'detail']
        if contracts.get('search', {}).get('enabled'):
            domain.pages.append('search')
        domain.api_endpoints = [f'GET {base_api}', f'GET {base_api}/{{id}}']
        domain.forbidden_artifacts = ['generic_form', 'generic_delete']
        backend = ['vo', 'mapper', 'mapper_xml', 'service', 'service_impl', 'controller']
        frontend = self._readonly_frontend_plan(frontend_mode)
        domain.file_generation_plan = {
            'backend': backend,
            'frontend': frontend,
            'common': ['mybatis_config'],
        }
        domain.artifact_manifest = self._manifest(domain, frontend_mode, backend + ['mybatis_config'], frontend)

    def _apply_crud_like_plan(self, domain: DomainAnalysis, frontend_mode: str, contracts: dict) -> None:
        domain.pages = ['list', 'detail', 'form']
        if contracts.get('search', {}).get('enabled'):
            domain.pages.append('search')
        base_api = f'/api/{domain.name}'
        pk_path = '/{id}'

        domain.api_endpoints = [
            f'GET {base_api}', f'GET {base_api}{pk_path}', f'POST {base_api}', f'PUT {base_api}{pk_path}', f'DELETE {base_api}{pk_path}',
        ]
        backend = ['vo', 'mapper', 'mapper_xml', 'service', 'service_impl', 'controller']
        if contracts.get('attachment', {}).get('enabled'):
            backend.append('file_handler')
        frontend = self._crud_frontend_plan(frontend_mode)
        domain.file_generation_plan = {
            'backend': backend,
            'frontend': frontend,
            'common': ['mybatis_config'],
        }
        domain.artifact_manifest = self._manifest(domain, frontend_mode, backend + ['mybatis_config'], frontend)

    def _manifest(self, domain: DomainAnalysis, frontend_mode: str, backend_types: list[str], frontend_types: list[str]) -> dict:
        return {
            'backend': [
                {'artifact_type': artifact_type, 'required': True, 'domain': domain.name}
                for artifact_type in self._dedupe(backend_types)
            ],
            'frontend': [
                {'artifact_type': artifact_type, 'required': True, 'domain': domain.name, 'frontend_mode': frontend_mode}
                for artifact_type in self._dedupe(frontend_types)
            ],
            'common': [
                {'artifact_type': 'analysis_contract', 'required': True, 'domain': domain.name},
            ],
        }

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        out: list[str] = []
        seen = set()
        for value in values:
            if value and value not in seen:
                seen.add(value)
                out.append(value)
        return out

    @staticmethod
    def _crud_frontend_plan(frontend_mode: str) -> list[str]:
        if frontend_mode == 'jsp':
            return ['list_jsp', 'detail_jsp', 'form_jsp']
        if frontend_mode == 'react':
            return ['page_list', 'page_detail', 'page_form', 'api', 'route']
        if frontend_mode == 'vue':
            return ['view_list', 'view_detail', 'view_form', 'api', 'route']
        if frontend_mode == 'nexacro':
            return ['dataset', 'transaction', 'form']
        return []

    @staticmethod
    def _schedule_frontend_plan(frontend_mode: str) -> list[str]:
        if frontend_mode == 'jsp':
            return ['calendar_jsp', 'detail_jsp', 'form_jsp']
        if frontend_mode == 'react':
            return ['page_calendar', 'page_detail', 'page_form', 'api', 'route']
        if frontend_mode == 'vue':
            return ['view_calendar', 'view_detail', 'view_form', 'api', 'route']
        if frontend_mode == 'nexacro':
            return ['calendar_form', 'detail_form', 'edit_form', 'transaction']
        return []

    @staticmethod
    def _dashboard_frontend_plan(frontend_mode: str) -> list[str]:
        if frontend_mode == 'jsp':
            return ['dashboard_jsp', 'detail_jsp']
        if frontend_mode == 'react':
            return ['page_dashboard', 'page_detail', 'api', 'route']
        if frontend_mode == 'vue':
            return ['view_dashboard', 'view_detail', 'api', 'route']
        if frontend_mode == 'nexacro':
            return ['dashboard_form', 'detail_form', 'transaction']
        return []

    @staticmethod
    def _report_frontend_plan(frontend_mode: str) -> list[str]:
        if frontend_mode == 'jsp':
            return ['report_jsp', 'detail_jsp']
        if frontend_mode == 'react':
            return ['page_report', 'page_detail', 'api', 'route']
        if frontend_mode == 'vue':
            return ['view_report', 'view_detail', 'api', 'route']
        if frontend_mode == 'nexacro':
            return ['report_form', 'detail_form', 'transaction']
        return []

    @staticmethod
    def _readonly_frontend_plan(frontend_mode: str) -> list[str]:
        if frontend_mode == 'jsp':
            return ['list_jsp', 'detail_jsp']
        if frontend_mode == 'react':
            return ['page_list', 'page_detail', 'api', 'route']
        if frontend_mode == 'vue':
            return ['view_list', 'view_detail', 'api', 'route']
        if frontend_mode == 'nexacro':
            return ['dataset', 'detail_form', 'transaction']
        return []

    @staticmethod
    def _auth_frontend_plan(frontend_mode: str) -> list[str]:
        if frontend_mode == 'jsp':
            return ['login_jsp']
        if frontend_mode == 'react':
            return ['login_page', 'auth_api', 'route_guard']
        if frontend_mode == 'vue':
            return ['login_view', 'auth_api', 'route_guard']
        if frontend_mode == 'nexacro':
            return ['login_form', 'transaction']
        return []
