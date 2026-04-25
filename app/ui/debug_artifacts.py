from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

DEBUG_FILENAMES = {
    'analysis_result': 'analysis_result.json',
    'backend_plan': 'backend_plan.json',
    'jsp_plan': 'jsp_plan.json',
    'react_plan': 'react_plan.json',
    'vue_plan': 'vue_plan.json',
    'nexacro_plan': 'nexacro_plan.json',
    'validation_report': 'validation_report.json',
    'repair_plan': 'repair_plan.json',
}


def _read_json(path: Path) -> Dict[str, Any] | None:
    try:
        if not path.exists():
            return None
        raw = path.read_text(encoding='utf-8')
        data = json.loads(raw)
        return data if isinstance(data, dict) else {'root': data}
    except Exception as exc:
        return {'_read_error': str(exc), '_path': str(path)}


def load_debug_bundle(output_dir: str) -> Dict[str, Any]:
    out = (output_dir or '').strip()
    root = Path(out) if out else Path('.')
    debug_dir = root / '.autopj_debug'

    bundle: Dict[str, Any] = {
        'output_dir': str(root),
        'debug_dir': str(debug_dir),
        'exists': debug_dir.exists(),
        'files': {},
        'analysis_result': None,
        'backend_plan': None,
        'jsp_plan': None,
        'react_plan': None,
        'vue_plan': None,
        'nexacro_plan': None,
        'validation_report': None,
        'repair_plan': None,
        'apply_report': None,
    }

    for key, filename in DEBUG_FILENAMES.items():
        path = debug_dir / filename
        bundle['files'][filename] = path.exists()
        bundle[key] = _read_json(path)

    apply_path = root / 'apply_report.json'
    bundle['files']['apply_report.json'] = apply_path.exists()
    bundle['apply_report'] = _read_json(apply_path)
    return bundle


def _safe_join(items: Iterable[str], sep: str = ', ') -> str:
    values = [str(x) for x in items if str(x).strip()]
    return sep.join(values) if values else '(none)'


def _pick_frontend_plan(bundle: Dict[str, Any]) -> Tuple[str, Dict[str, Any] | None]:
    for key in ('jsp_plan', 'react_plan', 'vue_plan', 'nexacro_plan'):
        data = bundle.get(key)
        if isinstance(data, dict) and data:
            return key, data
    return '', None


def render_debug_summary_text(bundle: Dict[str, Any]) -> str:
    analysis = bundle.get('analysis_result') or {}
    backend = bundle.get('backend_plan') or {}
    validation = bundle.get('validation_report') or {}
    repair = bundle.get('repair_plan') or {}
    apply_report = bundle.get('apply_report') or {}
    frontend_plan_name, frontend_plan = _pick_frontend_plan(bundle)

    project = analysis.get('project') or {}
    domains = analysis.get('domains') or []
    summary = validation.get('summary') or {}

    lines = [
        'UI REINFORCEMENT SUMMARY',
        f"- output_dir: {bundle.get('output_dir') or '(none)'}",
        f"- debug_dir_exists: {bundle.get('exists')}",
        f"- project_name: {project.get('project_name') or backend.get('project_name') or '(unknown)'}",
        f"- backend_mode: {project.get('backend_mode') or backend.get('backend_mode') or '(unknown)'}",
        f"- frontend_mode: {project.get('frontend_mode') or backend.get('frontend_mode') or '(unknown)'}",
        f"- database_type: {project.get('database_type') or backend.get('database_type') or '(unknown)'}",
        f"- domains: {len(domains)}",
        f"- backend_domains: {len(backend.get('domains') or [])}",
        f"- frontend_plan: {frontend_plan_name or '(none)'} / domains={len((frontend_plan or {}).get('domains') or [])}",
        f"- validation_ok: {validation.get('ok')}",
        f"- failed_checks: {summary.get('failed_checks', 0)}",
        f"- total_errors: {summary.get('total_errors', 0)}",
        f"- repair_mode: {repair.get('repair_mode') or '(none)'}",
    ]

    if isinstance(apply_report, dict) and apply_report:
        written = len(apply_report.get('written') or [])
        failed = len(apply_report.get('failed') or [])
        lines.append(f'- apply_report: written={written}, failed={failed}')
    else:
        lines.append('- apply_report: (none)')

    existing = [name for name, ok in (bundle.get('files') or {}).items() if ok]
    lines.append(f"- available_files: {_safe_join(existing)}")
    return '\n'.join(lines)


def render_analysis_text(bundle: Dict[str, Any]) -> str:
    analysis = bundle.get('analysis_result') or {}
    if not analysis:
        return 'analysis_result.json 없음'

    project = analysis.get('project') or {}
    lines = [
        '[ANALYSIS RESULT]',
        f"- project_name: {project.get('project_name') or '(unknown)'}",
        f"- base_package: {project.get('base_package') or '(unknown)'}",
        f"- frontend_mode: {project.get('frontend_mode') or '(unknown)'}",
        f"- database_type: {project.get('database_type') or '(unknown)'}",
        '',
        '- domains:',
    ]
    for domain in analysis.get('domains') or []:
        lines.append(
            f"  - {domain.get('name')}: feature_kind={domain.get('feature_kind')}, table={domain.get('source_table')}, pk={domain.get('primary_key') or '(none)'}"
        )
        pages = domain.get('pages') or []
        lines.append(f"    pages={_safe_join(pages)}")
        fields = domain.get('fields') or []
        for field in fields[:15]:
            lines.append(
                f"    field: {field.get('column')} -> {field.get('name')} ({field.get('java_type')}) pk={field.get('pk')}"
            )
        if len(fields) > 15:
            lines.append(f"    ... {len(fields) - 15} more fields")
    return '\n'.join(lines)


def _render_backend_plan(backend: Dict[str, Any]) -> list[str]:
    lines = ['[BACKEND PLAN]']
    lines.append(f"- template_managed_files: {_safe_join(backend.get('template_managed_files') or [])}")
    for domain in backend.get('domains') or []:
        lines.append(
            f"  - {domain.get('domain_name')}: feature_kind={domain.get('feature_kind')}, controller_mode={domain.get('controller_mode')}"
        )
        for artifact in domain.get('artifacts') or []:
            lines.append(f"    {artifact.get('artifact_type')}: {artifact.get('target_path')}")
    return lines


def _render_frontend_plan(title: str, plan: Dict[str, Any]) -> list[str]:
    lines = [f'[{title}]']
    for key in ('app_root', 'route_registry_path', 'route_constants_path', 'api_client_path'):
        if plan.get(key):
            lines.append(f"- {key}: {plan.get(key)}")
    if plan.get('scaffold_files'):
        lines.append(f"- scaffold_files: {_safe_join(plan.get('scaffold_files') or [])}")

    for domain in plan.get('domains') or []:
        lines.append(
            f"  - {domain.get('domain_name')}: feature_kind={domain.get('feature_kind')}, route_base={domain.get('route_base_path') or domain.get('form_dir') or '(n/a)'}"
        )
        for key in ('views', 'artifacts', 'forms', 'scripts', 'datasets'):
            items = domain.get(key) or []
            if not items:
                continue
            for item in items:
                lines.append(f"    {item.get('artifact_type')}: {item.get('target_path')}")
    return lines


def render_plan_text(bundle: Dict[str, Any]) -> str:
    sections: list[str] = []
    backend = bundle.get('backend_plan') or {}
    if backend:
        sections.extend(_render_backend_plan(backend))
        sections.append('')

    for key, title in (
        ('jsp_plan', 'JSP PLAN'),
        ('react_plan', 'REACT PLAN'),
        ('vue_plan', 'VUE PLAN'),
        ('nexacro_plan', 'NEXACRO PLAN'),
    ):
        plan = bundle.get(key) or {}
        if plan:
            sections.extend(_render_frontend_plan(title, plan))
            sections.append('')

    return '\n'.join(sections).strip() or '생성 계획 파일 없음'


def render_validation_text(bundle: Dict[str, Any]) -> str:
    report = bundle.get('validation_report') or {}
    repair = bundle.get('repair_plan') or {}
    if not report and not repair:
        return 'validation_report.json / repair_plan.json 없음'

    lines = ['[VALIDATION REPORT]']
    if report:
        lines.append(f"- ok: {report.get('ok')}")
        lines.append(f"- frontend_key: {report.get('frontend_key') or '(none)'}")
        summary = report.get('summary') or {}
        lines.append(f"- total_checks: {summary.get('total_checks', 0)}")
        lines.append(f"- failed_checks: {summary.get('failed_checks', 0)}")
        lines.append(f"- total_errors: {summary.get('total_errors', 0)}")
        for check in report.get('checks') or []:
            lines.append(f"  - {check.get('name')}: ok={check.get('ok')}, errors={len(check.get('errors') or [])}")
        for item in report.get('classified_errors') or []:
            lines.append(
                f"  - error_code={item.get('code')}, target={item.get('target')}, repairable={item.get('repairable')}, message={item.get('message')}"
            )

    lines.append('')
    lines.append('[REPAIR PLAN]')
    if repair:
        lines.append(f"- ok: {repair.get('ok')}")
        lines.append(f"- repair_mode: {repair.get('repair_mode') or '(none)'}")
        for action in repair.get('actions') or []:
            lines.append(
                f"  - action={action.get('action')}, target={action.get('target')}, reason={action.get('reason') or action.get('code') or '(none)'}"
            )
        notes = repair.get('notes') or []
        if notes:
            lines.append(f"- notes: {_safe_join(notes, sep=' | ')}")
    return '\n'.join(lines)


def render_apply_report_text(bundle: Dict[str, Any]) -> str:
    report = bundle.get('apply_report') or {}
    if not report:
        return 'apply_report.json 없음'

    lines = ['[APPLY REPORT]']
    for key in ('ok', 'output_dir', 'project_dir', 'written_count', 'failed_count'):
        if key in report:
            lines.append(f"- {key}: {report.get(key)}")

    written = report.get('written') or []
    failed = report.get('failed') or []
    if written:
        lines.append('- written:')
        for item in written[:100]:
            lines.append(f'  - {item}')
        if len(written) > 100:
            lines.append(f'  ... {len(written) - 100} more written files')
    if failed:
        lines.append('- failed:')
        for item in failed[:100]:
            lines.append(f'  - {item}')
        if len(failed) > 100:
            lines.append(f'  ... {len(failed) - 100} more failed files')
    return '\n'.join(lines)
