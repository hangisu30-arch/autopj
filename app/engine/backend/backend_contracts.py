from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class BackendArtifact:
    artifact_type: str
    target_path: str
    purpose: str
    class_name: str = ""
    package: str = ""
    controller_mode: str = ""
    required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BackendDomainPlan:
    domain_name: str
    entity_name: str
    feature_kind: str
    controller_mode: str
    source_table: str = ""
    primary_key: str = ""
    primary_key_column: str = ""
    base_package: str = ""
    artifacts: List[BackendArtifact] = field(default_factory=list)
    forbidden_methods: List[str] = field(default_factory=list)
    access_mode: str = 'shared'
    owner_field_candidates: List[str] = field(default_factory=list)
    role_field_candidates: List[str] = field(default_factory=list)
    auth_sensitive_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["artifacts"] = [artifact.to_dict() for artifact in self.artifacts]
        return data


@dataclass
class BackendPlanResult:
    project_name: str
    base_package: str
    backend_mode: str
    frontend_mode: str
    database_type: str
    template_managed_files: List[str] = field(default_factory=list)
    domains: List[BackendDomainPlan] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "base_package": self.base_package,
            "backend_mode": self.backend_mode,
            "frontend_mode": self.frontend_mode,
            "database_type": self.database_type,
            "template_managed_files": list(self.template_managed_files),
            "domains": [domain.to_dict() for domain in self.domains],
            "warnings": list(self.warnings),
        }
