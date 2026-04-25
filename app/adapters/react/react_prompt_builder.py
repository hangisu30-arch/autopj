from __future__ import annotations

from typing import Any, Dict

from .react_contracts import ReactPlanResult


def react_plan_to_prompt_text(plan: Dict[str, Any] | ReactPlanResult | None) -> str:
    if plan is None:
        return ""
    if isinstance(plan, ReactPlanResult):
        data = plan.to_dict()
    else:
        data = plan

    lines = [
        "[REACT GENERATION PLAN - SOURCE OF TRUTH]",
        f"- project_name: {data.get('project_name') or '(unknown)'}",
        f"- frontend_mode: {data.get('frontend_mode') or '(unknown)'}",
        f"- app_root: {data.get('app_root') or 'frontend/react'}",
        f"- route_registry_path: {data.get('route_registry_path') or 'frontend/react/src/routes/index.jsx'}",
        f"- route_constants_path: {data.get('route_constants_path') or 'frontend/react/src/constants/routes.js'}",
        f"- api_client_path: {data.get('api_client_path') or 'frontend/react/src/api/client.js'}",
    ]

    scaffold = data.get("scaffold_files") or []
    if scaffold:
        lines.append(f"- scaffold_files: {', '.join(scaffold)}")

    domains = data.get("domains") or []
    if not domains:
        lines.append("- domains: (none computed)")
        lines.append("- Build a shared application shell with global navigation so multi-domain routes stay discoverable.")
        lines.append("- Outside explicit auth/login/signup pages and credential-bearing account/user/member create-edit pages, never render or bind auth-sensitive fields such as password/login_password/passwd in React list/detail pages. Credential-bearing account forms may include password inputs, but must never echo existing password values in tables or detail views.")
        lines.append("- Never expose generation metadata fields such as db, schemaName, database, tableName, packageName, frontendType, or backendType in React page bindings or state.")
        lines.append("- Never treat compile/build/runtime/startup/endpoint_smoke as business fields in React routes, forms, tables, or state.")
        lines.append("- Create/edit/save React UI must expose every real DB/DTO column required for persistence. Do not drop table columns from the form just because they look runtime-managed.")
        lines.append("- When a field is read-only, still render it explicitly and keep the API payload/backend SQL aligned to the full table column set.")
        lines.append("- Bind React UI only from the final DTO/API contract. If a mapper-backed field is needed, repair the contract instead of inventing ad-hoc metadata or alias fields.")
        lines.append("- If access_mode is owner_admin_split, create separated self/admin routes or guarded sections and scope non-admin data by the owner field.")
        lines.append("- When admin functionality is required, add an admin menu entry only for admin-role sessions. Normal-user screens must not render admin menu links or admin navigation affordances.")
        lines.append("- Admin pages/routes/APIs must be protected by role checks on both UI and server sides.")
        lines.append("- Use one canonical domain namespace consistently across routes, page directories, API services, and imports. Do not mix snake_case and camelCase variants for the same domain.")
        lines.append("- Only generate calendar pages/routes/APIs when the requirement explicitly asks for calendar/캘린더/달력 화면. Do not create calendar artifacts just because the domain is schedule-like or has temporal columns.")
        lines.append("- For calendar features, the main route, main page/view, and API contract must all agree on the same canonical domain namespace.")
        lines.append("- Keep static UI copy short. Avoid helper paragraphs, repeated captions, decorative subtitles, and duplicate layout wrappers when the label/component already explains the field.")
        lines.append("- Reuse shared components for page shell, search form, table toolbar, form rows, and action bars instead of duplicating large JSX blocks across pages.")
        lines.append("- All physical table names must start with tb_ and the same canonical table name must be reused across SQL, DTO, API, routes, and UI labels.")
        lines.append("- Shared stylesheet/app shell assets must actually be wired into the rendered pages so generated CSS is visible without manual fixes.")
        return "\n".join(lines)

    lines.append("- domains:")
    for domain in domains:
        lines.append(
            f"  - {domain.get('domain_name')}: feature_kind={domain.get('feature_kind')}, api_prefix={domain.get('api_prefix')}, "
            f"route_key={domain.get('route_constant_key')}, route_base_path={domain.get('route_base_path')}"
        )
        forbidden = domain.get("forbidden_artifacts") or []
        if forbidden:
            lines.append(f"    forbidden_artifacts={', '.join(forbidden)}")
        access_mode = domain.get('access_mode') or 'shared'
        owner_fields = domain.get('owner_field_candidates') or []
        role_fields = domain.get('role_field_candidates') or []
        sensitive = domain.get('auth_sensitive_fields') or []
        if access_mode != 'shared' or owner_fields or role_fields or sensitive:
            lines.append(f"    access_mode={access_mode}")
        if owner_fields:
            lines.append(f"    owner_field_candidates={', '.join(owner_fields)}")
        if role_fields:
            lines.append(f"    role_field_candidates={', '.join(role_fields)}")
        if sensitive:
            lines.append(f"    auth_sensitive_fields={', '.join(sensitive)}")
        for artifact in domain.get("artifacts") or []:
            route_path = (artifact.get('route_path') or '').strip()
            route_suffix = f" route={route_path}" if route_path else ""
            lines.append(
                f"    - {artifact.get('artifact_type')}: {artifact.get('target_path')}{route_suffix}"
            )

    lines.append("- You MUST generate React files according to this plan.")
    lines.append("- Use React functional components only. Do not emit Angular/Nest syntax such as @Injectable or constructor(private ...).")
    lines.append("- Centralize routes in src/routes/index.jsx and route constants in src/constants/routes.js.")
    lines.append("- Keep API calls in src/api/client.js and src/api/services/*.js rather than inside pages.")
    lines.append("- For auth domains, only login/auth flow is allowed; generic CRUD pages are forbidden.")
    lines.append("- Build a shared application shell with global navigation so multi-domain routes stay discoverable.")
    lines.append("- Outside explicit auth/login/signup pages and credential-bearing account/user/member create-edit pages, never render or bind auth-sensitive fields such as password/login_password/passwd in React list/detail pages. Credential-bearing account forms may include password inputs, but must never echo existing password values in tables or detail views.")
    lines.append("- Never expose generation metadata fields such as db, schemaName, database, tableName, packageName, frontendType, or backendType in React page bindings or state.")
    lines.append("- Never treat compile/build/runtime/startup/endpoint_smoke as business fields in React routes, forms, tables, or state.")
    lines.append("- Create/edit/save React UI must expose every real DB/DTO column required for persistence. Do not drop table columns from the form just because they look runtime-managed.")
    lines.append("- When a field is read-only, still render it explicitly and keep the API payload/backend SQL aligned to the full table column set.")
    lines.append("- If access_mode is owner_admin_split, create separated self/admin routes or guarded sections and scope non-admin data by the owner field.")
    lines.append("- When admin functionality is required, add an admin menu entry only for admin-role sessions. Normal-user screens must not render admin menu links or admin navigation affordances.")
    lines.append("- Admin pages/routes/APIs must be protected by role checks on both UI and server sides.")
    lines.append("- Use one canonical domain namespace consistently across routes, page directories, API services, and imports. Do not mix snake_case and camelCase variants for the same domain.")
    lines.append("- Only generate calendar pages/routes/APIs when the requirement explicitly asks for calendar/캘린더/달력 화면. Do not create calendar artifacts just because the domain is schedule-like or has temporal columns.")
    lines.append("- For calendar features, the main route, main page/view, and API contract must all agree on the same canonical domain namespace.")
    lines.append("- Keep static UI copy short. Avoid helper paragraphs, repeated captions, decorative subtitles, and duplicate layout wrappers when the label/component already explains the field.")
    lines.append("- Reuse shared components for page shell, search form, table toolbar, form rows, and action bars instead of duplicating large JSX blocks across pages.")
    return "\n".join(lines)

# autopj guard: never emit synthetic placeholder fields such as repeat7, section, tempField, sampleField into business UI or backend contracts.
