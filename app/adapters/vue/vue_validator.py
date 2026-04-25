from __future__ import annotations

from typing import Any, Dict, List, Tuple


def validate_vue_plan(plan: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(plan, dict):
        return False, ["plan must be a dict"]

    frontend_mode = (plan.get("frontend_mode") or "").strip().lower()
    if frontend_mode and frontend_mode != "vue":
        return False, [f"frontend_mode must be vue for vue plan, got={frontend_mode}"]

    app_root = (plan.get("app_root") or "").strip()
    if app_root != "frontend/vue":
        errors.append("app_root must be frontend/vue")

    required_globals = {
        "frontend/vue/package.json",
        "frontend/vue/vite.config.js",
        "frontend/vue/index.html",
        "frontend/vue/src/main.js",
        "frontend/vue/src/App.vue",
        "frontend/vue/src/router/index.js",
        "frontend/vue/src/constants/routes.js",
        "frontend/vue/src/api/client.js",
        "frontend/vue/src/stores/index.js",
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
        view_dir = (domain.get("view_dir") or "").strip()
        store_path = (domain.get("store_path") or "").strip()
        router_name = (domain.get("router_name") or "").strip()
        artifacts = domain.get("artifacts") or []
        forbidden = set(domain.get("forbidden_artifacts") or [])

        if not view_dir.startswith("frontend/vue/src/views/"):
            errors.append(f"{domain_name}: invalid view_dir={view_dir}")
        if not service_path.startswith("frontend/vue/src/api/"):
            errors.append(f"{domain_name}: invalid service_path={service_path}")
        if store_path and store_path != "frontend/vue/src/stores/index.js":
            errors.append(f"{domain_name}: invalid store_path={store_path}")
        if not router_name:
            errors.append(f"{domain_name}: router_name is required")
        if not artifacts:
            errors.append(f"{domain_name}: artifacts must not be empty")
            continue

        access_mode = (domain.get('access_mode') or 'shared').strip().lower()
        if access_mode not in {'shared', 'owner_only', 'admin_all', 'owner_admin_split', 'auth_only'}:
            errors.append(f"{domain_name}: invalid access_mode={access_mode}")
        artifact_types = {artifact.get("artifact_type") for artifact in artifacts}
        if feature_kind == "auth":
            required = {"login_view", "auth_api", "route_guard"}
            missing = required - artifact_types
            if missing:
                errors.append(f"{domain_name}: missing auth vue artifacts={sorted(missing)}")
            expected_forbidden = {"view_list", "view_detail", "view_form", "generic_crud_service"}
            if not expected_forbidden.issubset(forbidden):
                errors.append(f"{domain_name}: auth domain missing forbidden_artifacts entries")
        else:
            required = {"view_list", "view_detail", "view_form", "api_service"}
            missing = required - artifact_types
            if missing:
                errors.append(f"{domain_name}: missing vue artifacts={sorted(missing)}")

        for artifact in artifacts:
            path = (artifact.get("target_path") or "").strip()
            if not path.startswith("frontend/vue/"):
                errors.append(f"{domain_name}: invalid vue artifact root={path}")
            if path in seen_paths and not path.endswith("guards.js") and not path.endswith("auth.js"):
                errors.append(f"duplicate vue artifact path detected: {path}")
            seen_paths.add(path)
            if "/WEB-INF/views/" in path:
                errors.append(f"{domain_name}: JSP path leaked into vue plan -> {path}")
            if path.endswith('.jsx'):
                errors.append(f"{domain_name}: react artifact leaked into vue plan -> {path}")

    return len(errors) == 0, errors
