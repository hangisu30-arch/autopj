from __future__ import annotations

import json
import difflib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .runtime_smoke import run_backend_runtime_validation, write_runtime_report
from execution_core.builtin_crud import _db_reserved_keywords, _normalize_db_vendor


_BOOT_APP_CLASS = 'EgovBootApplication'
_BOOT_APP_ILLEGAL_SUFFIXES = (
    'Controller.java',
    'ServiceImpl.java',
    'Service.java',
    'Mapper.java',
    'VO.java',
    'Mapper.xml',
    'List.jsp',
    'Detail.jsp',
    'Form.jsp',
    'Calendar.jsp',
    'View.jsp',
    'Edit.jsp',
)


_INFRA_CANONICAL_PATH_SUFFIXES = {
    'AuthLoginInterceptor.java': '/config/AuthLoginInterceptor.java',
    'WebMvcConfig.java': '/config/WebMvcConfig.java',
    'JwtTokenProvider.java': '/config/JwtTokenProvider.java',
    'LoginDatabaseInitializer.java': '/config/LoginDatabaseInitializer.java',
    'MyBatisConfig.java': '/config/MyBatisConfig.java',
}
_INFRA_ALIAS_FILENAMES = {'AuthenticInterceptor.java': 'AuthLoginInterceptor.java', 'AuthInterceptor.java': 'AuthLoginInterceptor.java', 'WebConfig.java': 'WebMvcConfig.java'}
_INFRA_CRUD_STEMS = {'AuthLoginInterceptor', 'AuthenticInterceptor', 'AuthInterceptor', 'WebConfig', 'WebMvcConfig', 'JwtTokenProvider', 'LoginDatabaseInitializer', 'MyBatisConfig'}
_INFRA_ILLEGAL_SUFFIXES = ('Controller.java', 'ServiceImpl.java', 'Service.java', 'Mapper.java', 'VO.java', 'Mapper.xml', 'List.jsp', 'Detail.jsp', 'Form.jsp', 'Calendar.jsp', 'View.jsp', 'Edit.jsp')


def _is_illegal_infra_artifact_rel(path: str) -> bool:
    norm = (path or '').replace('\\', '/').lstrip('./')
    name = Path(norm).name
    if name in _INFRA_ALIAS_FILENAMES:
        return True
    canonical_suffix = _INFRA_CANONICAL_PATH_SUFFIXES.get(name)
    if canonical_suffix:
        return not norm.endswith(canonical_suffix)
    for stem in _INFRA_CRUD_STEMS:
        if any(name == f'{stem}{suffix}' for suffix in _INFRA_ILLEGAL_SUFFIXES):
            return True
    return False


def _is_boot_crud_artifact_rel(path: str) -> bool:
    norm = (path or '').replace('\\', '/').lstrip('./')
    name = Path(norm).name
    if name == f'{_BOOT_APP_CLASS}.java':
        return False
    return any(name == f'{_BOOT_APP_CLASS}{suffix}' for suffix in _BOOT_APP_ILLEGAL_SUFFIXES)


def _normalize_rel_path(path: str) -> str:
    return (path or "").replace("\\", "/").lstrip("./")


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return path.read_text(encoding="utf-8", errors="ignore")


def _issue(
    issue_type: str,
    path: str,
    message: str,
    repairable: bool = True,
    severity: str = "error",
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "type": issue_type,
        "path": _normalize_rel_path(path),
        "message": message,
        "repairable": repairable,
        "severity": severity,
        "details": details or {},
    }


def _canonical_snake_name(name: str) -> str:
    raw = str(name or '').strip()
    if not raw:
        return ''
    raw = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', raw)
    raw = re.sub(r'[^A-Za-z0-9]+', '_', raw)
    return raw.strip('_').lower()


def _canonical_camel_name(name: str) -> str:
    snake = _canonical_snake_name(name)
    parts = [part for part in snake.split('_') if part]
    if not parts:
        return ''
    return parts[0] + ''.join(part[:1].upper() + part[1:] for part in parts[1:])


def _domain_canonical_key(name: str) -> str:
    snake = _canonical_snake_name(name)
    return snake.replace('_', '')


def _combine_controller_route(prefix: str, route: str) -> str:
    class_prefix = str(prefix or '').strip()
    method_route = str(route or '').strip()
    if not method_route:
        return class_prefix
    if not class_prefix:
        return method_route
    if not method_route.startswith('/'):
        method_route = '/' + method_route
    if not class_prefix.startswith('/'):
        class_prefix = '/' + class_prefix
    if method_route == class_prefix or method_route.startswith(class_prefix + '/'):
        return method_route
    return '/' + '/'.join(part.strip('/') for part in (class_prefix, method_route) if part.strip('/'))


ENTRY_ONLY_CONTROLLER_DOMAINS = {"index", "home", "main", "landing", "root"}
_ENTRY_ONLY_VIEW_DIRS = set(ENTRY_ONLY_CONTROLLER_DOMAINS)


def _jsp_screen_role(jsp: Path, body: str) -> str:
    stem_low = jsp.stem.lower()
    parent_low = jsp.parent.name.lower()
    low = (body or '').lower()
    if (
        parent_low in _ENTRY_ONLY_VIEW_DIRS
        or stem_low in _ENTRY_ONLY_VIEW_DIRS
        or any(stem_low.startswith(f'{name}form') for name in _ENTRY_ONLY_VIEW_DIRS)
        or '진입 전용 화면' in (body or '')
        or 'location.replace("${pagecontext.request.contextpath}' in low
    ):
        return 'entry'
    if stem_low.endswith('calendar'):
        return 'calendar'
    if any(token in stem_low for token in ('signup', 'register', 'join')):
        return 'signup'
    if 'login' in stem_low and 'integrationguide' not in stem_low and 'certlogin' not in stem_low and 'jwtlogin' not in stem_low:
        return 'login'
    if stem_low.endswith('form'):
        return 'form'
    if stem_low.endswith('list'):
        return 'list'
    if stem_low.endswith(('detail', 'view')):
        return 'detail'
    return 'view'


_NON_DOMAIN_CALENDAR_DIRS = {
    'common', 'layout', 'fragments', 'fragment', 'includes', 'include', 'shared', 'templates', 'template',
    'views', 'generic', 'logininterceptor', 'webmvcconfig', 'config', 'spring', 'mvc', 'authenticinterceptor', 'authinterceptor'
}
_CALENDAR_DOMAIN_HINTS = {'schedule', 'reservation', 'booking', 'room', 'calendar', 'event', 'events'}
_NON_CALENDAR_CRUD_HINTS = {'user', 'member', 'login', 'auth', 'config', 'mapper', 'interceptor', 'service', 'generic', 'authenticinterceptor', 'authinterceptor'}

def _calendar_view_requires_controller(calendar_jsp: Path, domain: str) -> bool:
    low_domain = _canonical_snake_name(domain or '')
    if not low_domain or low_domain in _NON_DOMAIN_CALENDAR_DIRS:
        return False
    if low_domain in _NON_CALENDAR_CRUD_HINTS:
        return False
    if low_domain == 'schedule':
        return True
    return any(token in low_domain for token in _CALENDAR_DOMAIN_HINTS)


def _controller_request_mapping_aliases(body: str, controller: Path) -> List[str]:
    class_map_match = re.search(r'@RequestMapping\(([^)]*)\)', body, re.DOTALL)
    aliases: List[str] = []
    if class_map_match:
        ann = class_map_match.group(1) or ''
        for route_match in re.finditer(r"[\"'](/[^\"']+)[\"']", ann):
            route = (route_match.group(1) or '').strip()
            if route and route not in aliases:
                aliases.append(route)
    if aliases:
        return aliases
    stem = controller.stem[:-10] if controller.stem.endswith('Controller') else controller.stem
    domain = _canonical_camel_name(stem) if stem else ''
    return [f'/{domain}'] if domain else []


def _controller_domain_and_prefix(body: str, controller: Path) -> Dict[str, str]:
    aliases = _controller_request_mapping_aliases(body, controller)
    prefix = aliases[0] if aliases else ''
    domain = prefix.strip('/').split('/')[-1] if prefix.strip('/') else ''
    if not domain:
        stem = controller.stem[:-10] if controller.stem.endswith('Controller') else controller.stem
        domain = _canonical_camel_name(stem) if stem else ''
        prefix = f'/{domain}' if domain else ''
    return {'domain': domain, 'prefix': prefix}

def _controller_is_entry_redirect_only(body: str, controller: Path, domain: str) -> bool:
    stem = controller.stem[:-10] if controller.stem.endswith("Controller") else controller.stem
    key = (domain or stem or "").strip().lower()
    if key not in ENTRY_ONLY_CONTROLLER_DOMAINS and stem.strip().lower() != "index":
        return False
    returns = [item.strip().lower() for item in re.findall(r"return\s+[\"']([^\"']+)[\"']\s*;", body)]
    if not returns:
        return False
    non_redirect = [item for item in returns if not (item.startswith("redirect:") or item.startswith("forward:"))]
    return not non_redirect


def _scan_controller_views(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / "src/main/java"
    if not java_root.exists():
        return issues
    for controller in java_root.rglob("*Controller.java"):
        body = _read_text(controller)
        rel = str(controller.relative_to(project_root))
        info = _controller_domain_and_prefix(body, controller)
        domain = (info.get("domain") or "").strip().lower()
        entry_only = _controller_is_entry_redirect_only(body, controller, domain)
        entry_domain = domain in ENTRY_ONLY_CONTROLLER_DOMAINS or controller.stem.lower() in {"indexcontroller", "homecontroller", "maincontroller", "landingcontroller", "rootcontroller"}
        if entry_only:
            continue
        for match in re.finditer(r'return\s+"([^"]+)"\s*;', body):
            view_name = (match.group(1) or "").strip()
            if not view_name or view_name.startswith("redirect:") or view_name.startswith("forward:"):
                continue
            if entry_domain and view_name.lower().startswith(("index/", "home/", "main/", "landing/", "root/")):
                continue
            jsp_path = project_root / "src/main/webapp/WEB-INF/views" / f"{view_name}.jsp"
            if not jsp_path.exists():
                issues.append(_issue("missing_view", rel, f"controller returns missing jsp: {view_name}", repairable=True, details={"missing_view": view_name}))
    return issues


def _scan_service_wiring(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / "src/main/java"
    if not java_root.exists():
        return issues
    for controller in java_root.rglob("*Controller.java"):
        body = _read_text(controller)
        rel = str(controller.relative_to(project_root))
        for svc in re.findall(r'private\s+final\s+([A-Za-z0-9_]+Service)\s+[A-Za-z0-9_]+\s*;', body):
            svc_files = list(java_root.rglob(f"{svc}.java"))
            impl_files = list(java_root.rglob(f"{svc}Impl.java"))
            if not svc_files:
                issues.append(_issue("missing_service", rel, f"controller references missing service interface: {svc}", repairable=False))
            if not impl_files:
                issues.append(_issue("missing_service_impl", rel, f"controller references missing service impl: {svc}Impl", repairable=False))
    return issues


def _scan_expected_service_pairs(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / "src/main/java"
    if not java_root.exists():
        return issues
    entry_only = {"index", "home", "main", "landing", "root", "view"}
    auth_helper_controllers = {"jwtlogin", "integratedauth"}
    for controller in java_root.rglob("*Controller.java"):
        body = _read_text(controller)
        stem = controller.stem[:-10] if controller.stem.endswith("Controller") else controller.stem
        rel = str(controller.relative_to(project_root))
        stem_low = stem.lower()
        if stem_low in entry_only or stem_low in auth_helper_controllers:
            continue
        info = _controller_domain_and_prefix(body, controller)
        domain = (info.get("domain") or stem or "").strip().lower()
        if domain in entry_only or domain in auth_helper_controllers:
            continue
        has_mapping = bool(re.search(r'@(GetMapping|PostMapping|RequestMapping)', body))
        if not has_mapping:
            continue
        is_safe_view_controller = (
            'AUTOPJ_SAFE_VIEW_CONTROLLER' in body
            or (
                'Service' not in body
                and 'service.' not in body
                and 'private final ' not in body
                and '@ResponseBody' in body
                and re.search(r'return\s+"(?:redirect:)?[A-Za-z0-9_/.-]+"\s*;', body) is not None
            )
        )
        if is_safe_view_controller:
            continue
        svc_files = list(java_root.rglob(f"{stem}Service.java"))
        impl_files = list(java_root.rglob(f"{stem}ServiceImpl.java"))
        if not svc_files:
            issues.append(_issue("missing_service", rel, f"expected service interface missing for controller domain {stem}", repairable=False))
        if not impl_files:
            issues.append(_issue("missing_service_impl", rel, f"expected service impl missing for controller domain {stem}", repairable=False))
    return issues


def _scan_mapper_xml(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / "src/main/java"
    resources_root = project_root / "src/main/resources"
    if not java_root.exists() or not resources_root.exists():
        return issues
    mapper_xmls = {p.name: p for p in resources_root.rglob("*Mapper.xml")}
    for mapper in java_root.rglob("*Mapper.java"):
        expected_xml = f"{mapper.stem}.xml"
        if expected_xml not in mapper_xmls:
            issues.append(_issue("missing_mapper_xml", str(mapper.relative_to(project_root)), f"mapper xml missing for {mapper.name}", repairable=False))
    return issues


def _snake_name(name: str) -> str:
    token = (name or '').strip()
    if not token:
        return ''
    token = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', token)
    token = re.sub(r'[^A-Za-z0-9]+', '_', token)
    return token.strip('_').lower()


def _split_sql_columns(body: str) -> List[str]:
    return [chunk.strip() for chunk in re.split(r",\s*(?![^()]*\))", body or '') if chunk and chunk.strip()]


def _iter_create_table_blocks(sql: str) -> List[tuple[str, str]]:
    body = _read_text(Path(sql)) if isinstance(sql, Path) else str(sql or '')
    out: List[tuple[str, str]] = []
    start_pat = re.compile(r'create\s+table\s+(?:if\s+not\s+exists\s+)?[`"]?([A-Za-z_][\w]*)[`"]?\s*\(', re.IGNORECASE)
    pos = 0
    while True:
        match = start_pat.search(body, pos)
        if not match:
            break
        table = (match.group(1) or '').strip().lower()
        idx = match.end()
        depth = 1
        in_single = False
        in_double = False
        while idx < len(body):
            ch = body[idx]
            prev = body[idx - 1] if idx > 0 else ''
            if ch == "'" and not in_double and prev != '\\':
                in_single = not in_single
            elif ch == '"' and not in_single and prev != '\\':
                in_double = not in_double
            elif not in_single and not in_double:
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    if depth == 0:
                        out.append((table, body[match.end():idx]))
                        pos = idx + 1
                        break
            idx += 1
        else:
            break
    return out


_SCHEMA_GENERATION_METADATA_MARKERS = {'db', 'database', 'dbname', 'schema', 'schemaname', 'schema_name', 'table', 'tablename', 'table_name', 'package', 'packagename', 'package_name', 'frontend', 'frontendtype', 'backend', 'backendtype', 'entity', 'entityname', 'project', 'projectname', 'path', 'filepath', 'filename', 'compile', 'compiled', 'build', 'runtime', 'startup', 'endpoint_smoke'}


def _schema_metadata_columns(columns: List[str]) -> List[str]:
    out: List[str] = []
    for col in columns or []:
        low = str(col or '').strip().lower()
        if low and low in _SCHEMA_GENERATION_METADATA_MARKERS and low not in out:
            out.append(low)
    return out


def _is_ignored_alignment_column(name: str) -> bool:
    low = str(name or '').strip().lower()
    return bool(low) and low in _SCHEMA_GENERATION_METADATA_MARKERS


def _parse_schema_sql_tables(project_root: Path) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    candidates = [
        project_root / 'src/main/resources/schema.sql',
        project_root / 'src/main/resources/db/schema.sql',
        project_root / 'src/main/resources/login-schema.sql',
        project_root / 'src/main/resources/db/login-schema.sql',
        project_root / 'src/main/resources/db/schema-mysql.sql',
    ]
    comment_pat = re.compile(r"\bCOMMENT\s+'((?:[^']|''|\\')*)'", re.IGNORECASE)
    for schema_path in candidates:
        if not schema_path.exists():
            continue
        body = _read_text(schema_path)
        for table, cols_body in _iter_create_table_blocks(body):
            columns: List[str] = []
            comments: Dict[str, str] = {}
            for raw in _split_sql_columns(cols_body):
                line = raw.strip()
                if not line or re.match(r'^(primary|foreign|unique|constraint|key|index)\b', line, re.IGNORECASE):
                    continue
                m = re.match(r'[`"]?([A-Za-z_][\w]*)[`"]?\s+', line)
                if not m:
                    continue
                col = (m.group(1) or '').strip().lower()
                columns.append(col)
                c = comment_pat.search(line)
                if c:
                    comments[col] = (c.group(1) or '').replace("''", "'").strip()
            if table and columns:
                out[table] = {'columns': columns, 'comments': comments, 'path': str(schema_path.relative_to(project_root))}
    return out


def _ensure_tb_table_name(name: str) -> str:
    low = str(name or '').strip().strip('`"').lower()
    low = re.sub(r'[^a-z0-9_]+', '_', low).strip('_')
    if not low:
        return 'tb_item'
    if low in {'tb', 'tb_'}:
        return 'tb_item'
    if low.startswith('tb_'):
        return low
    return f'tb_{low}'


def _scan_table_prefix_contract(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    schema_tables = _parse_schema_sql_tables(project_root)
    for table, info in (schema_tables or {}).items():
        rel = str(info.get('path') or 'src/main/resources/schema.sql')
        if table and not str(table).strip().lower().startswith('tb_'):
            issues.append(_issue('table_prefix_missing', rel, f'all physical table names must start with tb_: {table}', repairable=True, details={'table': table, 'canonical_table': _ensure_tb_table_name(table)}))
    resources_root = project_root / 'src/main/resources'
    if resources_root.exists():
        for mapper_xml in resources_root.rglob('*Mapper.xml'):
            contract = _parse_mapper_contract(mapper_xml)
            table = str(contract.get('table') or '').strip().lower()
            if table and not table.startswith('tb_'):
                issues.append(_issue('table_prefix_missing', str(mapper_xml.relative_to(project_root)), f'mapper xml uses non-tb_ table name: {table}', repairable=True, details={'table': table, 'canonical_table': _ensure_tb_table_name(table)}))
    return issues


def _parse_mapper_contract(mapper_path: Path) -> Dict[str, Any]:
    body = _read_text(mapper_path)
    table_names: List[str] = []
    for pattern in (r'insert\s+into\s+[`"]?([A-Za-z_][\w]*)[`"]?', r'update\s+[`"]?([A-Za-z_][\w]*)[`"]?', r'delete\s+from\s+[`"]?([A-Za-z_][\w]*)[`"]?', r'from\s+[`"]?([A-Za-z_][\w]*)[`"]?'):
        for m in re.finditer(pattern, body, re.IGNORECASE):
            name = (m.group(1) or '').strip().lower()
            if name and name not in table_names:
                table_names.append(name)
    table = table_names[0] if table_names else ''
    specs: List[tuple[str, str, str]] = []
    insert_pat = re.compile(r'insert\s+into\s+[`"]?([A-Za-z_][\w]*)[`"]?\s*\((.*?)\)\s*values\s*\((.*?)\)', re.IGNORECASE | re.DOTALL)
    for m in insert_pat.finditer(body):
        current_table = (m.group(1) or '').strip().lower()
        if table and current_table != table:
            continue
        cols = [c.strip(' `"') for c in _split_sql_columns(m.group(2) or '')]
        vals = [v.strip() for v in _split_sql_columns(m.group(3) or '')]
        for col, val in zip(cols, vals):
            ph = re.search(r'#\{\s*([A-Za-z_][\w]*)\s*\}', val)
            prop = ph.group(1) if ph else ''
            if col:
                specs.append((prop or _snake_name(col), col, 'String'))
    update_pat = re.compile(r'update\s+[`"]?([A-Za-z_][\w]*)[`"]?\s+set\s+(.*?)\s+where\s+', re.IGNORECASE | re.DOTALL)
    for m in update_pat.finditer(body):
        current_table = (m.group(1) or '').strip().lower()
        if table and current_table != table:
            continue
        for raw in _split_sql_columns(m.group(2) or ''):
            mm = re.search(r'[`"]?([A-Za-z_][\w]*)[`"]?\s*=\s*#\{\s*([A-Za-z_][\w]*)\s*\}', raw)
            if mm:
                specs.append((mm.group(2), mm.group(1), 'String'))
    result_pat = re.compile(r'<(?:id|result)\s+[^>]*property=[\"\']([A-Za-z_][\w]*)[\"\'][^>]*column=[\"\']([A-Za-z_][\w]*)[\"\']', re.IGNORECASE)
    for prop, col in result_pat.findall(body):
        specs.append((prop, col, 'String'))
    seen: set[str] = set()
    columns: List[str] = []
    props: List[str] = []
    for prop, col, _ in specs:
        cl = (col or '').strip().lower()
        pr = (prop or '').strip() or _snake_name(cl)
        if cl and cl not in seen:
            seen.add(cl)
            columns.append(cl)
            props.append(pr)
    return {'table': table, 'columns': columns, 'props': props, 'path': str(mapper_path)}




def _sanitize_alignment_columns(mapper_columns: List[str], schema_columns: List[str], vo_columns: List[str]) -> List[str]:
    mapper_cols = [str(c or '').strip().lower() for c in (mapper_columns or []) if str(c or '').strip()]
    schema_cols = [str(c or '').strip().lower() for c in (schema_columns or []) if str(c or '').strip()]
    vo_cols = [str(c or '').strip().lower() for c in (vo_columns or []) if str(c or '').strip()]
    suspicious_only = {'string', 'varchar', 'char', 'text', 'integer', 'number'}
    if not mapper_cols:
        return [col for col in (schema_cols or vo_cols) if not _is_ignored_alignment_column(col)]
    schema_set = set(schema_cols)
    vo_set = set(vo_cols)
    cleaned: List[str] = []
    for col in mapper_cols:
        if _is_ignored_alignment_column(col):
            continue
        if col in suspicious_only and (schema_set or vo_set) and col not in schema_set and col not in vo_set:
            continue
        if col not in cleaned:
            cleaned.append(col)
    fallback = [col for col in (schema_cols or vo_cols or mapper_cols) if not _is_ignored_alignment_column(col)]
    return cleaned or fallback


def _scan_mapper_table_vo_alignment(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    resources_root = project_root / 'src/main/resources'
    java_root = project_root / 'src/main/java'
    if not resources_root.exists() or not java_root.exists():
        return issues
    schema_tables = _parse_schema_sql_tables(project_root)
    vo_map: Dict[str, Dict[str, Any]] = {}
    for vo in java_root.rglob('*VO.java'):
        stem = vo.stem[:-2] if vo.stem.endswith('VO') else vo.stem
        props = _parse_vo_properties(_read_text(vo))
        cols = [_snake_name(item.get('name') or '') for item in props if item.get('name') and item.get('name') != 'serialVersionUID']
        vo_map[stem.lower()] = {'columns': [c for c in cols if c], 'path': str(vo.relative_to(project_root)), 'props': [item.get('name') for item in props if item.get('name') and item.get('name') != 'serialVersionUID']}
    for mapper_xml in resources_root.rglob('*Mapper.xml'):
        contract = _parse_mapper_contract(mapper_xml)
        mapper_columns = [str(c or '').strip().lower() for c in (contract.get('columns') or []) if str(c or '').strip()]
        table = str(contract.get('table') or '').strip().lower()
        if not mapper_columns or not table:
            continue
        stem = mapper_xml.stem[:-6] if mapper_xml.stem.endswith('Mapper') else mapper_xml.stem
        rel = str(mapper_xml.relative_to(project_root))
        schema_info = schema_tables.get(table) or {}
        schema_columns = [str(c or '').strip().lower() for c in (schema_info.get('columns') or []) if str(c or '').strip()]
        vo_info = vo_map.get(stem.lower()) or {}
        vo_columns = [str(c or '').strip().lower() for c in (vo_info.get('columns') or []) if str(c or '').strip()]
        effective_mapper_columns = _sanitize_alignment_columns(mapper_columns, schema_columns, vo_columns)
        metadata_columns = _schema_metadata_columns(schema_columns)
        if metadata_columns:
            issues.append(_issue('schema_generation_metadata_column', rel, f'schema.sql for table {table} must not contain generation metadata columns: {", ".join(metadata_columns)}', repairable=True, details={'table': table, 'mapper_columns': effective_mapper_columns, 'raw_mapper_columns': mapper_columns, 'schema_columns': schema_columns, 'metadata_columns': metadata_columns, 'schema_path': schema_info.get('path') or ''}))
        if schema_columns and set(effective_mapper_columns) != set(schema_columns):
            issues.append(_issue('mapper_table_column_mismatch', rel, f'mapper xml columns for table {table} differ from schema.sql columns', repairable=True, details={'table': table, 'mapper_columns': effective_mapper_columns, 'raw_mapper_columns': mapper_columns, 'schema_columns': schema_columns, 'schema_path': schema_info.get('path') or ''}))
        if vo_columns and set(effective_mapper_columns) != set(vo_columns):
            issues.append(_issue('mapper_vo_column_mismatch', rel, f'mapper xml columns for {stem}VO differ from VO fields', repairable=True, details={'table': table, 'mapper_columns': effective_mapper_columns, 'raw_mapper_columns': mapper_columns, 'vo_columns': vo_columns, 'vo_path': vo_info.get('path') or ''}))
        if schema_columns:
            missing_comments = [col for col in effective_mapper_columns if not str((schema_info.get('comments') or {}).get(col) or '').strip()]
            if missing_comments:
                issues.append(_issue('schema_column_comment_missing', rel, f'schema.sql is missing column comments for table {table}: {", ".join(missing_comments)}', repairable=True, details={'table': table, 'missing_comments': missing_comments, 'mapper_columns': effective_mapper_columns, 'schema_path': schema_info.get('path') or ''}))
    return issues


def _collect_jsp_field_names(body: str) -> List[str]:
    names: List[str] = []
    for pattern in (r'<input[^>]+name="([^"]+)"', r"<input[^>]+name='([^']+)'", r'<select[^>]+name="([^"]+)"', r"<select[^>]+name='([^']+)'", r'<textarea[^>]+name="([^"]+)"', r"<textarea[^>]+name='([^']+)'"):
        for m in re.finditer(pattern, body, re.IGNORECASE):
            name = (m.group(1) or '').strip()
            if name and name not in names:
                names.append(name)
    return names


def _is_temporal_search_field(name: str) -> bool:
    low = str(name or '').strip().lower()
    return bool(low) and ('datetime' in low or low.endswith('date') or low.endswith('dt') or 'date' in low)


def _search_field_variants(name: str) -> List[str]:
    base = str(name or '').strip()
    if not base:
        return []
    variants = [base]
    if _is_temporal_search_field(base):
        variants.extend([
            f'{base}From',
            f'{base}To',
            f'{base}Start',
            f'{base}End',
            f'{base}Begin',
            f'{base}Finish',
        ])
    return variants


def _search_ui_covers_field(names: List[str] | set[str], prop: str) -> bool:
    prop = str(prop or '').strip()
    if not prop:
        return True
    name_set = {str(item or '').strip().lower() for item in (names or []) if str(item or '').strip()}
    variants = [item.lower() for item in _search_field_variants(prop)]
    if prop.lower() in name_set:
        return True
    if _is_temporal_search_field(prop):
        range_groups = [
            (f'{prop}From'.lower(), f'{prop}To'.lower()),
            (f'{prop}Start'.lower(), f'{prop}End'.lower()),
            (f'{prop}Begin'.lower(), f'{prop}Finish'.lower()),
        ]
        if any(start in name_set and end in name_set for start, end in range_groups):
            return True
    return any(variant in name_set for variant in variants)


def _nav_anchor_with_label_exists(body: str, labels: List[str] | tuple[str, ...]) -> bool:
    if not body:
        return False
    pattern = '|'.join(re.escape(str(label)) for label in labels if str(label).strip())
    if not pattern:
        return False
    anchor_re = re.compile(r'<a\b[^>]*>.*?(?:' + pattern + r').*?</a>', re.IGNORECASE | re.DOTALL)
    return bool(anchor_re.search(body))

def _looks_like_search_jsp(body: str) -> bool:
    low = (body or '').lower()
    return any(token in low for token in ('searchform', '검색', '조회', 'search-btn', 'btn-search', 'name="search', "name='search"))


def _canonical_jsp_alias_target(project_root: Path, jsp: Path) -> Path | None:
    rel = jsp.relative_to(project_root)
    parts = list(rel.parts)
    try:
        views_idx = parts.index('views')
    except ValueError:
        return None
    if views_idx + 1 >= len(parts) - 1:
        return None
    domain = parts[views_idx + 1]
    stem = jsp.stem
    suffix = ''
    for candidate in ('Calendar', 'Detail', 'Form', 'List', 'View', 'Edit', 'Login', 'Main', 'Guide'):
        if stem.lower().endswith(candidate.lower()):
            suffix = candidate
            base = stem[:-len(candidate)]
            break
    else:
        base = stem
    canonical_domain = _canonical_camel_name(domain) or domain
    canonical_base = _canonical_camel_name(base) or base
    canonical_stem = f'{canonical_base}{suffix}' if suffix else canonical_base
    target_parts = parts[:]
    target_parts[views_idx + 1] = canonical_domain
    target_parts[-1] = canonical_stem + jsp.suffix
    target = project_root.joinpath(*target_parts)
    if target.resolve() == jsp.resolve():
        return None
    return target if target.exists() else None


def _infer_jsp_domain_and_vo_candidates(jsp: Path) -> List[str]:
    parts = list(jsp.parts)
    try:
        views_idx = parts.index('views')
        domain = (parts[views_idx + 1] if views_idx + 1 < len(parts) - 1 else '').strip()
    except ValueError:
        domain = ''
    stem = jsp.stem
    base = re.sub(r'(List|Detail|Form|Calendar|View|Edit|Login|Main|Guide)$', '', stem, flags=re.IGNORECASE)
    candidates: List[str] = []
    for token in (domain, base, stem, _canonical_camel_name(domain), _canonical_camel_name(base), _canonical_snake_name(domain), _canonical_snake_name(base)):
        tok = (token or '').strip()
        if not tok:
            continue
        pascal = ''.join(part[:1].upper() + part[1:] for part in _canonical_snake_name(tok).split('_') if part) or (tok[:1].upper() + tok[1:])
        for key in (tok, pascal, _canonical_camel_name(tok), _canonical_snake_name(tok)):
            key = str(key or '').strip()
            if not key:
                continue
            vo_key = f'{key}VO'.lower()
            if vo_key not in candidates:
                candidates.append(vo_key)
    return candidates


def _parse_mapper_props_by_domain(project_root: Path) -> Dict[str, List[str]]:
    resources_root = project_root / 'src/main/resources'
    props_by_domain: Dict[str, List[str]] = {}
    if not resources_root.exists():
        return props_by_domain
    for mapper_xml in resources_root.rglob('*Mapper.xml'):
        contract = _parse_mapper_contract(mapper_xml)
        stem = mapper_xml.stem[:-6] if mapper_xml.stem.endswith('Mapper') else mapper_xml.stem
        domain = stem.lower()
        props = [str(p or '').strip() for p in (contract.get('props') or []) if str(p or '').strip()]
        if domain and props:
            for key in {domain, _domain_canonical_key(domain), _canonical_snake_name(domain), _canonical_camel_name(domain)}:
                if not key:
                    continue
                props_by_domain.setdefault(key, [])
                for prop in props:
                    if prop not in props_by_domain[key]:
                        props_by_domain[key].append(prop)
    return props_by_domain


_JSP_HELPER_COLLECTION_PROPS = {
    'calendarcells': {'date', 'day', 'eventCount', 'events', 'currentMonth', 'today'},
    'calendarCells': {'date', 'day', 'eventCount', 'events', 'currentMonth', 'today'},
}


def _collect_jsp_helper_var_props(body: str) -> Dict[str, set[str]]:
    helper: Dict[str, set[str]] = {}
    if not body:
        return helper
    foreach_pat = re.compile(
        r"<c:forEach[^>]*\bvar=[\"']([A-Za-z_][A-Za-z0-9_]*)[\"'][^>]*\bitems=[\"']\s*\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\s*[\"'][^>]*>",
        re.IGNORECASE,
    )
    for var_name, items_name in foreach_pat.findall(body):
        props = _JSP_HELPER_COLLECTION_PROPS.get(items_name) or _JSP_HELPER_COLLECTION_PROPS.get(items_name.lower())
        if props:
            helper.setdefault(var_name, set()).update(props)
    return helper


def _collect_jsp_property_refs(body: str) -> Dict[str, List[str]]:
    refs: Dict[str, List[str]] = {}
    if not body:
        return refs
    skip_vars = {'param', 'paramValues', 'sessionScope', 'requestScope', 'pageScope', 'applicationScope', 'cookie', 'header', 'initParam'}
    patterns = [
        r'\$\{\s*([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*\}',
        r'#\{\s*([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*\}',
    ]
    for pattern in patterns:
        for var_name, prop in re.findall(pattern, body):
            if var_name in skip_vars:
                continue
            refs.setdefault(var_name, [])
            if prop not in refs[var_name]:
                refs[var_name].append(prop)
    return refs


def _suggest_property_replacement(missing_prop: str, available_props: List[str]) -> str:
    available = [str(p or '').strip() for p in (available_props or []) if str(p or '').strip()]
    if not available:
        return ''
    low_map = {prop.lower(): prop for prop in available}
    groups = [
        ({'remark', 'memo', 'note', 'content', 'description', 'body'}, ('content', 'description', 'memo', 'note', 'remark', 'purpose', 'title', 'name')),
        ({'username', 'membername', 'loginname', 'name'}, ('userName', 'memberName', 'loginName', 'name')),
        ({'title', 'subject', 'name', 'purpose'}, ('title', 'subject', 'purpose', 'name', 'description')),
    ]
    low_missing = (missing_prop or '').strip().lower()
    if low_missing == 'id':
        preferred_id_props = [
            'memberId', 'loginId', 'userId', 'accountId', 'customerId', 'adminId',
            'scheduleId', 'reservationId', 'roomId', 'boardId', 'noticeId', 'postId',
        ]
        for cand in preferred_id_props:
            hit = low_map.get(cand.lower())
            if hit:
                return hit
        suffix_hits = [prop for prop in available if prop.lower().endswith('id') and prop.lower() not in {'id', 'password', 'loginpassword', 'login_password'}]
        if len(suffix_hits) == 1:
            return suffix_hits[0]
        if suffix_hits:
            return suffix_hits[0]
    for group, preferred in groups:
        if low_missing in group:
            for cand in preferred:
                hit = low_map.get(cand.lower())
                if hit:
                    return hit
    exact = low_map.get(low_missing)
    if exact:
        return exact
    close = difflib.get_close_matches(missing_prop, available, n=1, cutoff=0.72)
    return close[0] if close else ''


def _scan_jsp_vo_property_mismatch(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    view_root = project_root / 'src/main/webapp/WEB-INF/views'
    java_root = project_root / 'src/main/java'
    if not view_root.exists() or not java_root.exists():
        return issues
    vo_map: Dict[str, Dict[str, Any]] = {}
    for vo in java_root.rglob('*VO.java'):
        props = _parse_vo_properties(_read_text(vo))
        vo_map[vo.stem.lower()] = {
            'path': str(vo.relative_to(project_root)),
            'props': [p.get('name') for p in props if p.get('name')],
        }
    mapper_props_by_domain = _parse_mapper_props_by_domain(project_root)
    for jsp in view_root.rglob('*.jsp'):
        if _canonical_jsp_alias_target(project_root, jsp):
            continue
        body = _read_text(jsp)
        refs = _collect_jsp_property_refs(body)
        helper_var_props = _collect_jsp_helper_var_props(body)
        if not refs:
            continue
        candidates = _infer_jsp_domain_and_vo_candidates(jsp)
        vo_info = next((vo_map.get(key) for key in candidates if vo_map.get(key)), None)
        domain_key = ''
        for key in candidates:
            if key.endswith('vo'):
                domain_key = key[:-2]
                break
        domain_key = _domain_canonical_key(domain_key) or domain_key
        if not vo_info:
            continue
        available_props = [str(p or '').strip() for p in (vo_info.get('props') or []) if str(p or '').strip()]
        mapper_props = list(mapper_props_by_domain.get(domain_key, [])) if domain_key else []
        available_set = set(available_props)
        missing_props: List[str] = []
        missing_by_var: Dict[str, List[str]] = {}
        suggestions: Dict[str, str] = {}
        for var_name, props in refs.items():
            helper_props = helper_var_props.get(var_name) or set()
            for prop in props:
                if prop in available_set or prop in helper_props:
                    continue
                # allow mapper-backed view props even before VO repair so calendar/detail JSPs do not fail on first pass
                low_prop = str(prop or '').strip().lower()
                if prop in mapper_props and low_prop not in {'db', 'schemaname', 'schema_name', 'database', 'tablename', 'packagename', 'frontendtype', 'backendtype', 'password', 'loginpassword', 'login_password', 'passwd', 'pwd'}:
                    continue
                missing_by_var.setdefault(var_name, [])
                missing_by_var[var_name].append(prop)
                if prop not in missing_props:
                    missing_props.append(prop)
                    suggestion = _suggest_property_replacement(prop, available_props or mapper_props)
                    if suggestion:
                        suggestions[prop] = suggestion
        if missing_props:
            issues.append(_issue(
                'jsp_vo_property_mismatch',
                str(jsp.relative_to(project_root)),
                f'jsp references undefined VO properties: {", ".join(missing_props)}',
                repairable=True,
                details={
                    'vo_path': vo_info.get('path') or '',
                    'available_props': available_props,
                    'mapper_props': mapper_props,
                    'missing_props': missing_props,
                    'missing_props_by_var': missing_by_var,
                    'suggested_replacements': suggestions,
                },
            ))
    return issues



_GENERATION_METADATA_MARKERS = {'db', 'schemaname', 'schema_name', 'database', 'tablename', 'table_name', 'packagename', 'package_name', 'frontendtype', 'backendtype'}
_AUTH_SENSITIVE_MARKERS = {'password', 'passwd', 'pwd', 'loginpassword', 'login_password'}
_SYNTHETIC_PLACEHOLDER_RE = re.compile(r'^(?:repeat\d+|section|temp[a-z0-9_]*|sample[a-z0-9_]*|example[a-z0-9_]*)$', re.IGNORECASE)


def _normalize_field_key(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', str(name or '').strip().lower())


def _is_generation_metadata_field(name: str) -> bool:
    return _normalize_field_key(name) in _GENERATION_METADATA_MARKERS


def _is_auth_sensitive_field(name: str) -> bool:
    return _normalize_field_key(name) in _AUTH_SENSITIVE_MARKERS


def _is_non_auth_search_forbidden_field(name: str) -> bool:
    return _is_auth_sensitive_field(name) or _is_generation_metadata_field(name) or bool(_SYNTHETIC_PLACEHOLDER_RE.match(str(name or '').strip()))

def _scan_search_fields_cover_all_columns(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    view_root = project_root / 'src/main/webapp/WEB-INF/views'
    java_root = project_root / 'src/main/java'
    if not view_root.exists() or not java_root.exists():
        return issues
    vo_map: Dict[str, List[str]] = {}
    search_vo_map: Dict[str, List[str]] = {}
    for vo in java_root.rglob('*VO.java'):
        stem = vo.stem[:-2] if vo.stem.endswith('VO') else vo.stem
        props = [item.get('name') for item in _parse_vo_properties(_read_text(vo)) if item.get('name') and item.get('name') != 'serialVersionUID']
        key = stem.lower()
        vo_map[key] = props
        if key.endswith('search'):
            search_vo_map[key[:-6]] = props
    for jsp in view_root.rglob('*List.jsp'):
        rel = str(jsp.relative_to(project_root)).replace('\\', '/')
        stem = jsp.stem[:-4] if jsp.stem.endswith('List') else jsp.stem
        stem_low = stem.lower()
        if stem_low in {'login', 'auth', 'signin', 'logout'} or '/views/login/' in rel.lower():
            continue
        body = _read_text(jsp)
        props = search_vo_map.get(stem_low) or vo_map.get(stem_low) or []
        if not props:
            continue
        names = set(_collect_jsp_field_names(body))
        filtered_props = []
        for prop in props:
            if _is_non_auth_search_forbidden_field(prop):
                continue
            filtered_props.append(prop)
        if not filtered_props:
            continue
        if not _looks_like_search_jsp(body):
            issues.append(_issue('search_ui_missing', rel, f'list jsp is missing concrete search conditions for {stem}', repairable=True, details={'missing_fields': filtered_props, 'vo_props': filtered_props}))
            continue
        missing = [prop for prop in filtered_props if not _search_ui_covers_field(names, prop) and not _is_non_auth_search_forbidden_field(prop)]
        if missing:
            issues.append(_issue('search_fields_incomplete', rel, f'search UI must expose all search fields for {stem}: {", ".join(missing)}', repairable=True, details={'missing_fields': missing, 'vo_props': filtered_props}))
    return issues
def _scan_form_fields_cover_all_columns(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    view_root = project_root / 'src/main/webapp/WEB-INF/views'
    java_root = project_root / 'src/main/java'
    if not view_root.exists() or not java_root.exists():
        return issues
    vo_map: Dict[str, List[str]] = {}
    for vo in java_root.rglob('*VO.java'):
        stem = vo.stem[:-2] if vo.stem.endswith('VO') else vo.stem
        props = [item.get('name') for item in _parse_vo_properties(_read_text(vo)) if item.get('name') and item.get('name') != 'serialVersionUID']
        vo_map[stem.lower()] = props
    signup_candidates = [jsp for jsp in view_root.rglob('*.jsp') if any(token in jsp.stem.lower() for token in ('signup', 'register', 'join'))]
    for jsp in list(view_root.rglob('*Form.jsp')) + signup_candidates:
        rel = str(jsp.relative_to(project_root)).replace('\\', '/')
        body = _read_text(jsp)
        candidates = _infer_jsp_domain_and_vo_candidates(jsp)
        props: List[str] = []
        fallback_keys = [jsp.parent.name.lower(), jsp.stem.lower(), re.sub(r'(form|detail|list|calendar|view|edit|login|main|guide)$', '', jsp.stem.lower())]
        for key in list(candidates) + fallback_keys:
            info = vo_map.get((key or '').lower())
            if info:
                props = info
                break
        if not props:
            continue
        names = set(_collect_jsp_field_names(body))
        required = [prop for prop in props if not _is_generation_metadata_field(prop)]
        missing = [prop for prop in required if prop not in names]
        if missing:
            stem = jsp.stem[:-4] if jsp.stem.endswith('Form') else jsp.stem
            issues.append(_issue('form_fields_incomplete', rel, f'form UI must expose all VO/table columns for {stem}: {", ".join(missing)}', repairable=True, details={'missing_fields': missing, 'vo_props': required}))
    return issues


def _scan_boolean_getters(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / "src/main/java"
    for vo in java_root.rglob("*VO.java"):
        body = _read_text(vo)
        rel = str(vo.relative_to(project_root))
        for match in re.finditer(r'private\s+(Boolean|boolean)\s+(\w+)\s*;', body):
            prop = match.group(2)
            cap = prop[:1].upper() + prop[1:]
            has_get = re.search(rf'public\s+(?:Boolean|boolean)\s+get{re.escape(cap)}\s*\(', body)
            has_is = re.search(rf'public\s+(?:Boolean|boolean)\s+is{re.escape(cap)}\s*\(', body)
            if has_get and has_is:
                issues.append(_issue("duplicate_boolean_getter", rel, f"duplicate get/is getter for property {prop}"))
    return issues


def _camel(name: str) -> str:
    name = (name or '').strip()
    return name[:1].upper() + name[1:] if name else ''


def _parse_vo_properties(vo_body: str) -> List[Dict[str, str]]:
    props: List[Dict[str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(r'private\s+([A-Za-z0-9_$.<>]+)\s+(\w+)\s*;', vo_body):
        type_name = (m.group(1) or '').strip()
        prop = (m.group(2) or '').strip()
        if not prop or prop in seen:
            continue
        seen.add(prop)
        props.append({'name': prop, 'type': type_name})
    return props


def _getter_name(prop: str, type_name: str = '') -> str:
    cap = _camel(prop)
    if type_name in {'boolean', 'Boolean'}:
        return f'is{cap}'
    return f'get{cap}'


def _choose_prop(props: List[Dict[str, str]], preferred_names: List[str], contains_tokens: List[str], type_tokens: List[str] | None = None) -> str:
    if not props:
        return ''
    preferred = [p.lower() for p in preferred_names]
    for cand in preferred:
        for item in props:
            if item['name'].lower() == cand:
                return item['name']
    for token in contains_tokens:
        low_token = token.lower()
        for item in props:
            if low_token in item['name'].lower():
                return item['name']
    if type_tokens:
        for item in props:
            t = item['type'].lower()
            if any(tok.lower() in t for tok in type_tokens):
                return item['name']
    return ''


def _infer_id_field(props: List[Dict[str, str]]) -> Dict[str, str]:
    if not props:
        return {}

    def _is_boolean_like(type_name: str) -> bool:
        simple = (type_name or '').strip().split('.')[-1].lower()
        return simple in {'boolean', 'bool'}

    exact = {'id', 'seq', 'no'}
    non_boolean_props = [item for item in props if not _is_boolean_like(item.get('type') or '')]
    candidates = non_boolean_props or props
    for item in candidates:
        if item['name'].lower() in exact:
            return item
    for item in candidates:
        low = item['name'].lower()
        if low.endswith('id') or low.endswith('_id'):
            return item
    for item in candidates:
        low = item['name'].lower()
        if 'id' in low or 'seq' in low or low.endswith('no'):
            return item
    return candidates[0] if candidates else {}


def _parse_service_method_signatures(service_body: str) -> Dict[str, Dict[str, Any]]:
    methods: Dict[str, Dict[str, Any]] = {}
    pat = re.compile(r'([A-Za-z0-9_$.<>]+)\s+(\w+)\s*\(([^)]*)\)\s*(?:throws\s+[^;]+)?;')
    for m in pat.finditer(service_body):
        method_name = (m.group(2) or '').strip()
        params_raw = (m.group(3) or '').strip()
        params: List[Dict[str, str]] = []
        if params_raw:
            for chunk in [c.strip() for c in params_raw.split(',') if c.strip()]:
                cleaned = re.sub(r'@[A-Za-z0-9_$.]+(?:\([^)]*\))?\s*', '', chunk).strip()
                parts = cleaned.split()
                if len(parts) >= 2:
                    params.append({'type': parts[-2].strip(), 'name': parts[-1].strip()})
        methods[method_name] = {'params': params}
    return methods


def _parse_controller_method_blocks(body: str) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    sig_re = re.compile(
        r'(@(?:GetMapping|PostMapping|RequestMapping)[\s\S]{0,200}?)\s+public\s+[A-Za-z0-9_$.<>]+\s+(\w+)\s*\(([^)]*)\)\s*(?:throws\s+[^\{]+)?\{',
        re.DOTALL,
    )
    for m in sig_re.finditer(body):
        start_idx = m.end() - 1
        depth = 0
        end_idx = -1
        i = start_idx
        while i < len(body):
            ch = body[i]
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break
            i += 1
        if end_idx == -1:
            continue
        blocks.append({
            'annotation_block': m.group(1) or '',
            'method_name': m.group(2) or '',
            'params_raw': m.group(3) or '',
            'body': body[start_idx + 1:end_idx] or '',
        })
    return blocks


def _parse_param_defs(params_raw: str) -> Dict[str, Dict[str, str]]:
    result: Dict[str, Dict[str, str]] = {}
    if not params_raw.strip():
        return result
    chunks = [c.strip() for c in params_raw.split(',') if c.strip()]
    for chunk in chunks:
        req_name = ''
        m_req = re.search(r'@RequestParam\(([^)]*)\)', chunk)
        if m_req:
            args = m_req.group(1) or ''
            lit = re.search(r"[\"\']([^\"\']+)[\"\']", args)
            if lit:
                req_name = lit.group(1).strip()
        cleaned = re.sub(r'@[A-Za-z0-9_$.]+(?:\([^)]*\))?\s*', '', chunk).strip()
        parts = cleaned.split()
        if len(parts) >= 2:
            type_name = parts[-2].strip()
            var_name = parts[-1].strip()
            result[var_name] = {'type': type_name, 'request_param_name': req_name}
    return result


def _scan_controller_service_signature_mismatch(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / 'src/main/java'
    if not java_root.exists():
        return issues

    service_defs: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for service_file in java_root.rglob('*Service.java'):
        service_defs[service_file.stem] = _parse_service_method_signatures(_read_text(service_file))

    vo_id_defs: Dict[str, Dict[str, str]] = {}
    for vo in java_root.rglob('*VO.java'):
        stem = vo.stem[:-2] if vo.stem.endswith('VO') else vo.stem
        props = _parse_vo_properties(_read_text(vo))
        id_field = _infer_id_field(props)
        if id_field:
            vo_id_defs[stem.lower()] = {'name': id_field.get('name') or '', 'type': id_field.get('type') or ''}

    service_field_re = re.compile(r'private\s+(?:final\s+)?([A-Za-z0-9_]+Service)\s+(\w+)\s*;')

    for controller in java_root.rglob('*Controller.java'):
        body = _read_text(controller)
        rel = str(controller.relative_to(project_root))
        stem = controller.stem[:-10] if controller.stem.endswith('Controller') else controller.stem
        vo_id = vo_id_defs.get(stem.lower()) or {}
        service_fields = {m.group(2): m.group(1) for m in service_field_re.finditer(body)}
        if not service_fields:
            continue
        method_blocks = _parse_controller_method_blocks(body)
        for block in method_blocks:
            param_defs = _parse_param_defs(block.get('params_raw') or '')
            method_body = block.get('body') or ''
            for service_var, service_name in service_fields.items():
                sigs = service_defs.get(service_name) or {}
                for call in re.finditer(rf'\b{re.escape(service_var)}\.(\w+)\s*\(\s*(\w+)\s*\)', method_body):
                    method_name = call.group(1)
                    arg_name = call.group(2)
                    sig = sigs.get(method_name) or {}
                    params = sig.get('params') or []
                    if len(params) != 1:
                        continue
                    expected = params[0]
                    current = param_defs.get(arg_name)
                    if not current:
                        continue
                    expected_type = (expected.get('type') or '').strip()
                    current_type = (current.get('type') or '').strip()
                    if expected_type and current_type and expected_type != current_type:
                        expected_param_name = (vo_id.get('name') or expected.get('name') or arg_name).strip()
                        issues.append(_issue(
                            'controller_service_signature_mismatch',
                            rel,
                            f'controller passes {current_type} to {service_name}.{method_name} but service expects {expected_type}',
                            repairable=True,
                            details={
                                'service_name': service_name,
                                'service_var': service_var,
                                'service_method': method_name,
                                'arg_name': arg_name,
                                'current_type': current_type,
                                'expected_type': expected_type,
                                'current_request_param_name': current.get('request_param_name') or '',
                                'expected_request_param_name': expected_param_name,
                            },
                        ))
    return issues


def _scan_undefined_vo_getter_usage(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / 'src/main/java'
    if not java_root.exists():
        return issues
    vo_map: Dict[str, Dict[str, Any]] = {}
    for vo in java_root.rglob('*VO.java'):
        body = _read_text(vo)
        simple = vo.stem
        props = _parse_vo_properties(body)
        getters = {_getter_name(p['name'], p['type']) for p in props}
        vo_map[simple.lower()] = {
            'path': str(vo.relative_to(project_root)),
            'props': props,
            'getters': getters,
        }
    for controller in java_root.rglob('*Controller.java'):
        body = _read_text(controller)
        rel = str(controller.relative_to(project_root))
        stem = controller.stem[:-10] if controller.stem.endswith('Controller') else controller.stem
        vo_info = vo_map.get(f'{stem}vo'.lower())
        if not vo_info:
            continue
        if '.getId()' not in body or 'getId' in (vo_info.get('getters') or set()):
            continue
        props = list(vo_info.get('props') or [])
        id_prop = _choose_prop(props, ['id'], ['id', 'seq', 'no'])
        date_prop = _choose_prop(props, ['startDatetime', 'startDate', 'reservationDate', 'eventDate', 'scheduleDate', 'targetDate', 'date'], ['datetime', 'date', 'time'], ['date', 'localdate', 'localdatetime', 'timestamp'])
        status_prop = _choose_prop(props, ['statusCd', 'statusCode', 'status', 'state'], ['status', 'state', 'step', 'phase'])
        priority_prop = _choose_prop(props, ['priorityCd', 'priorityCode', 'priority', 'importanceCd', 'importance'], ['priority', 'importance', 'rank'])
        details = {
            'vo_path': vo_info.get('path') or '',
            'vo_class': f'{stem}VO',
            'available_props': [p['name'] for p in props],
            'suggested_id_getter': _getter_name(id_prop) if id_prop else '',
            'suggested_date_getter': _getter_name(date_prop) if date_prop else '',
            'suggested_status_getter': _getter_name(status_prop) if status_prop else '',
            'suggested_priority_getter': _getter_name(priority_prop) if priority_prop else '',
        }
        issues.append(_issue(
            'undefined_vo_getter_usage',
            rel,
            f'controller uses undefined getter getId() for {stem}VO',
            repairable=True,
            details=details,
        ))
    return issues


def _scan_id_type_mismatch(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / "src/main/java"
    if not java_root.exists():
        return issues
    vo_defs: Dict[str, Dict[str, str]] = {}
    for vo in java_root.rglob("*VO.java"):
        props = _parse_vo_properties(_read_text(vo))
        id_field = _infer_id_field(props)
        if id_field:
            stem = vo.stem[:-2] if vo.stem.endswith("VO") else vo.stem
            vo_defs[stem.lower()] = {'name': id_field.get('name') or '', 'type': id_field.get('type') or ''}
    for controller in java_root.rglob("*Controller.java"):
        body = _read_text(controller)
        rel = str(controller.relative_to(project_root))
        stem = controller.stem[:-10] if controller.stem.endswith("Controller") else controller.stem
        vo_def = vo_defs.get(stem.lower())
        if not vo_def:
            continue
        expected_type = vo_def.get('type') or ''
        expected_name = vo_def.get('name') or 'id'
        for match in re.finditer(r'@RequestParam\(([^)]*)\)\s+([A-Za-z0-9_$.<>]+)\s+(\w+)', body):
            args, ctrl_type, var_name = match.groups()
            lit = re.search(r"[\"\']([^\"\']+)[\"\']", args or "")
            req_name = (lit.group(1).strip() if lit else var_name).strip()
            if req_name not in {'id', expected_name} and var_name not in {'id', expected_name}:
                continue
            if ctrl_type != expected_type:
                issues.append(_issue(
                    'id_type_mismatch',
                    rel,
                    f'controller id type {ctrl_type} differs from VO id type {expected_type}',
                    repairable=True,
                    details={
                        'current_type': ctrl_type,
                        'expected_type': expected_type,
                        'current_var_name': var_name,
                        'expected_var_name': expected_name,
                        'current_request_param_name': req_name,
                        'expected_request_param_name': expected_name,
                    },
                ))
                break
    return issues

def _scan_optional_param_guard_mismatch(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / "src/main/java"
    if not java_root.exists():
        return issues

    def _normalize_java_type(type_name: str) -> str:
        simple = (type_name or "").strip().split('.')[-1]
        return {
            'Long': 'Long',
            'long': 'long',
            'Integer': 'Integer',
            'int': 'int',
            'String': 'String',
        }.get(simple, simple)

    for controller in java_root.rglob("*Controller.java"):
        body = _read_text(controller)
        rel = str(controller.relative_to(project_root))
        for block in _parse_controller_method_blocks(body):
            params = _parse_param_defs(block.get('params_raw') or '')
            method_body = block.get('body') or ''
            for var_name, info in params.items():
                current_type = _normalize_java_type(info.get('type') or '')
                expected_guard = ''
                if current_type == 'String':
                    expected_guard = f'{var_name} != null && !{var_name}.isBlank()'
                    bad_patterns = [rf'\b{re.escape(var_name)}\.longValue\s*\(', rf'\b{re.escape(var_name)}\.intValue\s*\(']
                elif current_type == 'Long':
                    expected_guard = f'{var_name} != null && {var_name}.longValue() != 0L'
                    bad_patterns = [rf'\b{re.escape(var_name)}\.isBlank\s*\(', rf'\b{re.escape(var_name)}\.trim\s*\(']
                elif current_type == 'Integer':
                    expected_guard = f'{var_name} != null && {var_name}.intValue() != 0'
                    bad_patterns = [rf'\b{re.escape(var_name)}\.isBlank\s*\(', rf'\b{re.escape(var_name)}\.trim\s*\(']
                elif current_type == 'long':
                    expected_guard = f'{var_name} != 0L'
                    bad_patterns = [rf'\b{re.escape(var_name)}\.isBlank\s*\(', rf'\b{re.escape(var_name)}\.trim\s*\(', rf'\b{re.escape(var_name)}\.longValue\s*\(']
                elif current_type == 'int':
                    expected_guard = f'{var_name} != 0'
                    bad_patterns = [rf'\b{re.escape(var_name)}\.isBlank\s*\(', rf'\b{re.escape(var_name)}\.trim\s*\(', rf'\b{re.escape(var_name)}\.intValue\s*\(']
                else:
                    continue
                for pattern in bad_patterns:
                    if re.search(pattern, method_body):
                        issues.append(_issue(
                            'optional_param_guard_mismatch',
                            rel,
                            f'controller optional param guard is incompatible with {current_type} parameter {var_name}',
                            repairable=True,
                            details={
                                'current_type': current_type,
                                'current_var_name': var_name,
                                'expected_guard': expected_guard,
                            },
                        ))
                        break
    return issues


def _scan_route_param_consistency(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / "src/main/java"
    view_root = project_root / "src/main/webapp/WEB-INF/views"
    if not java_root.exists() or not view_root.exists():
        return issues

    method_block_re = re.compile(
        r"@(?:GetMapping|PostMapping|RequestMapping)\(([^\)]*)\)([\s\S]{0,240}?\{)",
        re.DOTALL,
    )

    for controller in java_root.rglob("*Controller.java"):
        body = _read_text(controller)
        rel = str(controller.relative_to(project_root))
        info = _controller_domain_and_prefix(body, controller)
        domain = info["domain"]
        prefixes = _controller_request_mapping_aliases(body, controller)
        if not domain:
            continue
        route_params: Dict[str, str] = {}
        for mm in method_block_re.finditer(body):
            ann_args = mm.group(1) or ''
            block = (ann_args or '') + "\n" + (mm.group(2) or '')
            routes = [
                (route_match.group(1) or '').strip()
                for route_match in re.finditer(r"[\"'](/[^\"']+\.do)[\"']", ann_args)
                if (route_match.group(1) or '').strip()
            ]
            if not routes:
                continue
            names = re.findall(r"@RequestParam\(([^\)]*)\)", block)
            req_names: List[str] = []
            for args in names:
                lit = re.search(r"[\"']([^\"']+)[\"']", args)
                if lit:
                    req_names.append(lit.group(1).strip())
            if len(req_names) == 1:
                for prefix in prefixes or ['']:
                    for route in routes:
                        full_route = _combine_controller_route(prefix, route)
                        if full_route:
                            route_params[full_route] = req_names[0]
        if not route_params:
            continue
        jsp_dir = view_root / domain
        if not jsp_dir.exists():
            continue
        mismatched_paths: List[str] = []
        mismatched_found: Dict[str, List[str]] = {}
        for jsp in jsp_dir.glob("*.jsp"):
            jsp_body = _read_text(jsp)
            jsp_rel = str(jsp.relative_to(project_root))
            for route, expected in route_params.items():
                query_re = re.compile(rf"<c:url\s+value=[\"\']{re.escape(route)}[\"\']\s*/>\?([A-Za-z0-9_]+)=", re.IGNORECASE)
                for m in query_re.finditer(jsp_body):
                    actual = m.group(1)
                    if actual != expected:
                        mismatched_paths.append(jsp_rel)
                        mismatched_found.setdefault(route, []).append(actual)
                form_re = re.compile(
                    rf'<form[^>]*action="[^"]*{re.escape(route)}[^"]*"[^>]*>.*?<input[^>]*type="hidden"[^>]*name="([^"]+)"',
                    re.IGNORECASE | re.DOTALL,
                )
                for m in form_re.finditer(jsp_body):
                    actual = m.group(1)
                    if actual != expected:
                        mismatched_paths.append(jsp_rel)
                        mismatched_found.setdefault(route, []).append(actual)
        if mismatched_paths:
            issues.append(
                _issue(
                    "route_param_mismatch",
                    rel,
                    f"controller request params do not match jsp route parameters in {domain}",
                    repairable=True,
                    details={
                        "domain": domain,
                        "route_params": route_params,
                        "jsp_paths": sorted(set(mismatched_paths)),
                        "found_params": {k: sorted(set(v)) for k, v in mismatched_found.items()},
                    },
                )
            )
    return issues


def _scan_delete_ui(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / "src/main/java"
    view_root = project_root / "src/main/webapp/WEB-INF/views"
    if not java_root.exists() or not view_root.exists():
        return issues
    for controller in java_root.rglob("*Controller.java"):
        body = _read_text(controller)
        rel = str(controller.relative_to(project_root))
        if not re.search(r'@(PostMapping|RequestMapping)\(\s*"/delete\.do"', body):
            continue
        stem = controller.stem[:-10] if controller.stem.endswith("Controller") else controller.stem
        jsp_dir = next((p for p in view_root.rglob(stem.lower()) if p.is_dir()), None)
        if not jsp_dir:
            issues.append(_issue("missing_delete_ui", rel, f"delete endpoint exists but jsp folder missing for {stem}", repairable=False))
            continue
        found = False
        for jsp in jsp_dir.glob("*.jsp"):
            jsp_body = _read_text(jsp)
            if any(token in jsp_body for token in ("delete.do", "remove.do", "삭제", "Delete")):
                found = True
                break
        if not found:
            issues.append(_issue("missing_delete_ui", rel, f"delete endpoint exists but delete UI is missing in {jsp_dir.name}", repairable=True))
    return issues


def _scan_nested_forms(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    tag_re = re.compile(r'<(/?)form\b', re.IGNORECASE)
    for jsp in (project_root / "src/main/webapp/WEB-INF/views").rglob("*.jsp"):
        body = _read_text(jsp)
        depth = 0
        for match in tag_re.finditer(body):
            closing = bool(match.group(1))
            if not closing:
                depth += 1
                if depth > 1:
                    issues.append(_issue("nested_form", str(jsp.relative_to(project_root)), "jsp contains a form nested inside another form", repairable=True))
                    break
            elif depth > 0:
                depth -= 1
    return issues


def _scan_invalid_action_wrappers(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    wrapper_re = re.compile(r'<(div|span|section|article)\b[^>]*\saction\s*=\s*[""][^""]*[""][^>]*>', re.IGNORECASE)
    for jsp in (project_root / "src/main/webapp/WEB-INF/views").rglob("*.jsp"):
        body = _read_text(jsp)
        if wrapper_re.search(body):
            issues.append(_issue("invalid_action_wrapper", str(jsp.relative_to(project_root)), "non-form jsp tag uses action attribute", repairable=True))
    return issues






def _has_orphan_closing_tag(body: str, tag_name: str) -> bool:
    pattern = re.compile(rf'(?is)<{re.escape(tag_name)}\b[^>]*>|</{re.escape(tag_name)}\s*>')
    depth = 0
    for match in pattern.finditer(body or ''):
        token = match.group(0) or ''
        is_closing = token.lstrip().startswith('</')
        is_self_closing = token.rstrip().endswith('/>')
        if is_closing:
            if depth <= 0:
                return True
            depth -= 1
        elif not is_self_closing:
            depth += 1
    return False

def _scan_malformed_jsp_structure(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    view_root = project_root / "src/main/webapp/WEB-INF/views"
    if not view_root.exists():
        return issues
    leading_close_re = re.compile(
        r'^\s*(?:<%@[^%]*%>\s*|<!--.*?-->\s*|<jsp:[^>]+>\s*|<html[^>]*>\s*|</?head[^>]*>\s*|<body[^>]*>\s*|<%@\s*include[^%]*header\.jsp\s*%>\s*|<%@\s*include[^%]*leftnav\.jsp\s*%>\s*)*(</(?:div|section|article|aside|form|table|tr|td|ul|li|nav)>)',
        re.IGNORECASE | re.DOTALL,
    )
    for jsp in view_root.rglob("*.jsp"):
        body = _read_text(jsp)
        rel = str(jsp.relative_to(project_root))
        if _is_jsp_validation_partial(rel):
            continue
        if _is_structural_views_crud_jsp(jsp, project_root):
            issues.append(_issue('jsp_structural_views_artifact', rel, 'structural views directory must not contain CRUD jsp artifact', repairable=True))
            continue
        low = body.lower()
        stem_low = jsp.stem.lower()
        open_forms = len(re.findall(r'<form\b', low))
        close_forms = len(re.findall(r'</form\b', low))
        if close_forms and not open_forms:
            issues.append(_issue('malformed_jsp_structure', rel, 'jsp closes form without opening form tag', repairable=True))
            continue
        if open_forms != close_forms:
            issues.append(_issue('malformed_jsp_structure', rel, 'jsp form tags are structurally unbalanced', repairable=True))
            continue
        if '</body>' in low and '<body' not in low:
            issues.append(_issue('malformed_jsp_structure', rel, 'jsp closes body without opening body tag', repairable=True))
            continue
        if '</if>' in low:
            issues.append(_issue('malformed_jsp_structure', rel, 'jsp contains orphan closing if tag', repairable=True))
            continue
        for tag_name in ('c:if', 'c:choose', 'c:when', 'c:otherwise', 'c:forEach', 'c:forTokens', 'c:catch', 'div', 'section', 'article', 'aside', 'table', 'tr', 'td', 'ul', 'li', 'nav'):
            if _has_orphan_closing_tag(body, tag_name):
                issues.append(_issue('malformed_jsp_structure', rel, f'jsp contains orphan closing {tag_name} tag', repairable=True))
                break
        else:
            pass
        if issues and issues[-1]['path'] == rel and 'orphan closing c:' in str(issues[-1].get('message') or ''):
            continue
        if leading_close_re.search(body):
            issues.append(_issue('malformed_jsp_structure', rel, 'jsp starts content with orphan closing layout tag', repairable=True))
            continue
        normalized = re.sub(r'(?is)^\s*(?:<%@[^%]*%>\s*|<!--.*?-->\s*|<!doctype[^>]*>\s*|<html[^>]*>\s*|<head[^>]*>.*?</head>\s*|<body[^>]*>\s*|<%@\s*include[^%]*header\.jsp\s*%>\s*|<%@\s*include[^%]*leftnav\.jsp\s*%>\s*)*', '', body)
        if re.match(r'(?is)^\s*</(?:div|section|article|aside|form|table|tr|td|ul|li|nav)>', normalized):
            issues.append(_issue('malformed_jsp_structure', rel, 'jsp starts content with orphan closing layout tag', repairable=True))
            continue
        if re.search(r'''(?is)<form[^>]*method=["']post["'][^>]*>.*?<div[^>]*class=["'][^"']*autopj-search-fields[^"']*["'][^>]*>.*?</div>.*?</form>''', body):
            issues.append(_issue('malformed_jsp_structure', rel, 'search fields are nested inside post form markup', repairable=True))
            continue
        if rel.lower().endswith('/common/css.jsp'):
            if '<%@ include file="/WEB-INF/views/common/header.jsp" %>' in body or '<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>' in body:
                issues.append(_issue('malformed_jsp_structure', rel, 'common/css.jsp must contain stylesheet links only', repairable=True))
                continue
        if re.search(r"<c:out\s+[^>]*value\s*=\s*['\"]\s*['\"]", body, re.IGNORECASE):
            issues.append(_issue('malformed_jsp_structure', rel, 'jsp contains empty output binding placeholder', repairable=True))
            continue
        if re.search(r"<input\b[^>]*/\s+type\s*=\s*['\"]", body, re.IGNORECASE):
            issues.append(_issue('malformed_jsp_structure', rel, 'jsp contains malformed input tag attribute order', repairable=True))
            continue
        if re.search(r"(?:href|action)\s*=\s*['\"][^'\"]*\?[A-Za-z_][\w]*=\s*['\"]", body, re.IGNORECASE):
            issues.append(_issue('malformed_jsp_structure', rel, 'jsp contains unresolved route parameter placeholder', repairable=True))
            continue
        if re.search(r"<input\b[^>]*type\s*=\s*['\"]hidden['\"][^>]*value\s*=\s*['\"]\s*['\"]", body, re.IGNORECASE):
            issues.append(_issue('malformed_jsp_structure', rel, 'jsp contains empty hidden primary key binding placeholder', repairable=True))
            continue
        for style_body in re.findall(r'<style\b[^>]*>(.*?)</style>', body, re.IGNORECASE | re.DOTALL):
            plain_style = re.sub(r'/\*.*?\*/', '', style_body, flags=re.DOTALL)
            if plain_style.count('{') != plain_style.count('}'):
                issues.append(_issue('malformed_jsp_structure', rel, 'jsp contains malformed style block', repairable=True))
                break
            if re.search(r'(?m)^\s*(?:width|height|min-width|min-height|max-width|max-height|margin|padding|border|background|font|color)\s*:', plain_style):
                issues.append(_issue('malformed_jsp_structure', rel, 'jsp style block contains selectorless css declaration', repairable=True))
                break
        head_match = re.search(r'<head\b[^>]*>(.*?)</head>', body, re.IGNORECASE | re.DOTALL)
        if head_match:
            head_body = head_match.group(1).lower()
            forbidden = ('<body', '<form', '<div', '<section', '<aside', '<table', '<input', '<textarea', '<select')
            if any(token in head_body for token in forbidden):
                issues.append(_issue('malformed_jsp_structure', rel, 'jsp head section contains body/form markup', repairable=True))
                continue
        screen_role = _jsp_screen_role(jsp, body)
        is_entry_like = screen_role == 'entry'
        is_calendar_like = screen_role == 'calendar'
        is_login_like = screen_role == 'login'
        is_signup_like = screen_role == 'signup'
        is_form_like = screen_role in {'form', 'login', 'signup'}
        if is_form_like and not is_entry_like and '<form' not in low:
            issues.append(_issue('malformed_jsp_structure', rel, 'form-like jsp is missing opening form tag', repairable=True, details={'screen_role': screen_role}))
            continue
        if is_login_like and '<input' in low and 'type="password"' not in low and "type='password'" not in low:
            issues.append(_issue('malformed_jsp_structure', rel, 'login jsp is missing password input field', repairable=True, details={'screen_role': screen_role}))
            continue
        if is_signup_like and ('회원가입' in body or 'sign up' in low or 'register' in low) and 'type="password"' not in low and "type='password'" not in low:
            issues.append(_issue('malformed_jsp_structure', rel, 'signup jsp is missing password input field', repairable=True, details={'screen_role': screen_role}))
            continue
    return issues


def _discover_primary_login_route(project_root: Path) -> str:
    java_root = project_root / 'src/main/java'
    if not java_root.exists():
        return ''
    candidates: List[str] = []
    auth_helper: List[str] = []
    for controller in java_root.rglob('*Controller.java'):
        body = _read_text(controller)
        info = _controller_domain_and_prefix(body, controller)
        prefix = info.get('prefix') or ''
        for match in re.finditer(r'@(GetMapping|RequestMapping)\(([^)]*)\)', body, re.DOTALL):
            ann = match.group(0)
            path_match = re.search(r"[\"'](/[^\"']+)[\"']", ann)
            if not path_match:
                continue
            route = path_match.group(1).strip()
            full_route = _combine_controller_route(prefix, route)
            low = full_route.lower()
            if not low.endswith('.do'):
                continue
            if any(token in low for token in ('integratedcallback', 'integrationguide', 'integratedlogin', 'certlogin', 'jwtlogin', 'ssologin', 'actionmain')):
                auth_helper.append(full_route)
                continue
            if 'login' in low:
                candidates.append(full_route)
    ordered = candidates + auth_helper
    return next((route for route in ordered if route), '')


def _discover_signup_route(project_root: Path) -> str:
    java_root = project_root / 'src/main/java'
    if not java_root.exists():
        return ''
    candidates: List[str] = []
    for controller in java_root.rglob('*Controller.java'):
        body = _read_text(controller)
        info = _controller_domain_and_prefix(body, controller)
        prefix = info.get('prefix') or ''
        for match in re.finditer(r'@(GetMapping|RequestMapping)\(([^)]*)\)', body, re.DOTALL):
            ann = match.group(0)
            path_match = re.search(r"[\"'](/[^\"']+)[\"']", ann)
            if not path_match:
                continue
            route = path_match.group(1).strip()
            full_route = _combine_controller_route(prefix, route)
            low = full_route.lower()
            if not low.endswith('.do'):
                continue
            if any(token in low for token in ('signup', 'register', 'join')):
                candidates.append(full_route)
    return next((route for route in candidates if route), '')


def _scan_common_auth_navigation(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    primary_login = _discover_primary_login_route(project_root)
    signup_route = _discover_signup_route(project_root)
    if not primary_login and not signup_route:
        return issues
    helper_markers = ('/integratedcallback.do', '/integrationguide.do', '/integratedlogin.do', '/ssologin.do', '/certlogin.do', '/jwtlogin.do', '/actionmain.do')
    generic_login_markers = ('/login.do', "value='/login.do'", 'value="/login.do"')
    signup_markers = ('signup', 'register', 'join', '회원가입')
    for rel in ('src/main/webapp/WEB-INF/views/common/header.jsp', 'src/main/webapp/WEB-INF/views/common/leftNav.jsp'):
        abs_path = project_root / rel
        if not abs_path.exists():
            continue
        body = _read_text(abs_path)
        low = body.lower()
        if primary_login:
            has_wrong_helper = any(marker in low for marker in helper_markers)
            has_generic_login = any(marker in low for marker in generic_login_markers) and primary_login.lower() != '/login.do'
            login_label_exists = _nav_anchor_with_label_exists(body, ('로그인', 'login'))
            if ((has_wrong_helper or has_generic_login) and primary_login.lower() not in low) or (login_label_exists and primary_login.lower() not in low):
                issues.append(_issue('auth_nav_route_mismatch', rel, f'common navigation should point login entry to {primary_login}', repairable=True, details={'login_route': primary_login, 'signup_route': signup_route}))
        if signup_route and not _nav_anchor_with_label_exists(body, ('회원가입', 'signup', 'register', 'join')):
            issues.append(_issue('auth_nav_route_mismatch', rel, f'common navigation should include signup entry to {signup_route}', repairable=True, details={'login_route': primary_login, 'signup_route': signup_route}))
    return issues
def _scan_unexpected_auth_helper_artifacts(project_root: Path, cfg: Any) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    checks = [
        ('jwt', bool(getattr(cfg, 'auth_jwt_login', False)), [
            'src/main/webapp/WEB-INF/views/login/jwtLogin.jsp',
            'src/main/java/**/JwtLoginController.java',
            'src/main/java/**/JwtTokenProvider.java',
        ]),
        ('cert', bool(getattr(cfg, 'auth_cert_login', False)), [
            'src/main/webapp/WEB-INF/views/login/certLogin.jsp',
            'src/main/java/**/CertLoginController.java',
            'src/main/java/**/CertLoginService.java',
            'src/main/java/**/CertLoginServiceImpl.java',
        ]),
        ('integration', bool(getattr(cfg, 'auth_unified_auth', False)), [
            'src/main/webapp/WEB-INF/views/login/integrationGuide.jsp',
            'src/main/java/**/IntegratedAuthService.java',
            'src/main/java/**/IntegratedAuthServiceImpl.java',
        ]),
    ]
    for helper, enabled, patterns in checks:
        if enabled:
            continue
        for pattern in patterns:
            if '**/' in pattern:
                base, name = pattern.split('**/', 1)
                base_path = project_root / base.rstrip('/')
                matches = list(base_path.rglob(name)) if base_path.exists() else []
            else:
                candidate = project_root / pattern
                matches = [candidate] if candidate.exists() else []
            for match in matches:
                rel = str(match.relative_to(project_root)).replace('\\', '/')
                issues.append(_issue('unexpected_auth_helper_artifact', rel, f'{helper} auth helper was generated without that auth option being enabled', repairable=True, details={'helper': helper}))
    return issues

def _scan_broken_c_url(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for jsp in (project_root / "src/main/webapp/WEB-INF/views").rglob("*.jsp"):
        body = _read_text(jsp)
        rel = str(jsp.relative_to(project_root))
        for lineno, line in enumerate(body.splitlines(), start=1):
            if '<c:url' not in line:
                continue
            low = line.lower()
            if '/>' in line or '</c:url>' in low:
                continue
            issues.append(_issue("broken_c_url", rel, f"line {lineno} contains unterminated c:url tag", repairable=True))
            break
    return issues


_TEMPORAL_NAME_RE = re.compile(r'(date|time|datetime)', re.IGNORECASE)


_CSS_IDENTIFIER_RE = re.compile(r'\b\d+fr(?:_\d+fr)*\b', re.IGNORECASE)


def _scan_illegal_identifiers(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / "src/main/java"
    resources_root = project_root / "src/main/resources"
    if java_root.exists():
        for java in java_root.rglob("*.java"):
            body = _read_text(java)
            rel = str(java.relative_to(project_root))
            if _CSS_IDENTIFIER_RE.search(body) or re.search(r'\b(?:get|set)\d+[A-Za-z0-9_]*\s*\(', body):
                issues.append(_issue("illegal_identifier", rel, "java source contains invalid identifier token or css-derived field name", repairable=False))
    if resources_root.exists():
        for res in list(resources_root.rglob("*.xml")) + list(resources_root.rglob("*.sql")):
            body = _read_text(res)
            rel = str(res.relative_to(project_root))
            if _CSS_IDENTIFIER_RE.search(body):
                issues.append(_issue("illegal_identifier", rel, "sql/xml contains css-derived identifier token", repairable=False))
    return issues



def _jsp_or_common_has_jquery(project_root: Path, body: str) -> bool:
    low = (body or '').lower()
    if 'jquery' in low and ('<script' in low or 'src=' in low):
        return True
    include_paths = re.findall(r'<%@\s*include\s+file\s*=\s*"([^"]+)"\s*%>', body or '', re.IGNORECASE)
    for include in include_paths:
        rel = include.replace('\\', '/').strip()
        candidate = project_root / ('src/main/webapp/' + rel.lstrip('/')) if rel.startswith('/') else project_root / rel
        if candidate.exists():
            included = _read_text(candidate).lower()
            if 'jquery' in included and ('<script' in included or 'src=' in included):
                return True
    return False

def _is_jsp_validation_partial(rel: str) -> bool:
    low = str(rel or '').replace('\\', '/').lower()
    return low.endswith('/web-inf/views/common/header.jsp') or low.endswith('/web-inf/views/common/leftnav.jsp') or low.endswith('/web-inf/views/common/footer.jsp') or low.endswith('/web-inf/views/common/taglibs.jsp') or low.endswith('/web-inf/views/include.jsp') or low.endswith('/web-inf/views/common/include.jsp') or low.endswith('/web-inf/views/common/navi.jsp') or low.endswith('/web-inf/views/common/layout.jsp') or low.endswith('/web-inf/views/common.jsp') or low.endswith('/web-inf/views/_layout.jsp')


def _scan_jsp_dependency_issues(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    view_root = project_root / "src/main/webapp/WEB-INF/views"
    web_root = project_root / "src/main/webapp"
    if not view_root.exists():
        return issues
    for jsp in view_root.rglob("*.jsp"):
        body = _read_text(jsp)
        rel = str(jsp.relative_to(project_root))
        if _is_jsp_validation_partial(rel):
            continue
        low = body.lower()
        if 'fn:' in body and 'taglib prefix="fn"' not in low and "taglib prefix='fn'" not in low:
            issues.append(_issue("jsp_dependency_missing", rel, "jsp uses fn: tag without fn taglib declaration", repairable=True, details={"kind": "fn_taglib"}))
        if ('$(' in body or 'jQuery(' in body) and not _jsp_or_common_has_jquery(project_root, body):
            issues.append(_issue("jsp_dependency_missing", rel, "jsp uses jquery syntax without jquery script include", repairable=True, details={"kind": "jquery"}))
        for asset in ('/js/fullcalendar.min.js', '/js/moment.min.js', '/css/fullcalendar.min.css'):
            if asset in body:
                asset_path = web_root / asset.lstrip('/')
                if not asset_path.exists():
                    issues.append(_issue("jsp_dependency_missing", rel, f"jsp references missing asset {asset}", repairable=True, details={"kind": "asset", "asset": asset}))
    return issues




def _discover_controller_routes(project_root: Path) -> set[str]:
    java_root = project_root / "src/main/java"
    routes: set[str] = set()
    if not java_root.exists():
        return routes
    for controller in java_root.rglob('*Controller.java'):
        body = _read_text(controller)
        info = _controller_domain_and_prefix(body, controller)
        prefix = info.get('prefix') or ''
        for match in re.finditer(r'@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\(([^)]*)\)', body, re.DOTALL):
            ann = match.group(0) or ''
            for path_match in re.finditer(r'''["'](/[^"']+)["']''', ann):
                route = (path_match.group(1) or '').strip()
                if not route:
                    continue
                full = _combine_controller_route(prefix, route)
                if full:
                    routes.add(full)
    return routes


def _extract_jsp_route_references(body: str) -> set[str]:
    refs: set[str] = set()
    patterns = [
        r'''<c:url\s+value=["'](/[^"']+)["']''',
        r'''\b(?:action|href|src)=["'](?:\$\{pageContext\.request\.contextPath\})?(/[^"']+)["']''',
        r'''(?:location\.href|window\.location(?:\.href)?|fetch|url)\s*[:=,(]\s*["'](?:\$\{pageContext\.request\.contextPath\})?(/[^"']+)["']''',
        r'''["']\$\{pageContext\.request\.contextPath\}(/[^"']+)["']''',
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, body, re.IGNORECASE):
            route = (match.group(1) or '').strip()
            if route:
                refs.add(route)
    return refs


def _is_static_route_reference(route: str) -> bool:
    low = (route or '').strip().lower()
    return (
        not low
        or low.startswith(('http://', 'https://', '//', '#'))
        or low.startswith(('/css/', '/js/', '/images/', '/webjars/', '/favicon', '/error'))
        or low.endswith(('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf'))
    )


def _is_jquery_usage_without_include(body: str) -> bool:
    low = (body or '').lower()
    uses_jquery = '$.ajax' in low or '$(' in low or 'jQuery(' in body
    if not uses_jquery:
        return False
    if 'jquery.min.js' in low or 'jquery.js' in low or '/webjars/jquery' in low:
        return False
    return True


def _is_structural_views_crud_jsp(path: Path, project_root: Path) -> bool:
    try:
        rel_low = _normalize_rel_path(str(path.relative_to(project_root))).lower()
    except Exception:
        rel_low = _normalize_rel_path(str(path)).lower()
    if '/web-inf/views/views/' not in rel_low:
        return False
    name = path.name.lower()
    return any(name.endswith(suffix) for suffix in ('list.jsp', 'detail.jsp', 'form.jsp', 'calendar.jsp', 'view.jsp', 'edit.jsp'))


def _scan_unresolved_jsp_routes(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    view_root = project_root / "src/main/webapp/WEB-INF/views"
    if not view_root.exists():
        return issues
    controller_routes = _discover_controller_routes(project_root)
    for jsp in view_root.rglob("*.jsp"):
        body = _read_text(jsp)
        rel = str(jsp.relative_to(project_root))
        if _is_jsp_validation_partial(rel):
            continue
        low = body.lower()
        if '/view/{viewName}.do' in body or '{viewname}' in low:
            issues.append(_issue('jsp_unresolved_route', rel, 'jsp contains unresolved generic view route placeholder', repairable=True))
        refs = sorted(route for route in _extract_jsp_route_references(body) if not _is_static_route_reference(route))
        missing = []
        for route in refs:
            route_base = route.split('?', 1)[0].strip()
            if route in controller_routes or route_base in controller_routes:
                continue
            missing.append(route)
        if missing:
            issues.append(_issue('jsp_missing_route_reference', rel, f'jsp references routes with no matching controller mapping: {", ".join(missing)}', repairable=True, details={'missing_routes': missing, 'discovered_routes': sorted(controller_routes)}))
        if _is_jquery_usage_without_include(body):
            issues.append(_issue('jsp_dependency_missing', rel, 'jquery usage detected without jquery include', repairable=True, details={'kind': 'jquery'}))
    return issues


def _scan_legacy_calendar_jsp(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    view_root = project_root / "src/main/webapp/WEB-INF/views"
    if not view_root.exists():
        return issues
    for jsp in view_root.rglob('*Calendar.jsp'):
        body = _read_text(jsp)
        low = body.lower()
        if any(token in low for token in ('fullcalendar.min.js', 'moment.min.js', '$(document).ready', 'eventclick:', 'dayclick:', '.fullcalendar(')):
            issues.append(_issue('legacy_calendar_jsp', str(jsp.relative_to(project_root)), 'legacy fullcalendar-based calendar jsp detected', repairable=True))
    return issues

def _scan_temporal_inputs(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for jsp in (project_root / "src/main/webapp/WEB-INF/views").rglob("*.jsp"):
        body = _read_text(jsp)
        rel = str(jsp.relative_to(project_root))
        for match in re.finditer(r'<input[^>]+name="([^"]+)"[^>]*>', body, re.IGNORECASE):
            name = match.group(1)
            tag = match.group(0)
            if not _TEMPORAL_NAME_RE.search(name):
                continue
            type_match = re.search(r'type="([^"]+)"', tag, re.IGNORECASE)
            input_type = (type_match.group(1) if type_match else "text").lower()
            if "datetime" in name.lower() and input_type != "datetime-local":
                issues.append(_issue("temporal_input_type", rel, f"{name} should use datetime-local input", repairable=True))
            elif "date" in name.lower() and "time" not in name.lower() and input_type != "date":
                issues.append(_issue("temporal_input_type", rel, f"{name} should use date input", repairable=True))
            elif name.lower().endswith("time") and "date" not in name.lower() and input_type != "time":
                issues.append(_issue("temporal_input_type", rel, f"{name} should use time input", repairable=True))
    return issues


def _scan_schema_conflicts(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    a = project_root / "src/main/resources/schema.sql"
    b = project_root / "src/main/resources/db/schema.sql"
    if a.exists() and b.exists():
        ta = _read_text(a)
        tb = _read_text(b)
        if ta.strip() and tb.strip() and ta.strip() != tb.strip():
            issues.append(_issue("schema_conflict", str(a.relative_to(project_root)), "schema.sql and db/schema.sql differ", repairable=True, details={"primary": str(a.relative_to(project_root)), "variants": [str(b.relative_to(project_root))]}))

    create_table_re = re.compile(r'create\s+table\s+(?:if\s+not\s+exists\s+)?[`"]?([A-Za-z_][\w]*)[`"]?', re.IGNORECASE)
    for schema_path in (a, b):
        if not schema_path.exists():
            continue
        body = _read_text(schema_path)
        names = [m.group(1).lower() for m in create_table_re.finditer(body)]
        seen: Dict[str, int] = {}
        for name in names:
            seen[name] = seen.get(name, 0) + 1
        for name, count in sorted(seen.items()):
            if count > 1:
                issues.append(_issue("duplicate_table_definition", str(schema_path.relative_to(project_root)), f"schema declares table '{name}' more than once", repairable=True, details={"table": name}))
    return issues


def _scan_schema_variant_conflicts(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    primary = project_root / "src/main/resources/schema.sql"
    db_dir = project_root / "src/main/resources/db"
    if not primary.exists() or not db_dir.exists():
        return issues
    primary_text = _read_text(primary).strip()
    differing: List[str] = []
    for variant in sorted(db_dir.glob("schema*.sql")):
        if _read_text(variant).strip() and _read_text(variant).strip() != primary_text:
            differing.append(str(variant.relative_to(project_root)))
    if differing:
        issues.append(
            _issue(
                "schema_variant_conflict",
                str(primary.relative_to(project_root)),
                "schema.sql variants differ from primary schema.sql",
                repairable=True,
                details={
                    "primary": str(primary.relative_to(project_root)),
                    "variants": differing,
                },
            )
        )
    return issues




def _scan_index_entrypoint_contract(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / "src/main/java"
    if not java_root.exists():
        return issues
    entry_domains = ENTRY_ONLY_CONTROLLER_DOMAINS
    crud_method_tokens = {"list", "detail", "form", "save", "delete", "update", "insert"}
    for controller in java_root.rglob("*Controller.java"):
        body = _read_text(controller)
        rel = str(controller.relative_to(project_root))
        stem = controller.stem[:-10] if controller.stem.endswith("Controller") else controller.stem
        info = _controller_domain_and_prefix(body, controller)
        domain = (info.get("domain") or stem or "").strip().lower()
        if domain not in entry_domains and stem.lower() not in {"index"}:
            continue
        refs = []
        for token in ("IndexVO", "IndexService", "IndexMapper", "HomeVO", "HomeService", "MainVO", "MainService"):
            if token in body:
                refs.append(token)
        if refs:
            issues.append(_issue(
                "index_entrypoint_miswired",
                rel,
                f"entry controller must not reference domain artifacts: {', '.join(refs)}",
                repairable=True,
                details={"controller_class": controller.stem, "domain": domain, "references": refs},
            ))
        bad_mappings: List[str] = []
        for mapping in re.finditer(r'@(GetMapping|PostMapping|RequestMapping)\(([^)]*)\)', body):
            args = (mapping.group(2) or '').lower()
            if any(tok in args for tok in ("/list", "/detail", "/form", "/save", "/delete", "/update", "/insert")):
                bad_mappings.append(args)
        for method in re.finditer(r'public\s+[A-Za-z0-9_$.<>]+\s+(\w+)\s*\(', body):
            name = (method.group(1) or '').strip().lower()
            if name in crud_method_tokens:
                bad_mappings.append(name)
        if bad_mappings:
            issues.append(_issue(
                "index_entrypoint_crud_leak",
                rel,
                "entry controller must not expose CRUD routes/methods",
                repairable=True,
                details={"controller_class": controller.stem, "domain": domain, "offenders": bad_mappings},
            ))
    return issues

def _scan_optional_primitive_params(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / "src/main/java"
    if not java_root.exists():
        return issues
    primitive_types = {"int", "long", "boolean", "double", "float", "short", "byte", "char"}
    for controller in java_root.rglob("*Controller.java"):
        body = _read_text(controller)
        rel = str(controller.relative_to(project_root))
        for m in re.finditer(r'@RequestParam\(([^\)]*)\)\s+([A-Za-z0-9_$.<>]+)\s+(\w+)', body):
            args, type_name, param_name = m.groups()
            if 'required = false' in args and type_name in primitive_types:
                issues.append(_issue("optional_primitive_param", rel, f"optional request param {param_name} must not use primitive type {type_name}", repairable=False))
    return issues


def _extract_annotation_paths(annotation: str) -> List[str]:
    ann = annotation or ''
    quoted = [item.strip() for item in re.findall(r"[\"\']([^\"\']+)[\"\']", ann) if item.strip()]
    if quoted:
        return [('/' + item.lstrip('/')) if not item.startswith('/') else item for item in quoted]
    return ['/']


def _extract_annotation_http_methods(kind: str, annotation: str) -> List[str]:
    mapping = {
        'GetMapping': ['GET'],
        'PostMapping': ['POST'],
        'PutMapping': ['PUT'],
        'DeleteMapping': ['DELETE'],
        'PatchMapping': ['PATCH'],
    }
    if kind in mapping:
        return mapping[kind]
    upper = (annotation or '').upper()
    methods = [m for m in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH') if f'REQUESTMETHOD.{m}' in upper]
    return methods or ['ANY']


def _methods_overlap(left: str, right: str) -> bool:
    return left == 'ANY' or right == 'ANY' or left == right


def _scan_duplicate_request_mappings(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / 'src/main/java'
    if not java_root.exists():
        return issues
    seen: Dict[str, List[Dict[str, str]]] = {}
    class_re = re.compile(r'@RequestMapping\(([^)]*)\)')
    method_re = re.compile(
        r'@((?:Get|Post|Put|Delete|Patch)Mapping|RequestMapping)\(([^)]*)\)\s+public\s+[A-Za-z0-9_$.<>\[\]]+\s+(\w+)\s*\(([^)]*)\)',
        re.DOTALL,
    )
    for controller in java_root.rglob('*Controller.java'):
        body = _read_text(controller)
        rel = str(controller.relative_to(project_root))
        class_match = class_re.search(body)
        class_paths = _extract_annotation_paths(class_match.group(0) if class_match else '') if class_match else ['/']
        controller_class = controller.stem
        for m in method_re.finditer(body):
            kind = m.group(1) or 'RequestMapping'
            annotation_args = m.group(2) or ''
            annotation = f'@{kind}({annotation_args})'
            method_name = m.group(3) or ''
            method_paths = _extract_annotation_paths(annotation)
            http_methods = _extract_annotation_http_methods(kind, annotation)
            for base in class_paths:
                for child in method_paths:
                    route = _normalize_rel_path((('/' + '/'.join(part.strip('/') for part in (base, child) if part.strip('/'))) if child != '/' or base != '/' else '/'))
                    if not route.startswith('/'):
                        route = '/' + route
                    for http_method in http_methods:
                        key = route
                        current = {
                            'path': rel,
                            'controller_class': controller_class,
                            'method_name': method_name,
                            'http_method': http_method,
                            'route': route,
                        }
                        prior_entries = seen.setdefault(key, [])
                        conflict = next(
                            (
                                item
                                for item in prior_entries
                                if _methods_overlap(item['http_method'], http_method)
                                and not (
                                    item['path'] == rel
                                    and item.get('method_name') == method_name
                                    and item.get('route') == route
                                    and item.get('http_method') == http_method
                                )
                            ),
                            None,
                        )
                        if conflict:
                            issues.append(_issue(
                                'ambiguous_request_mapping',
                                rel,
                                f'duplicate request mapping {http_method} {route} conflicts with {conflict["controller_class"]}#{conflict["method_name"]}',
                                repairable=True,
                                details={
                                    'route': route,
                                    'http_method': http_method,
                                    'controller_class': controller_class,
                                    'method_name': method_name,
                                    'conflicting_path': conflict['path'],
                                    'conflicting_controller_class': conflict['controller_class'],
                                    'conflicting_method_name': conflict['method_name'],
                                    'conflicting_http_method': conflict['http_method'],
                                },
                            ))
                        prior_entries.append(current)
    return issues


def _scan_mapper_namespaces(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / "src/main/java"
    resources_root = project_root / "src/main/resources"
    if not java_root.exists() or not resources_root.exists():
        return issues
    for mapper in java_root.rglob("*Mapper.java"):
        mapper_name = mapper.stem
        if mapper_name == f'{_BOOT_APP_CLASS}Mapper' or _is_boot_crud_artifact_rel(str(mapper.relative_to(project_root))) or _is_illegal_infra_artifact_rel(str(mapper.relative_to(project_root))):
            continue
        xmls = list(resources_root.rglob(f"{mapper_name}.xml"))
        if not xmls:
            continue
        body = _read_text(mapper)
        pkg_match = re.search(r'package\s+([A-Za-z0-9_.]+)\s*;', body)
        if not pkg_match:
            continue
        expected_ns = f"{pkg_match.group(1)}.{mapper_name}"
        for xml in xmls:
            xml_body = _read_text(xml)
            ns_match = re.search(r'<mapper[^>]+namespace="([^"]+)"', xml_body)
            if _is_illegal_infra_artifact_rel(str(xml.relative_to(project_root))):
                continue
            if ns_match and ns_match.group(1).strip() != expected_ns:
                issues.append(_issue("mapper_namespace_mismatch", str(xml.relative_to(project_root)), f"mapper namespace {ns_match.group(1).strip()} differs from {expected_ns}", repairable=True))
    return issues


def _scan_calendar_controller_support(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / "src/main/java"
    view_root = project_root / "src/main/webapp/WEB-INF/views"
    if not java_root.exists() or not view_root.exists():
        return issues
    controllers: Dict[str, tuple[Path, str]] = {}
    for controller in java_root.rglob("*Controller.java"):
        body = _read_text(controller)
        info = _controller_domain_and_prefix(body, controller)
        if info["domain"]:
            controllers[_domain_canonical_key(info["domain"])] = (controller, body)
    for calendar_jsp in view_root.rglob("*Calendar.jsp"):
        domain = calendar_jsp.parent.name
        domain_key = _domain_canonical_key(domain)
        rel_jsp = str(calendar_jsp.relative_to(project_root))
        if _is_boot_crud_artifact_rel(rel_jsp) or _is_illegal_infra_artifact_rel(rel_jsp):
            continue
        if not _calendar_view_requires_controller(calendar_jsp, domain):
            continue
        controller_info = controllers.get(domain_key)
        if not controller_info:
            issues.append(_issue("calendar_controller_missing", rel_jsp, f"calendar view exists but controller missing for {domain}", repairable=True, details={"domain": domain, "strategy": "remove_orphan_calendar_jsp"}))
            continue
        controller, body = controller_info
        rel = str(controller.relative_to(project_root))
        canonical_view_dir = _canonical_camel_name(domain) or domain
        stem = calendar_jsp.stem
        canonical_stem = stem
        if stem.lower().startswith(_canonical_snake_name(domain)) or stem.lower().startswith((canonical_view_dir or '').lower()):
            canonical_stem = f"{canonical_view_dir}Calendar"
        expected_view = f"{canonical_view_dir}/{canonical_stem}"
        low = body.lower()
        if _controller_is_entry_redirect_only(body, controller, domain):
            continue
        has_calendar_mapping = '@getmapping("/calendar.do")' in low or "@getmapping('/calendar.do')" in low
        if not has_calendar_mapping:
            issues.append(_issue("calendar_mapping_missing", rel, f"calendar jsp exists but controller missing /calendar.do for {domain}", repairable=True, details={"domain": domain, "expected_view": expected_view, "jsp_path": rel_jsp}))
            continue
        if f'return "{expected_view.lower()}"' not in low and f"return '{expected_view.lower()}'" not in low:
            issues.append(_issue("calendar_view_mismatch", rel, f"calendar controller should return {expected_view}", repairable=True, details={"domain": domain, "expected_view": expected_view, "jsp_path": rel_jsp}))
    return issues




def _scan_calendar_render_contract(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    java_root = project_root / "src/main/java"
    view_root = project_root / "src/main/webapp/WEB-INF/views"
    if not view_root.exists():
        return issues
    controllers: Dict[str, tuple[Path, str]] = {}
    if java_root.exists():
        for controller in java_root.rglob("*Controller.java"):
            body = _read_text(controller)
            info = _controller_domain_and_prefix(body, controller)
            if info["domain"]:
                controllers[info["domain"]] = (controller, body)
    for calendar_jsp in view_root.rglob("*Calendar.jsp"):
        domain = calendar_jsp.parent.name
        domain_key = _domain_canonical_key(domain)
        rel_jsp = str(calendar_jsp.relative_to(project_root))
        body = _read_text(calendar_jsp)
        low = body.lower()
        has_calendar_ui = 'calendar-grid' in low or 'calendar-weekdays' in low or 'schedule-page' in low
        has_shell_only_grid = 'data-role="calendar-grid"></div>' in low or ('class="cell-grid">' in low and 'items="${calendarcells}"' not in low)
        has_ssr_cells = 'items="${calendarcells}"' in low
        has_ssr_selected = 'items="${selecteddateschedules}"' in low
        bare_year_month = '<c:out value="${currentyear}"/>년 <c:out value="${currentmonth}"/>월' in low and 'not empty currentyear and not empty currentmonth' not in low
        if has_calendar_ui and (has_shell_only_grid or not has_ssr_cells or not has_ssr_selected or bare_year_month):
            issues.append(_issue(
                "calendar_ssr_missing",
                rel_jsp,
                f"calendar jsp for {domain} must server-render month cells, selected-date list, and safe year/month title",
                repairable=True,
                details={
                    "domain": domain,
                    "missing_cells": not has_ssr_cells,
                    "missing_selected_list": not has_ssr_selected,
                    "bare_year_month": bare_year_month,
                },
            ))
        controller_info = controllers.get(domain_key)
        if not controller_info:
            continue
        controller, controller_body = controller_info
        controller_low = controller_body.lower()
        has_calendar_mapping = '@getmapping("/calendar.do")' in controller_low or "@getmapping('/calendar.do')" in controller_low
        if not has_calendar_mapping:
            continue
        required_attrs = [
            'calendarcells', 'selecteddateschedules', 'currentyear', 'currentmonth',
            'prevyear', 'prevmonth', 'nextyear', 'nextmonth'
        ]
        if _controller_is_entry_redirect_only(controller_body, controller, domain):
            continue
        missing_attrs = [name for name in required_attrs if f'model.addattribute("{name}"' not in controller_low]
        if missing_attrs:
            issues.append(_issue(
                "calendar_data_contract_missing",
                str(controller.relative_to(project_root)),
                f"calendar controller for {domain} must populate calendar model contract: {', '.join(missing_attrs)}",
                repairable=True,
                details={"domain": domain, "missing": missing_attrs, "jsp_path": rel_jsp},
            ))
    return issues
def _scan_schema_bootstrap_conflicts(project_root: Path) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    props = project_root / "src/main/resources/application.properties"
    java_root = project_root / "src/main/java"
    if props.exists() and java_root.exists() and "spring.sql.init.mode=always" in _read_text(props).lower():
        for init in java_root.rglob("DatabaseInitializer.java"):
            issues.append(_issue("duplicate_schema_initializer", str(init.relative_to(project_root)), "spring.sql.init.mode=always already initializes schema.sql; DatabaseInitializer duplicates schema bootstrap", repairable=True))
    return issues




def _scan_reserved_db_identifiers(project_root: Path, db_vendor: str = '') -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    vendor = _normalize_db_vendor(db_vendor)
    reserved = _db_reserved_keywords(vendor)
    if not reserved:
        return issues
    schema_tables = _parse_schema_sql_tables(project_root)
    for table, info in (schema_tables or {}).items():
        rel = str(info.get('path') or 'src/main/resources/schema.sql')
        if str(table or '').strip().lower() in reserved:
            issues.append(_issue('reserved_db_identifier', rel, f'schema.sql uses reserved {vendor or "db"} identifier as table name: {table}', repairable=True, details={'kind': 'table', 'identifier': table, 'db_vendor': vendor}))
        for col in info.get('columns') or []:
            if str(col or '').strip().lower() in reserved:
                issues.append(_issue('reserved_db_identifier', rel, f'schema.sql uses reserved {vendor or "db"} identifier as column name: {col}', repairable=True, details={'kind': 'column', 'identifier': col, 'table': table, 'db_vendor': vendor}))
    return issues


def validate_generated_project(
    project_root: Path,
    cfg: Any,
    manifest: Optional[Dict[str, Any]] = None,
    include_runtime: bool = True,
    run_runtime: Optional[bool] = None,
) -> Dict[str, Any]:
    root = Path(project_root)
    static_issues: List[Dict[str, Any]] = []
    static_issues.extend(_scan_controller_views(root))
    static_issues.extend(_scan_service_wiring(root))
    static_issues.extend(_scan_expected_service_pairs(root))
    static_issues.extend(_scan_mapper_xml(root))
    static_issues.extend(_scan_table_prefix_contract(root))
    static_issues.extend(_scan_mapper_table_vo_alignment(root))
    static_issues.extend(_scan_boolean_getters(root))
    static_issues.extend(_scan_id_type_mismatch(root))
    static_issues.extend(_scan_controller_service_signature_mismatch(root))
    static_issues.extend(_scan_optional_param_guard_mismatch(root))
    static_issues.extend(_scan_undefined_vo_getter_usage(root))
    static_issues.extend(_scan_jsp_vo_property_mismatch(root))
    static_issues.extend(_scan_route_param_consistency(root))
    static_issues.extend(_scan_optional_primitive_params(root))
    static_issues.extend(_scan_duplicate_request_mappings(root))
    static_issues.extend(_scan_mapper_namespaces(root))
    static_issues.extend(_scan_calendar_controller_support(root))
    static_issues.extend(_scan_calendar_render_contract(root))
    static_issues.extend(_scan_illegal_identifiers(root))
    static_issues.extend(_scan_reserved_db_identifiers(root, getattr(cfg, 'database_key', '') or getattr(cfg, 'database_type', '') or ''))
    static_issues.extend(_scan_jsp_dependency_issues(root))
    static_issues.extend(_scan_unresolved_jsp_routes(root))
    static_issues.extend(_scan_legacy_calendar_jsp(root))
    static_issues.extend(_scan_schema_bootstrap_conflicts(root))
    static_issues.extend(_scan_index_entrypoint_contract(root))
    if (getattr(cfg, "frontend_key", "") or "").lower() == "jsp":
        static_issues.extend(_scan_delete_ui(root))
        static_issues.extend(_scan_nested_forms(root))
        static_issues.extend(_scan_invalid_action_wrappers(root))
        static_issues.extend(_scan_broken_c_url(root))
        static_issues.extend(_scan_malformed_jsp_structure(root))
        static_issues.extend(_scan_temporal_inputs(root))
        static_issues.extend(_scan_search_fields_cover_all_columns(root))
        static_issues.extend(_scan_form_fields_cover_all_columns(root))
    static_issues.extend(_scan_common_auth_navigation(root))
    static_issues.extend(_scan_unexpected_auth_helper_artifacts(root, cfg))
    static_issues.extend(_scan_schema_conflicts(root))
    static_issues.extend(_scan_schema_variant_conflicts(root))

    runtime_report = {"ok": True, "compile": {"status": "skipped"}, "startup": {"status": "skipped"}, "endpoint_smoke": {"status": "skipped"}}
    if run_runtime is not None:
        include_runtime = bool(run_runtime)
    if include_runtime:
        runtime_report = run_backend_runtime_validation(root, manifest=manifest)
        write_runtime_report(root, runtime_report)

    legacy_code_map = {
        "missing_view": "missing_view_jsp",
        "missing_service": "missing_service_interface",
        "missing_service_impl": "missing_service_impl",
        "missing_mapper_xml": "missing_mapper_xml",
        "duplicate_boolean_getter": "ambiguous_boolean_getter",
        "id_type_mismatch": "controller_vo_type_mismatch",
        "controller_service_signature_mismatch": "controller_service_signature_mismatch",
        "optional_param_guard_mismatch": "optional_param_guard_mismatch",
        "undefined_vo_getter_usage": "undefined_vo_getter_usage",
        "jsp_vo_property_mismatch": "jsp_vo_property_mismatch",
        "route_param_mismatch": "route_param_mismatch",
        "missing_delete_ui": "missing_delete_ui",
        "nested_form": "nested_form",
        "invalid_action_wrapper": "invalid_action_wrapper",
        "broken_c_url": "broken_c_url",
        "malformed_jsp_structure": "malformed_jsp_structure",
        "auth_nav_route_mismatch": "auth_nav_route_mismatch",
        "search_ui_missing": "search_fields_incomplete",
        "jsp_missing_route_reference": "jsp_missing_route_reference",
        "temporal_input_type": "temporal_input_type_mismatch",
        "schema_conflict": "schema_conflict",
        "duplicate_table_definition": "duplicate_table_definition",
        "schema_variant_conflict": "schema_variant_conflict",
        "optional_primitive_param": "optional_primitive_param",
        "ambiguous_request_mapping": "ambiguous_request_mapping",
        "mapper_namespace_mismatch": "mapper_namespace_mismatch",
        "calendar_mapping_missing": "calendar_mapping_missing",
        "calendar_view_mismatch": "calendar_view_mismatch",
        "illegal_identifier": "illegal_identifier",
        "reserved_db_identifier": "reserved_db_identifier",
        "jsp_dependency_missing": "jsp_dependency_missing",
        "table_prefix_missing": "table_prefix_missing",
        "form_fields_incomplete": "form_fields_incomplete",
        "jsp_unresolved_route": "jsp_unresolved_route",
        "legacy_calendar_jsp": "legacy_calendar_jsp",
        "duplicate_schema_initializer": "duplicate_schema_initializer",
        "index_entrypoint_miswired": "index_entrypoint_miswired",
        "index_entrypoint_crud_leak": "index_entrypoint_crud_leak",
        "unexpected_auth_helper_artifact": "unexpected_auth_helper_artifact",
    }
    issues = [
        {
            "code": legacy_code_map.get(item.get("type") or "", item.get("type") or ""),
            "path": item.get("path") or "",
            "repairable": bool(item.get("repairable", True)),
            "details": dict({"message": item.get("message") or ""}, **(item.get("details") or {})),
        }
        for item in static_issues
    ]
    runtime_smoke = dict(runtime_report)
    compile_errors = ((runtime_smoke.get("compile") or {}).get("errors") or [])
    if runtime_smoke.get("status") == "skipped" or any((err.get("code") == "build_tool_missing") for err in compile_errors):
        runtime_smoke["skipped"] = True
    report = {
        "ok": not static_issues and runtime_report.get("ok", False),
        "static_issue_count": len(static_issues),
        "static_issues": static_issues,
        "issues": issues,
        "runtime": runtime_report,
        "runtime_smoke": runtime_smoke,
    }
    debug_dir = root / ".autopj_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / "generated_project_validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
