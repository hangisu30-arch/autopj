from __future__ import annotations

from typing import Any, Dict, List

from app.engine.analysis.ir_support import get_access_policy, get_auth_sensitive_fields, get_backend_artifacts, get_ui_policy, get_domain_meta, get_allowed_ui_fields, get_forbidden_ui_fields, get_generation_metadata_fields
from .backend_contracts import BackendArtifact, BackendDomainPlan, BackendPlanResult


class BackendTaskBuilder:
    def build(self, analysis_result: Dict[str, Any]) -> BackendPlanResult:
        project = analysis_result.get('project') or {}
        frontend_mode = (project.get('frontend_mode') or 'jsp').strip().lower()
        controller_mode = self._controller_mode(frontend_mode)
        root_base_package = project.get('base_package') or 'egovframework.project'

        domains: List[BackendDomainPlan] = []
        warnings: List[str] = []

        for raw_domain in analysis_result.get('domains') or []:
            naming = raw_domain.get('naming') or {}
            domain_name = raw_domain.get('name') or 'domain'
            entity_name = raw_domain.get('entity_name') or naming.get('entity_name') or domain_name.title()
            feature_kind = raw_domain.get('feature_kind') or 'crud'
            access_policy = get_access_policy(raw_domain)
            ui_policy = get_ui_policy(raw_domain)
            domain_plan = BackendDomainPlan(
                domain_name=domain_name,
                entity_name=entity_name,
                feature_kind=feature_kind,
                controller_mode=controller_mode,
                source_table=raw_domain.get('source_table') or domain_name,
                primary_key=raw_domain.get('primary_key') or '',
                primary_key_column=raw_domain.get('primary_key_column') or '',
                base_package=root_base_package,
                artifacts=self._build_domain_artifacts(raw_domain, naming, frontend_mode, root_base_package),
                forbidden_methods=self._forbidden_methods(feature_kind),
                access_mode=access_policy.get('mode') or 'shared',
                owner_field_candidates=list(access_policy.get('ownerFieldCandidates') or ui_policy.get('ownerFieldCandidates') or []),
                role_field_candidates=list(access_policy.get('roleFieldCandidates') or ui_policy.get('roleFieldCandidates') or []),
                auth_sensitive_fields=get_auth_sensitive_fields(raw_domain),
            )
            if not domain_plan.artifacts:
                warnings.append(f'No backend artifacts computed for domain={domain_name}')
            domains.append(domain_plan)

        return BackendPlanResult(
            project_name=project.get('project_name') or 'project',
            base_package=root_base_package,
            backend_mode=project.get('backend_mode') or 'egov_spring',
            frontend_mode=frontend_mode,
            database_type=project.get('database_type') or 'mysql',
            template_managed_files=['pom.xml', 'mvnw', 'mvnw.cmd', '.mvn/wrapper/maven-wrapper.properties', 'src/main/resources/application.properties'],
            domains=domains,
            warnings=warnings,
        )

    def _build_domain_artifacts(self, raw_domain: Dict[str, Any], naming: Dict[str, Any], frontend_mode: str, root_base_package: str) -> List[BackendArtifact]:
        feature_kind = raw_domain.get('feature_kind') or 'crud'
        controller_mode = self._controller_mode(frontend_mode)
        entity_name = raw_domain.get('entity_name') or naming.get('entity_name') or 'Domain'
        domain_name = raw_domain.get('name') or 'domain'
        ir_backend = get_backend_artifacts(raw_domain)

        def artifact(artifact_type: str, target_path: str, purpose: str, class_name: str = '', package: str = '') -> BackendArtifact:
            return BackendArtifact(
                artifact_type=artifact_type,
                target_path=target_path,
                purpose=purpose,
                class_name=class_name,
                package=package,
                controller_mode=controller_mode if artifact_type == 'controller' else '',
            )

        artifacts: List[BackendArtifact] = []
        if naming:
            vo_class = ir_backend.get('vo') or naming.get('vo_class_name', f'{entity_name}VO')
            mapper_class = ir_backend.get('mapperInterface') or naming.get('mapper_class_name', f'{entity_name}Mapper')
            service_class = ir_backend.get('service') or naming.get('service_class_name', f'{entity_name}Service')
            service_impl_class = ir_backend.get('serviceImpl') or naming.get('service_impl_class_name', f'{entity_name}ServiceImpl')
            controller_class = ir_backend.get('controller') or naming.get('controller_class_name', f'{entity_name}Controller')
            vo_path = ir_backend.get('voPath') or self._java_path(naming.get('vo_package', ''), vo_class)
            mapper_path = ir_backend.get('mapperPath') or self._java_path(naming.get('mapper_package', ''), mapper_class)
            mapper_xml_path = ir_backend.get('mapperXmlPath') or self._mapper_xml_path(domain_name, mapper_class)
            service_path = ir_backend.get('servicePath') or self._java_path(naming.get('service_package', ''), service_class)
            service_impl_path = ir_backend.get('serviceImplPath') or self._java_path(naming.get('service_impl_package', ''), service_impl_class)
            controller_path = ir_backend.get('controllerPath') or self._java_path(naming.get('web_package', ''), controller_class)

            artifacts.append(artifact('vo', vo_path, f'{entity_name} VO', vo_class, naming.get('vo_package', '')))
            artifacts.append(artifact('mapper', mapper_path, f'{entity_name} MyBatis mapper interface', mapper_class, naming.get('mapper_package', '')))
            artifacts.append(artifact('mapper_xml', mapper_xml_path, f'{entity_name} MyBatis mapper XML'))
            artifacts.append(artifact('service', service_path, f'{entity_name} service interface', service_class, naming.get('service_package', '')))
            artifacts.append(artifact('service_impl', service_impl_path, f'{entity_name} service implementation', service_impl_class, naming.get('service_impl_package', '')))
            artifacts.append(artifact('controller', controller_path, f'{entity_name} {controller_mode} backend controller', controller_class, naming.get('web_package', '')))

            config_package = f'{root_base_package}.config' if root_base_package else ''
            if config_package:
                artifacts.append(artifact('mybatis_config', self._java_path(config_package, 'MyBatisConfig'), 'MyBatis mapper scan configuration', 'MyBatisConfig', config_package))

        if feature_kind == 'auth':
            for item in artifacts:
                if item.artifact_type == 'controller':
                    item.purpose = f'{entity_name} auth controller (login/logout only, no generic CRUD)'
                elif item.artifact_type == 'mapper_xml':
                    item.purpose = f'{entity_name} auth query mapper XML (login lookup only)'

        return self._dedupe_artifacts(artifacts)

    @staticmethod
    def _java_path(package: str, class_name: str) -> str:
        pkg_path = package.replace('.', '/').strip('/')
        return f'src/main/java/{pkg_path}/{class_name}.java'

    @staticmethod
    def _mapper_xml_path(domain_name: str, mapper_class_name: str) -> str:
        return f'src/main/resources/egovframework/mapper/{domain_name}/{mapper_class_name}.xml'

    @staticmethod
    def _dedupe_artifacts(artifacts: List[BackendArtifact]) -> List[BackendArtifact]:
        deduped: List[BackendArtifact] = []
        seen = set()
        for artifact in artifacts:
            key = (artifact.artifact_type, artifact.target_path)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(artifact)
        return deduped

    @staticmethod
    def _forbidden_methods(feature_kind: str) -> List[str]:
        if feature_kind == 'auth':
            return ['list', 'detail', 'save', 'delete', 'insert', 'update']
        if feature_kind == 'dashboard':
            return ['save', 'delete', 'insert', 'update']
        return []

    @staticmethod
    def _controller_mode(frontend_mode: str) -> str:
        frontend_mode = (frontend_mode or '').lower()
        if frontend_mode == 'jsp':
            return 'mvc_controller'
        if frontend_mode == 'nexacro':
            return 'nexacro_controller'
        return 'rest_controller'
