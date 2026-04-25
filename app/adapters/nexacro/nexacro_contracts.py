from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class NexacroArtifact:
    artifact_type: str
    target_path: str
    purpose: str
    dataset_name: str = ''
    service_id: str = ''
    route_hint: str = ''
    required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NexacroDomainPlan:
    domain_name: str
    entity_name: str
    feature_kind: str
    api_prefix: str
    form_dir: str
    service_script_path: str
    dataset_prefix: str
    transaction_service_id: str
    artifacts: List[NexacroArtifact] = field(default_factory=list)
    forbidden_artifacts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['artifacts'] = [a.to_dict() for a in self.artifacts]
        return data


@dataclass
class NexacroPlanResult:
    project_name: str
    frontend_mode: str
    app_root: str = 'frontend/nexacro'
    service_url_map_path: str = 'frontend/nexacro/services/service-url-map.json'
    application_config_path: str = 'frontend/nexacro/Application_Desktop.xadl'
    environment_path: str = 'frontend/nexacro/_extlib_/environment.xml'
    scaffold_files: List[str] = field(default_factory=list)
    domains: List[NexacroDomainPlan] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'project_name': self.project_name,
            'frontend_mode': self.frontend_mode,
            'app_root': self.app_root,
            'service_url_map_path': self.service_url_map_path,
            'application_config_path': self.application_config_path,
            'environment_path': self.environment_path,
            'scaffold_files': list(self.scaffold_files),
            'domains': [d.to_dict() for d in self.domains],
            'warnings': list(self.warnings),
        }
