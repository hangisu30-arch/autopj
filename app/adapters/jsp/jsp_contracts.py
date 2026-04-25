from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class JspViewArtifact:
    artifact_type: str
    target_path: str
    view_name: str
    purpose: str
    required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class JspDomainPlan:
    domain_name: str
    entity_name: str
    feature_kind: str
    controller_class_name: str
    controller_package: str
    source_table: str = ""
    primary_key: str = ""
    model_attribute_name: str = ""
    base_view_dir: str = ""
    views: List[JspViewArtifact] = field(default_factory=list)
    forbidden_views: List[str] = field(default_factory=list)
    access_mode: str = 'shared'
    owner_field_candidates: List[str] = field(default_factory=list)
    role_field_candidates: List[str] = field(default_factory=list)
    auth_sensitive_fields: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["views"] = [v.to_dict() for v in self.views]
        return data


@dataclass
class JspPlanResult:
    project_name: str
    base_package: str
    frontend_mode: str
    view_root: str = "src/main/webapp/WEB-INF/views"
    domains: List[JspDomainPlan] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "base_package": self.base_package,
            "frontend_mode": self.frontend_mode,
            "view_root": self.view_root,
            "domains": [d.to_dict() for d in self.domains],
            "warnings": list(self.warnings),
        }
