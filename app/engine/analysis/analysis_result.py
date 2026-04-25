from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FieldInfo:
    name: str
    column: str
    java_type: str
    db_type: str = ""
    pk: bool = False
    nullable: bool = True
    searchable: bool = False
    display: bool = False
    role: str = "business"
    editable: Optional[bool] = None
    visible_in_form: Optional[bool] = None
    visible_in_detail: Optional[bool] = None
    visible_in_list: Optional[bool] = None
    source: str = ""
    default_value: str = ""
    java_import: str = ""
    comment: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            'javaImport': self.java_import,
            'visibleInForm': self.visible_in_form,
            'visibleInDetail': self.visible_in_detail,
            'visibleInList': self.visible_in_list,
            'defaultValue': self.default_value,
        }


@dataclass
class DomainNaming:
    package_base: str
    web_package: str
    service_package: str
    service_impl_package: str
    mapper_package: str
    vo_package: str

    entity_name: str
    vo_class_name: str
    mapper_class_name: str
    service_class_name: str
    service_impl_class_name: str
    controller_class_name: str

    jsp_list_view: str = ""
    jsp_detail_view: str = ""
    jsp_form_view: str = ""

    react_list_page_path: str = ""
    react_detail_page_path: str = ""
    react_form_page_path: str = ""
    react_api_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DomainAnalysis:
    name: str
    entity_name: str
    feature_kind: str
    auth_required: bool = False

    source_table: str = ""
    primary_key: str = ""
    primary_key_column: str = ""

    pages: List[str] = field(default_factory=list)
    api_endpoints: List[str] = field(default_factory=list)
    fields: List[FieldInfo] = field(default_factory=list)

    feature_types: List[str] = field(default_factory=list)
    contracts: Dict[str, Any] = field(default_factory=dict)
    file_generation_plan: Dict[str, List[str]] = field(default_factory=dict)
    artifact_manifest: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    forbidden_artifacts: List[str] = field(default_factory=list)
    naming: Optional[DomainNaming] = None
    ir: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['fields'] = [f.to_dict() for f in self.fields]
        if self.naming:
            data['naming'] = self.naming.to_dict()
        data['ir'] = self.ir or {}
        return data


@dataclass
class ProjectAnalysis:
    project_root: str
    project_name: str
    base_package: str
    backend_mode: str
    frontend_mode: str
    database_type: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AnalysisResult:
    project: ProjectAnalysis
    requirements_text: str
    schema_text: str
    domains: List[DomainAnalysis] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    generation_policy: Dict[str, Any] = field(default_factory=dict)
    ir_version: str = '1.0'

    def to_dict(self) -> Dict[str, Any]:
        return {
            'project': self.project.to_dict(),
            'inputs': {
                'requirements_text': self.requirements_text,
                'schema_present': bool(self.schema_text.strip()),
            },
            'ir_version': self.ir_version,
            'generation_policy': self.generation_policy,
            'domains': [d.to_dict() for d in self.domains],
            'warnings': self.warnings,
        }
