from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class ReactArtifact:
    artifact_type: str
    target_path: str
    purpose: str
    route_path: str = ""
    component_name: str = ""
    import_path: str = ""
    required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ReactDomainPlan:
    domain_name: str
    entity_name: str
    feature_kind: str
    api_prefix: str
    page_dir: str
    service_path: str
    route_constant_key: str
    route_base_path: str
    artifacts: List[ReactArtifact] = field(default_factory=list)
    forbidden_artifacts: List[str] = field(default_factory=list)
    access_mode: str = 'shared'
    owner_field_candidates: List[str] = field(default_factory=list)
    role_field_candidates: List[str] = field(default_factory=list)
    auth_sensitive_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["artifacts"] = [a.to_dict() for a in self.artifacts]
        return data


@dataclass
class ReactPlanResult:
    project_name: str
    frontend_mode: str
    app_root: str = "frontend/react"
    route_registry_path: str = "frontend/react/src/routes/index.jsx"
    route_constants_path: str = "frontend/react/src/constants/routes.js"
    api_client_path: str = "frontend/react/src/api/client.js"
    scaffold_files: List[str] = field(default_factory=list)
    domains: List[ReactDomainPlan] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "frontend_mode": self.frontend_mode,
            "app_root": self.app_root,
            "route_registry_path": self.route_registry_path,
            "route_constants_path": self.route_constants_path,
            "api_client_path": self.api_client_path,
            "scaffold_files": list(self.scaffold_files),
            "domains": [d.to_dict() for d in self.domains],
            "warnings": list(self.warnings),
        }
