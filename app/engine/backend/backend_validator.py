from __future__ import annotations

from typing import Any, Dict, List, Tuple


CRUD_BACKEND_ARTIFACTS = {"vo", "mapper", "mapper_xml", "service", "service_impl", "controller"}


def validate_backend_plan(plan: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(plan, dict):
        return False, ["plan must be a dict"]

    base_package = (plan.get("base_package") or "").strip()
    if not base_package.startswith("egovframework."):
        errors.append("base_package must start with egovframework.")

    domains = plan.get("domains") or []
    if not isinstance(domains, list) or not domains:
        errors.append("domains must be a non-empty list")
        return False, errors

    seen_paths = set()
    expected_config_path = f"src/main/java/{base_package.replace('.', '/')}/config/MyBatisConfig.java" if base_package else ""

    for domain in domains:
        domain_name = domain.get("domain_name") or "domain"
        feature_kind = (domain.get("feature_kind") or "crud").strip().lower()
        controller_mode = domain.get("controller_mode") or ""
        artifacts = domain.get("artifacts") or []
        if not artifacts:
            errors.append(f"{domain_name}: artifacts must not be empty")
            continue

        if controller_mode not in {"mvc_controller", "rest_controller", "nexacro_controller"}:
            errors.append(f"{domain_name}: invalid controller_mode={controller_mode}")

        artifact_types = {artifact.get("artifact_type") for artifact in artifacts}
        required_types = {"vo", "mapper", "mapper_xml", "service", "service_impl", "controller"}
        missing = required_types - artifact_types
        if missing:
            errors.append(f"{domain_name}: missing backend artifacts={sorted(missing)}")

        if feature_kind == "auth":
            forbidden = set(domain.get("forbidden_methods") or [])
            if not {"list", "detail", "save", "delete"}.issubset(forbidden):
                errors.append(f"{domain_name}: auth domain must forbid generic CRUD methods")
        if feature_kind == "upload" and artifact_types.issuperset(CRUD_BACKEND_ARTIFACTS):
            errors.append(f"{domain_name}: feature_kind upload conflicts with generic CRUD backend artifacts")

        for artifact in artifacts:
            path = artifact.get("target_path") or ""
            if not path:
                errors.append(f"{domain_name}: artifact path is empty")
                continue
            if path in seen_paths and not path.endswith("MyBatisConfig.java"):
                errors.append(f"duplicate backend artifact path detected: {path}")
            seen_paths.add(path)
            if not (path.startswith("src/main/java/") or path.startswith("src/main/resources/")):
                errors.append(f"{domain_name}: invalid backend artifact root={path}")
            if artifact.get("artifact_type") == "mybatis_config" and expected_config_path and path != expected_config_path:
                errors.append(f"{domain_name}: MyBatisConfig must use common config path={expected_config_path}, got={path}")

    return len(errors) == 0, errors
