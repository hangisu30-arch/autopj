from __future__ import annotations

from typing import Any, Dict

from .backend_contracts import BackendPlanResult


def backend_plan_to_prompt_text(plan: Dict[str, Any] | BackendPlanResult | None) -> str:
    if plan is None:
        return ""
    if isinstance(plan, BackendPlanResult):
        data = plan.to_dict()
    else:
        data = plan

    lines = [
        "[COMMON BACKEND GENERATION PLAN - SOURCE OF TRUTH]",
        f"- project_name: {data.get('project_name') or '(unknown)'}",
        f"- base_package: {data.get('base_package') or '(unknown)'}",
        f"- backend_mode: {data.get('backend_mode') or '(unknown)'}",
        f"- frontend_mode: {data.get('frontend_mode') or '(unknown)'}",
        f"- database_type: {data.get('database_type') or '(unknown)'}",
    ]

    template_managed = data.get("template_managed_files") or []
    if template_managed:
        lines.append(f"- template_managed_files: {', '.join(template_managed)}")

    rules_block = [
        "- You MUST generate backend files according to this plan.",
        "- Do not change controller mode computed here. JSP uses MVC, React/Vue use REST, Nexacro uses Nexacro controller style.",
        "- For auth domains, do not emit generic CRUD handlers or CRUD mapper methods.",
        "- JSP MVC Controller must stay thin: only list/detail/form/save/delete handlers unless explicitly required otherwise.",
        "- Do not put business logic, SQL construction, deep validation branches, helper methods, or large comments inside Controller.",
        "- Target JSP Controller size: <= 4500 chars, <= 120 lines, <= 5 mapping handlers.",
        "- MyBatisConfig must be valid Spring Boot Java: @Configuration, @MapperScan, DataSource, SqlSessionFactoryBean, and setMapperLocations are required.",
        "- Mapper interface and Mapper XML must stay in XML-only MyBatis mode: keep @Mapper on interface, but forbid SQL annotations such as @Select/@Insert/@Update/@Delete.",
        "- Mapper XML must be pure MyBatis mapper XML only. Never mix <beans>, HibernateTemplate, SqlMap, or legacy Spring bean fragments into Mapper.xml.",
        "- Service, ServiceImpl, Mapper, Controller, and Mapper XML signatures must match exactly for the same domain and id parameter type.",
        "- If a Service or ServiceImpl uses List or a VO type, generate the required imports explicitly.",
        "- JSP Controller form/save binding must use <Entity>VO, not undefined domain objects like <Entity>.",
        "- If EgovBootApplication package differs from generated module packages, add scanBasePackages so Spring can discover generated beans.",
        "- Outside explicit auth/signup/reset-password handlers, never expose auth-sensitive fields such as password/login_password/passwd in CRUD/calendar DTO response payloads or server-rendered model attributes.",
        "- Never leak generation metadata fields such as db, schemaName, database, tableName, packageName, frontendType, or backendType into DTOs, API payloads, model attributes, or frontend-facing contracts.",
        "- Never treat generation/runtime status markers such as compile, build, runtime, startup, or endpoint_smoke as business columns or mapper fields.",
        "- Backend contract must stay aligned to the full real table column set. Create/edit/save UI may mark fields read-only, but it must still render all persistence columns explicitly and SQL/DTO/VO must remain column-complete.",
        "- If a mapper-backed field is required by the UI, repair the DTO/API contract instead of inventing ad-hoc metadata or alias fields.",
        "- If access_mode is owner_admin_split, reuse the shared auth table/session context, separate owner/admin access rules at controller+service+mapper level, and avoid hardcoded domain names or frontend-specific logic.",
        "- When admin functionality is required, add an admin menu entry only for admin-role sessions and hide admin navigation from normal-user screens.",
        "- Admin pages/routes/APIs must be protected by role checks on both UI and server sides.",
        "- User-requested physical columns and column comments must be materialized in the real DB table, and CRUD/VO/DTO/Mapper/UI contracts must be generated from that reflected table contract.",
        "- Use one canonical domain namespace consistently across package names, route mappings, mapper paths, VO names, and view/page names. Do not mix snake_case and camelCase variants for the same domain.",
        "- Only generate calendar pages/routes/APIs when the requirement explicitly asks for calendar/캘린더/달력 화면. Do not create calendar artifacts just because the domain is schedule-like or has temporal columns.",
        "- For calendar features, keep the main route, controller return target, mapper contract, and frontend main view/page aligned to the same canonical domain namespace.",
        "- All physical table names must start with tb_ and the same canonical table name must be reused across schema.sql, mapper XML, SQL, VO/DTO, and frontend contracts.",
        "- Backend must not assume omitted UI fields; create/edit/save contracts must stay aligned to the full persistence column set.",
        "- JWT/cert/integration helper artifacts must never be generated unless the matching auth option is explicitly enabled. Existing stray helper files or route names must not be treated as an enable signal.",
        "- When frontend files are generated alongside backend code, favor shared layout/assets and compact page contracts over repeated explanatory copy or duplicated wrappers.",
    ]

    domains = data.get("domains") or []
    if not domains:
        lines.append("- domains: (none computed)")
        lines.extend(rules_block)
        return "\n".join(lines)

    lines.append("- domains:")
    for domain in domains:
        lines.append(
            f"  - {domain.get('domain_name')}: feature_kind={domain.get('feature_kind')}, "
            f"controller_mode={domain.get('controller_mode')}, table={domain.get('source_table') or domain.get('domain_name')}"
        )
        forbidden = domain.get("forbidden_methods") or []
        if forbidden:
            lines.append(f"    forbidden_methods={', '.join(forbidden)}")
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
            lines.append(f"    - {artifact.get('artifact_type')}: {artifact.get('target_path')}")

    lines.extend(rules_block)
    return "\n".join(lines)

# autopj guard: never emit synthetic placeholder fields such as repeat7, section, tempField, sampleField into business UI or backend contracts.
