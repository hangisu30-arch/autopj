from __future__ import annotations

from typing import Any, Dict, List, Tuple


def validate_react_plan(plan: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(plan, dict):
        return False, ["plan must be a dict"]

    frontend_mode = (plan.get("frontend_mode") or "").strip().lower()
    if frontend_mode and frontend_mode != "react":
        return False, [f"frontend_mode must be react for react plan, got={frontend_mode}"]

    app_root = (plan.get("app_root") or "").strip()
    if app_root != "frontend/react":
        errors.append("app_root must be frontend/react")

    required_globals = {
        "frontend/react/package.json",
        "frontend/react/vite.config.js",
        "frontend/react/index.html",
        "frontend/react/src/main.jsx",
        "frontend/react/src/App.jsx",
        "frontend/react/src/routes/index.jsx",
        "frontend/react/src/constants/routes.js",
        "frontend/react/src/api/client.js",
    }
    scaffold_files = set(plan.get("scaffold_files") or [])
    missing_globals = required_globals - scaffold_files
    if missing_globals:
        errors.append(f"missing scaffold_files={sorted(missing_globals)}")

    domains = plan.get("domains") or []
    if not isinstance(domains, list) or not domains:
        errors.append("domains must be a non-empty list")
        return False, errors

    seen_paths = set()
    for domain in domains:
        domain_name = domain.get("domain_name") or "domain"
        feature_kind = (domain.get("feature_kind") or "crud").strip().lower()
        service_path = (domain.get("service_path") or "").strip()
        page_dir = (domain.get("page_dir") or "").strip()
        route_key = (domain.get("route_constant_key") or "").strip()
        artifacts = domain.get("artifacts") or []
        forbidden = set(domain.get("forbidden_artifacts") or [])

        if not page_dir.startswith("frontend/react/src/pages/"):
            errors.append(f"{domain_name}: invalid page_dir={page_dir}")
        if not service_path.startswith("frontend/react/src/api/services/"):
            errors.append(f"{domain_name}: invalid service_path={service_path}")
        if not route_key:
            errors.append(f"{domain_name}: route_constant_key is required")
        if not artifacts:
            errors.append(f"{domain_name}: artifacts must not be empty")
            continue

        access_mode = (domain.get('access_mode') or 'shared').strip().lower()
        if access_mode not in {'shared', 'owner_only', 'admin_all', 'owner_admin_split', 'auth_only'}:
            errors.append(f"{domain_name}: invalid access_mode={access_mode}")
        artifact_types = {artifact.get("artifact_type") for artifact in artifacts}
        if feature_kind == "auth":
            required = {"login_page", "auth_api", "route_guard"}
            missing = required - artifact_types
            if missing:
                errors.append(f"{domain_name}: missing auth react artifacts={sorted(missing)}")
            expected_forbidden = {"page_list", "page_detail", "page_form", "generic_crud_service"}
            if not expected_forbidden.issubset(forbidden):
                errors.append(f"{domain_name}: auth domain missing forbidden_artifacts entries")
        else:
            required = {"page_list", "page_detail", "page_form", "api_service"}
            missing = required - artifact_types
            if missing:
                errors.append(f"{domain_name}: missing react artifacts={sorted(missing)}")

        for artifact in artifacts:
            path = (artifact.get("target_path") or "").strip()
            if not path.startswith("frontend/react/"):
                errors.append(f"{domain_name}: invalid react artifact root={path}")
            if path in seen_paths and not path.endswith("RouteGuard.jsx"):
                errors.append(f"duplicate react artifact path detected: {path}")
            seen_paths.add(path)
            if "/WEB-INF/views/" in path:
                errors.append(f"{domain_name}: JSP path leaked into react plan -> {path}")

    return len(errors) == 0, errors
