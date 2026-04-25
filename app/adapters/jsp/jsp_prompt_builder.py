from __future__ import annotations

from typing import Any, Dict

from .jsp_contracts import JspPlanResult


def jsp_plan_to_prompt_text(plan: Dict[str, Any] | JspPlanResult | None) -> str:
    if plan is None:
        return ""
    if isinstance(plan, JspPlanResult):
        data = plan.to_dict()
    else:
        data = plan

    lines = [
        "[JSP GENERATION PLAN - SOURCE OF TRUTH]",
        f"- project_name: {data.get('project_name') or '(unknown)'}",
        f"- base_package: {data.get('base_package') or '(unknown)'}",
        f"- frontend_mode: {data.get('frontend_mode') or '(unknown)'}",
        f"- view_root: {data.get('view_root') or 'src/main/webapp/WEB-INF/views'}",
    ]

    rules_block = [
        "- You MUST generate JSP files and MVC controller return values according to this plan.",
        "- Do not flatten views into /WEB-INF/views root when a domain directory is specified here.",
        "- For auth domains, only login JSP flow is allowed; generic CRUD JSPs are forbidden.",
        "- JSP MVC Controller must be minimal: request mapping, VO binding, service delegation, model setup, and view/redirect return only.",
        "- JSP CRUD Controller must only expose list/detail/form/save/delete unless explicitly required otherwise.",
        "- Do not place SQL text, large validation branches, helper methods, or long comments inside Controller.",
        "- Target JSP Controller size: <= 4500 chars, <= 120 lines, <= 5 mapping handlers.",
        "- Use <Entity>VO consistently in Service, ServiceImpl, Controller, Mapper interface, and Mapper XML. Do not switch some methods to raw String/Long unless the same id type is used everywhere.",
        "- Primary key request parameter name and type must come from the actual VO/DB primary key field (for example roomId: Long, memberId: String). Never hardcode generic id:String when the service/VO expects another name or type.",
        "- detail/form/delete controller methods, JSP query parameters, hidden inputs, service signatures, and mapper parameters must all use the same primary key property name and Java type.",
        "- Controller @ModelAttribute binding type must be <Entity>VO. Do not generate undefined domain objects such as <Entity>.",
        "- Service and ServiceImpl must import java.util.List when returning List<VO>, and must import every referenced VO/Mapper type explicitly.",
        "- Mapper interface must stay in XML-only mode: keep @Mapper, remove @Select/@Insert/@Update/@Delete/@Results annotations, and let Mapper.xml own the SQL.",
        "- Mapper XML must be pure MyBatis mapper XML with mapper DOCTYPE and namespace equal to the Mapper interface FQCN. Never mix Spring <beans> XML into Mapper.xml.",
        "- MyBatisConfig must include @MapperScan for the generated mapper package and setMapperLocations(classpath*:egovframework/mapper/**/*.xml).",
        "- Use a shared project layout with common/header.jsp and common/leftNav.jsp for all major JSP screens.",
        "- Calendar/list/detail/form pages must expose working detail/edit links based on the real primary key field name.",
        "- Outside explicit auth/login/signup screens and credential-bearing account/user/member create-edit forms, never render or bind auth-sensitive fields such as password/login_password/passwd in JSP list/detail/search UI. Credential-bearing account forms may include password inputs, but must never display existing password values in list/detail screens.",
        "- Create/edit/save UI must expose every real DB/VO column needed for persistence. Do not omit table columns from the form just because they look runtime-managed.",
        "- When a field is intentionally read-only, still render it explicitly and keep the backend SQL/schema contract aligned to the full table column set.",
        "- Never expose generation metadata fields such as db, schemaName, database, tableName, packageName, frontendType, or backendType in domain UI bindings.",
        "- Bind UI fields only from the final VO/DTO/API contract. If a mapper-backed field exists but the contract is missing it, repair the contract instead of inventing ad-hoc metadata or alias fields.",
        "- If access_mode is owner_admin_split, separate normal-user screens from admin screens and filter data by the owner field for non-admin sessions.",
        "- When admin functionality is required, add an admin menu entry only for admin-role sessions. Normal-user screens must not render admin menu links or admin navigation affordances.",
        "- Admin pages/routes/APIs must be protected by role checks on both UI and server sides.",
        "- Use one canonical domain namespace consistently across controller package, route base, view directory, file names, and generated artifacts. Do not mix snake_case and camelCase variants for the same domain.",
        "- Only generate calendar pages/routes/APIs when the requirement explicitly asks for calendar/캘린더/달력 화면. Do not create calendar artifacts just because the domain is schedule-like or has temporal columns.",
        "- For calendar features, the main route, main controller handler, main view/page, and return target must all agree on the same canonical domain namespace.",
        "- If the boot application class package is different from generated egovframework.<project>.* packages, include scanBasePackages to cover generated modules.",
        "- JSP must load the shared stylesheet contract correctly so generated common.css/layout CSS is actually visible on rendered pages.",
        "- Do not leave orphan closing tags such as </form>, </if>, </div>, or selectorless CSS declarations. Generate the matching opening structure or omit the stray closing token entirely.",
        "- All physical table names must start with tb_ and the same canonical table name must be reused across schema.sql, Mapper XML, SQL, VO, and JSP routes/forms.",
        "- User-requested columns and comments are authoritative. Reflect them into the real DB table first, then derive CRUD/search/detail/form/navigation contracts from that reflected table contract.",
        "- Never leave orphan closing tags such as </c:if> or </form>. Either generate the matching opening tag structure or remove the stray closing tag entirely.",
        "- JWT/cert/integration helper artifacts must never be generated unless the matching auth option is explicitly enabled. Existing stray helper file names must not be treated as a request to generate those auth modes.",
        "- Shared navigation must include signup/register entry when signup is required, and list pages must render concrete search conditions for every searchable persisted field except forbidden sensitive/meta fields.",
        "- Keep static UI copy short. Avoid helper paragraphs, repetitive field hints, decorative subtitles, and duplicated wrappers when the label/control already conveys the meaning.",
        "- Prefer shared include/layout assets over repeating the same style/script/header/search wrapper in every page. Generate compact JSP markup first and reuse common structure.",
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
            f"controller={domain.get('controller_package')}.{domain.get('controller_class_name')}, "
            f"model_attribute={domain.get('model_attribute_name')}, base_view_dir={domain.get('base_view_dir')}"
        )
        forbidden = domain.get("forbidden_views") or []
        if forbidden:
            lines.append(f"    forbidden_views={', '.join(forbidden)}")
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
        for view in domain.get("views") or []:
            lines.append(
                f"    - {view.get('artifact_type')}: {view.get('target_path')} -> return \"{view.get('view_name')}\""
            )

    lines.extend(rules_block)
    return "\n".join(lines)

# autopj guard: never emit synthetic placeholder fields such as repeat7, section, tempField, sampleField into business UI or backend contracts.
