from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import re
import xml.etree.ElementTree as ET

from .naming_rules import normalize_project_name


@dataclass
class AnalysisContext:
    project_root: str
    project_name: str
    base_package: str
    backend_mode: str
    frontend_mode: str
    database_type: str
    requirements_text: str
    schema_text: str

    @classmethod
    def from_inputs(
        cls,
        project_root: str,
        frontend_mode: str,
        database_type: str,
        requirements_text: str,
        schema_text: str = "",
        base_package: Optional[str] = None,
        project_name: Optional[str] = None,
        backend_mode: str = "egov_spring",
    ) -> "AnalysisContext":
        root = Path(project_root)
        resolved_project_name = normalize_project_name(project_name or root.name or "project")

        pom_group_id = _read_group_id_from_pom(root / "pom.xml")
        resolved_base_package = (
            base_package.strip()
            if base_package and base_package.strip()
            else _derive_base_package(pom_group_id, resolved_project_name)
        )

        return cls(
            project_root=str(root),
            project_name=resolved_project_name,
            base_package=resolved_base_package,
            backend_mode=backend_mode,
            frontend_mode=frontend_mode.lower().strip(),
            database_type=(database_type or "mysql").lower().strip(),
            requirements_text=(requirements_text or "").strip(),
            schema_text=(schema_text or "").strip(),
        )


def _derive_base_package(group_id: Optional[str], project_name: str) -> str:
    if group_id:
        gid = group_id.strip()
        if gid.startswith("egovframework."):
            return gid
    return f"egovframework.{normalize_project_name(project_name)}"


def _read_group_id_from_pom(pom_path: Path) -> Optional[str]:
    if not pom_path.exists():
        return None

    try:
        tree = ET.parse(pom_path)
        root = tree.getroot()

        ns_match = re.match(r"\{(.+)\}", root.tag)
        ns = {"m": ns_match.group(1)} if ns_match else {}

        group_id = root.findtext("m:groupId", namespaces=ns) or root.findtext("groupId")
        if group_id:
            return group_id.strip()

        parent_group_id = root.findtext("m:parent/m:groupId", namespaces=ns) or root.findtext("parent/groupId")
        if parent_group_id:
            return parent_group_id.strip()
    except Exception:
        return None

    return None
