from __future__ import annotations

from typing import Any, Dict

from .nexacro_contracts import NexacroPlanResult


def nexacro_plan_to_prompt_text(plan: Dict[str, Any] | NexacroPlanResult | None) -> str:
    if plan is None:
        return ''
    if isinstance(plan, NexacroPlanResult):
        data = plan.to_dict()
    else:
        data = plan

    lines = [
        '[NEXACRO GENERATION PLAN - SOURCE OF TRUTH]',
        f"- project_name: {data.get('project_name') or '(unknown)'}",
        f"- frontend_mode: {data.get('frontend_mode') or '(unknown)'}",
        f"- app_root: {data.get('app_root') or 'frontend/nexacro'}",
        f"- application_config_path: {data.get('application_config_path') or 'frontend/nexacro/Application_Desktop.xadl'}",
        f"- environment_path: {data.get('environment_path') or 'frontend/nexacro/_extlib_/environment.xml'}",
        f"- service_url_map_path: {data.get('service_url_map_path') or 'frontend/nexacro/services/service-url-map.json'}",
    ]

    scaffold = data.get('scaffold_files') or []
    if scaffold:
        lines.append(f"- scaffold_files: {', '.join(scaffold)}")

    domains = data.get('domains') or []
    if not domains:
        lines.append('- domains: (none computed)')
        return '\n'.join(lines)

    lines.append('- domains:')
    for domain in domains:
        lines.append(
            f"  - {domain.get('domain_name')}: feature_kind={domain.get('feature_kind')}, api_prefix={domain.get('api_prefix')}, dataset_prefix={domain.get('dataset_prefix')}, transaction_service_id={domain.get('transaction_service_id')}"
        )
        forbidden = domain.get('forbidden_artifacts') or []
        if forbidden:
            lines.append(f"    forbidden_artifacts={', '.join(forbidden)}")
        for artifact in domain.get('artifacts') or []:
            extra = []
            if artifact.get('dataset_name'):
                extra.append(f"dataset={artifact.get('dataset_name')}")
            if artifact.get('service_id'):
                extra.append(f"service_id={artifact.get('service_id')}")
            suffix = f" ({', '.join(extra)})" if extra else ''
            lines.append(f"    - {artifact.get('artifact_type')}: {artifact.get('target_path')}{suffix}")

    lines.append('- You MUST generate Nexacro files according to this plan.')
    lines.append('- Use .xfdl for forms, .xjs for transaction scripts, and JSON only for dataset metadata files.')
    lines.append('- Keep DataSet names, transaction service ids, and form paths aligned with this plan.')
    lines.append('- All physical table names must start with tb_ and the same canonical table name must be reused across SQL, DTO/DataSet contracts, transactions, and forms.')
    lines.append('- Shared styles/theme assets must be wired into generated forms so CSS/theme changes are visible without manual fixes.')
    lines.append('- Auth domains may generate only login/auth artifacts; generic CRUD Nexacro forms are forbidden for auth.')
    lines.append('- Never treat compile/build/runtime/startup/endpoint_smoke as business DataSet columns, transaction ids, or form fields.')
    lines.append('- Create/edit/save Nexacro forms must expose every real DB/DataSet column required for persistence. Do not drop table columns from the form just because they look runtime-managed.')
    lines.append('- When a field is read-only, still render it explicitly and keep the transaction input/backend SQL aligned to the full table column set.')
    lines.append('- Keep static UI copy short. Avoid long guide text, helper paragraphs, decorative subtitles, and verbose empty-state messages unless the user explicitly requested them.')
    lines.append('- Use concise captions and button labels. Prefer compact grids/forms over text-heavy layouts.')
    lines.append('- Reuse shared form/include/theme assets instead of copying the same title/search/action area into every form.')
    return '\n'.join(lines)
