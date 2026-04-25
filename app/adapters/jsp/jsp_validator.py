from __future__ import annotations

from typing import Any, Dict, List, Tuple


CRUD_JSP_ARTIFACTS = {"list_jsp", "detail_jsp", "form_jsp"}


def validate_jsp_plan(plan: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(plan, dict):
        return False, ["plan must be a dict"]

    frontend_mode = (plan.get("frontend_mode") or "").strip().lower()
    if frontend_mode and frontend_mode != "jsp":
        return False, [f"frontend_mode must be jsp for jsp plan, got={frontend_mode}"]

    view_root = (plan.get("view_root") or "").strip()
    if not view_root.startswith("src/main/webapp/WEB-INF/views"):
        errors.append("view_root must start with src/main/webapp/WEB-INF/views")

    domains = plan.get("domains") or []
    if not isinstance(domains, list) or not domains:
        errors.append("domains must be a non-empty list")
        return False, errors

    seen_paths = set()
    for domain in domains:
        domain_name = domain.get("domain_name") or "domain"
        feature_kind = (domain.get("feature_kind") or "crud").strip().lower()
        controller_class_name = (domain.get("controller_class_name") or "").strip()
        controller_package = (domain.get("controller_package") or "").strip()
        model_attribute_name = (domain.get("model_attribute_name") or "").strip()
        views = domain.get("views") or []
        forbidden_views = set(domain.get("forbidden_views") or [])

        if not controller_class_name.endswith("Controller"):
            errors.append(f"{domain_name}: controller_class_name must end with Controller")
        if not controller_package.startswith("egovframework."):
            errors.append(f"{domain_name}: controller_package must start with egovframework.")
        if not model_attribute_name:
            errors.append(f"{domain_name}: model_attribute_name is required")
        if not views:
            errors.append(f"{domain_name}: views must not be empty")
            continue

        access_mode = (domain.get('access_mode') or 'shared').strip().lower()
        if access_mode not in {'shared', 'owner_only', 'admin_all', 'owner_admin_split', 'auth_only'}:
            errors.append(f"{domain_name}: invalid access_mode={access_mode}")
        artifact_types = {view.get("artifact_type") for view in views}
        if feature_kind == "auth":
            if artifact_types != {"login_jsp"}:
                errors.append(f"{domain_name}: auth domain must only have login_jsp")
            expected_forbidden = {"list", "detail", "form", "delete"}
            if not expected_forbidden.issubset(forbidden_views):
                errors.append(f"{domain_name}: auth domain missing forbidden_views entries")
        else:
            missing = CRUD_JSP_ARTIFACTS - artifact_types
            if missing:
                errors.append(f"{domain_name}: missing jsp views={sorted(missing)}")
        if feature_kind == 'upload' and artifact_types.issuperset(CRUD_JSP_ARTIFACTS):
            errors.append(f'{domain_name}: feature_kind upload conflicts with CRUD JSP views')

        for view in views:
            path = (view.get("target_path") or "").strip()
            view_name = (view.get("view_name") or "").strip()
            if not path.startswith("src/main/webapp/WEB-INF/views/"):
                errors.append(f"{domain_name}: invalid jsp path={path}")
            if not path.endswith(".jsp"):
                errors.append(f"{domain_name}: jsp path must end with .jsp -> {path}")
            if path in seen_paths:
                errors.append(f"duplicate jsp path detected: {path}")
            seen_paths.add(path)
            if not view_name or view_name.startswith("/"):
                errors.append(f"{domain_name}: invalid view_name={view_name}")

    return len(errors) == 0, errors
