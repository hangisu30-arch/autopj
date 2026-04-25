from __future__ import annotations

import re
import difflib
from pathlib import Path

_NON_AUTH_GENERATION_METADATA_MARKERS = {'db', 'schemaname', 'schema_name', 'database', 'tablename', 'table_name', 'packagename', 'package_name', 'frontendtype', 'backendtype', 'compile', 'compiled', 'build', 'runtime', 'startup', 'endpoint_smoke'}
_NON_AUTH_AUTH_SENSITIVE_MARKERS = {'password', 'passwd', 'pwd', 'loginpassword', 'login_password'}


def _normalize_guard_field(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', str(name or '').strip().lower())


def _is_non_auth_forbidden_field(name: str) -> bool:
    key = _normalize_guard_field(name)
    return key in _NON_AUTH_GENERATION_METADATA_MARKERS or key in _NON_AUTH_AUTH_SENSITIVE_MARKERS
from typing import Any, Dict, List

from execution_core.builtin_crud import builtin_file, infer_schema_from_file_ops, schema_for
from app.io.execution_core_apply import _rewrite_detail_jsp_from_schema, _rewrite_form_jsp_from_schema, _rewrite_list_jsp_from_schema
from execution_core.feature_rules import FEATURE_KIND_AUTH, FEATURE_KIND_CRUD, FEATURE_KIND_SCHEDULE

_GENERATION_METADATA_PROPS = {'db', 'schemaName', 'schema_name', 'database', 'tableName', 'packageName', 'frontendType', 'backendType', 'compile', 'compiled', 'build', 'runtime', 'startup', 'endpoint_smoke'}
_AUTH_SENSITIVE_PROPS = {'password', 'loginPassword', 'login_password', 'passwd', 'pwd'}
_SYNTHETIC_PLACEHOLDER_RE = re.compile(r'^(?:repeat\d+|section|temp[a-z0-9_]*|sample[a-z0-9_]*|example[a-z0-9_]*)$', re.IGNORECASE)


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except Exception:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except FileNotFoundError:
            return ""


def _normalize_rel_path(path: str) -> str:
    return (path or "").replace("\\", "/").lstrip("./")


_BALANCED_JSP_TAGS = (
    'form', 'div', 'section', 'article', 'aside', 'table', 'tr', 'td', 'ul', 'li', 'nav', 'body',
    'c:if', 'c:choose', 'c:when', 'c:otherwise', 'c:forEach', 'c:forTokens', 'c:catch',
)


def _cleanup_orphan_jsp_closing_tags(body: str) -> str:
    rendered = body or ''
    for tag in _BALANCED_JSP_TAGS:
        pattern = re.compile(rf'(?is)<{re.escape(tag)}\b[^>]*>|</{re.escape(tag)}\s*>')
        parts: list[str] = []
        last = 0
        depth = 0
        for match in pattern.finditer(rendered):
            token = match.group(0) or ''
            parts.append(rendered[last:match.start()])
            is_closing = token.lstrip().startswith('</')
            is_self_closing = token.rstrip().endswith('/>')
            if is_closing:
                if depth > 0:
                    depth -= 1
                    parts.append(token)
            else:
                parts.append(token)
                if not is_self_closing:
                    depth += 1
            last = match.end()
        parts.append(rendered[last:])
        rendered = ''.join(parts)
    rendered = re.sub(r'(?im)^\s*</(?:div|section|article|aside|form|table|tr|td|ul|li|nav|body)>\s*$', '', rendered)
    rendered = re.sub(r'(?im)^\s*</c:(?:if|choose|when|otherwise|forEach|forTokens|catch)>\s*$', '', rendered)
    rendered = re.sub(r'\n{3,}', '\n\n', rendered)
    return rendered






_ROUTE_TOKEN_STOPWORDS = {
    'webinf', 'views', 'view', 'jsp', 'do', 'searchid', 'searchkeyword', 'searchcondition',
    'pagecontext', 'request', 'contextpath', 'c', 'url', 'action', 'form', 'listpage', 'detailpage',
}


def _tokenize_routeish(value: str) -> List[str]:
    raw = str(value or '').strip()
    if not raw:
        return []
    raw = raw.split('?', 1)[0]
    raw = raw.replace('\\', '/').replace('-', ' ').replace('_', ' ').replace('.', ' ').replace('/', ' ')
    raw = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', raw)
    tokens = [part.strip().lower() for part in raw.split() if part.strip()]
    return [token for token in tokens if token not in _ROUTE_TOKEN_STOPWORDS]


def _balance_form_tags(body: str) -> str:
    text = body or ''
    if not text.strip():
        return text

    # First, preserve the existing form-count normalization because form tags are the
    # most common structural regression in generated JSPs.
    open_forms = len(re.findall(r'<form\b', text, re.IGNORECASE))
    close_forms = len(re.findall(r'</form\b', text, re.IGNORECASE))
    if close_forms > open_forms:
        extra = close_forms - open_forms
        text = re.sub(r'(?is)</form\s*>', '', text, count=extra)
    elif open_forms > close_forms:
        extra = open_forms - close_forms
        closing = '\n' + ('</form>\n' * extra)
        if re.search(r'(?is)</body\s*>', text):
            text = re.sub(r'(?is)</body\s*>', closing + '</body>', text, count=1)
        else:
            text = text.rstrip() + closing

    balance_tags = ['div', 'section', 'article', 'aside', 'table', 'tr', 'td', 'ul', 'li', 'nav', 'form']
    token_re = re.compile(r'(?is)<(/?)(' + '|'.join(balance_tags) + r')\b[^>]*?>')
    parts: List[str] = []
    stack: List[str] = []
    last = 0
    for match in token_re.finditer(text):
        parts.append(text[last:match.start()])
        is_closing = bool(match.group(1))
        tag = (match.group(2) or '').lower()
        token = match.group(0) or ''
        if not is_closing:
            parts.append(token)
            if not token.rstrip().endswith('/>'):
                stack.append(tag)
        else:
            if tag not in stack:
                last = match.end()
                continue
            while stack and stack[-1] != tag:
                parts.append(f'</{stack.pop()}>')
            if stack and stack[-1] == tag:
                stack.pop()
                parts.append(token)
        last = match.end()
    parts.append(text[last:])
    text = ''.join(parts)

    if stack:
        suffix = ''.join(f'</{tag}>' for tag in reversed(stack))
        body_close = re.search(r'(?is)</body\s*>', text)
        html_close = re.search(r'(?is)</html\s*>', text)
        insert_at = body_close.start() if body_close else (html_close.start() if html_close else len(text))
        text = text[:insert_at].rstrip() + '\n' + suffix + text[insert_at:]

    text = re.sub(r'>\s+</', '></', text)
    return text

def _semantic_route_replacement(target: str, discovered_routes: List[str], jsp_path: Path | None = None) -> str:
    target = (target or '').strip()
    if not target or not discovered_routes:
        return ''
    query = ''
    if '?' in target:
        route_only, query = target.split('?', 1)
    else:
        route_only = target
    target_tokens = set(_tokenize_routeish(route_only))
    path_tokens = set(_tokenize_routeish(str(jsp_path or '')))
    all_tokens = target_tokens | path_tokens
    action_hint = ''
    lowered = route_only.lower()
    if any(tok in lowered for tok in ('update', 'save', 'insert', 'create', 'modify', 'approve', 'reject')):
        action_hint = 'save'
    elif any(tok in lowered for tok in ('detail', 'view')):
        action_hint = 'detail'
    elif any(tok in lowered for tok in ('form', 'edit', 'register', 'join', 'signup')):
        action_hint = 'form'
    elif any(tok in lowered for tok in ('delete', 'remove')):
        action_hint = 'delete'
    elif any(tok in lowered for tok in ('manage', 'search', 'list')) or query:
        action_hint = 'list'

    best = ('', -10)
    for route in discovered_routes:
        route_tokens = set(_tokenize_routeish(route))
        score = len(all_tokens & route_tokens) * 3 + len(target_tokens & route_tokens) * 2
        route_low = route.lower()
        if action_hint == 'save' and any(route_low.endswith(suf) for suf in ('/save.do', '/update.do', '/insert.do', '/actionsave.do', '/actionupdate.do')):
            score += 6
        elif action_hint == 'detail' and any(route_low.endswith(suf) for suf in ('/detail.do', '/view.do')):
            score += 6
        elif action_hint == 'form' and any(route_low.endswith(suf) for suf in ('/form.do', '/edit.do', '/register.do', '/join.do', '/signup.do')):
            score += 6
        elif action_hint == 'delete' and any(route_low.endswith(suf) for suf in ('/delete.do', '/remove.do')):
            score += 6
        elif action_hint == 'list' and any(route_low.endswith(suf) for suf in ('/list.do', '/search.do', '/manage.do')):
            score += 6
        if route_low.startswith('/admin') and 'admin' in all_tokens:
            score += 2
        if score > best[1]:
            best = (route, score)
    replacement = best[0]
    if replacement and query:
        replacement = replacement + '?' + query
    return replacement



_FRAMEWORK_INTERNAL_PATH_PREFIXES = (
    'src/main/java/org/springframework/',
    'src/main/java/java/',
    'src/main/java/jakarta/',
    'src/main/java/javax/',
    'src/main/java/org/apache/',
)


def _is_framework_internal_path(rel_path: str) -> bool:
    rel = _normalize_rel_path(rel_path).lower()
    return bool(rel) and any(rel.startswith(prefix) for prefix in _FRAMEWORK_INTERNAL_PATH_PREFIXES)


def _extract_base_package_from_initializer(path: Path) -> str:
    body = _read_text(path)
    m = re.search(r'^\s*package\s+([A-Za-z0-9_.]+)\s*;', body, re.MULTILINE)
    pkg = (m.group(1) if m else '').strip()
    if pkg.endswith('.config'):
        return pkg[:-7]
    return pkg.rsplit('.', 1)[0] if '.' in pkg else pkg


def _dedupe_alter_add_column_statements(body: str) -> str:
    seen: set[tuple[str, str]] = set()
    kept: list[str] = []
    statements = [chunk.strip() for chunk in re.split(r';\s*', body or '') if chunk.strip()]
    pat = re.compile(r'alter\s+table\s+[`"]?([A-Za-z_][\w]*)[`"]?\s+add\s+(?:column\s+)?[`"]?([A-Za-z_][\w]*)[`"]?', re.IGNORECASE)
    for stmt in statements:
        m = pat.search(stmt)
        if m:
            key = (m.group(1).lower(), m.group(2).lower())
            if key in seen:
                continue
            seen.add(key)
        kept.append(stmt if stmt.endswith(';') else stmt + ';')
    rendered = '\n\n'.join(kept).strip()
    return rendered + ('\n' if rendered else '')

def _dedupe_create_table_statements(body: str) -> str:
    seen_tables: dict[str, int] = {}
    kept: list[str] = []
    statements = [chunk.strip() for chunk in re.split(r';\s*', body or '') if chunk.strip()]
    pat = re.compile(r'create\s+table\s+(?:if\s+not\s+exists\s+)?[`"]?([A-Za-z_][\w]*)[`"]?', re.IGNORECASE)
    for stmt in statements:
        normalized = stmt if stmt.endswith(';') else stmt + ';'
        m = pat.search(stmt)
        if m:
            table = m.group(1).lower()
            idx = seen_tables.get(table)
            if idx is not None:
                kept[idx] = normalized
                continue
            seen_tables[table] = len(kept)
        kept.append(normalized)
    rendered = '\n\n'.join(kept).strip()
    return rendered + ('\n' if rendered else '')


def _snake_to_camel(name: str) -> str:
    parts = [p for p in re.split(r'[^A-Za-z0-9]+', str(name or '').strip()) if p]
    if not parts:
        return ''
    return parts[0][:1].lower() + parts[0][1:] + ''.join(part[:1].upper() + part[1:] for part in parts[1:])


def _split_domain_tokens(value: str) -> List[str]:
    raw = str(value or '').strip()
    if not raw:
        return []
    compact_low = re.sub(r'[^a-z0-9]+', '', raw.lower())
    alias_map = {
        'tbmember': 'tb member',
        'tbuser': 'tb user',
        'tbaccount': 'tb account',
        'tbadmin': 'tb admin',
        'tbmemberadmin': 'tb member admin',
        'tbmemberauth': 'tb member auth',
        'adminmember': 'admin member',
        'memberadmin': 'member admin',
        'memberauth': 'member auth',
    }
    if compact_low in alias_map:
        raw = alias_map[compact_low]
    spaced = raw.replace('-', ' ').replace('_', ' ')
    spaced = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', spaced)
    tokens = [part.strip().lower() for part in spaced.split() if part.strip()]
    return tokens


def _domain_key(value: str) -> str:
    return ''.join(_split_domain_tokens(value))


def _logical_domain_name(value: str) -> str:
    tokens = _split_domain_tokens(value)
    while tokens and tokens[0] == 'tb':
        tokens = tokens[1:]
    if not tokens:
        return str(value or '').strip()
    return tokens[0] + ''.join(token[:1].upper() + token[1:] for token in tokens[1:])


def _is_membership_like_domain(value: str) -> bool:
    tokens = set(_split_domain_tokens(value))
    if not tokens:
        return False
    return bool(tokens & {'member', 'user', 'account', 'admin'})


def _find_domain_controller(project_root: Path, domain: str) -> Path | None:
    java_root = Path(project_root) / 'src/main/java'
    java_root.mkdir(parents=True, exist_ok=True)
    target_key = _domain_key(domain)
    target_tokens = set(_split_domain_tokens(domain))
    exact_matches: List[Path] = []
    fuzzy_matches: List[Path] = []
    for candidate in java_root.rglob('*Controller.java'):
        rel = _normalize_rel_path(str(candidate.relative_to(java_root)))
        rel_match = re.search(r'/(?:|.*?/)([A-Za-z0-9_]+)/web/[^/]+Controller\.java$', '/' + rel)
        candidate_domain = rel_match.group(1) if rel_match else _controller_domain_from_path(candidate)
        candidate_key = _domain_key(candidate_domain)
        if not candidate_key:
            continue
        candidate_tokens = set(_split_domain_tokens(candidate_domain))
        if candidate_key == target_key or (candidate_tokens and candidate_tokens == target_tokens):
            exact_matches.append(candidate)
        elif candidate_tokens and target_tokens and candidate_tokens.issuperset(target_tokens):
            fuzzy_matches.append(candidate)
    if exact_matches:
        return sorted(exact_matches)[0]
    if fuzzy_matches:
        return sorted(fuzzy_matches)[0]
    return None


def _infer_controller_base_package(project_root: Path) -> str:
    java_root = Path(project_root) / 'src/main/java'
    if not java_root.exists():
        return 'egovframework.app'
    for candidate in sorted(java_root.rglob('*.java')):
        body = _read_text(candidate)
        m = re.search(r'^\s*package\s+([A-Za-z0-9_.]+)\s*;', body, flags=re.MULTILINE)
        if not m:
            continue
        pkg = (m.group(1) or '').strip()
        if pkg.endswith('.web'):
            parts = pkg.split('.')
            if len(parts) >= 3:
                return '.'.join(parts[:-2])
        if pkg.endswith('.service') or pkg.endswith('.service.impl'):
            parts = pkg.split('.')
            if len(parts) >= 2:
                return '.'.join(parts[:-2]) if pkg.endswith('.service') else '.'.join(parts[:-3])
        if len(pkg.split('.')) >= 2:
            return '.'.join(pkg.split('.')[:2])
        return pkg
    return 'egovframework.app'


def _ensure_membership_controller_path(project_root: Path, domain: str) -> Path | None:
    existing = _find_domain_controller(project_root, domain)
    if existing is not None:
        return existing
    java_root = Path(project_root) / 'src/main/java'
    java_root.mkdir(parents=True, exist_ok=True)
    logical_domain = _logical_domain_name(domain) or str(domain or '').strip() or 'member'
    if not logical_domain:
        logical_domain = 'member'
    class_name = logical_domain[:1].upper() + logical_domain[1:] + 'Controller'
    base_package = _infer_controller_base_package(project_root)
    package_path = Path(*base_package.split('.')) / logical_domain / 'web'
    controller_path = java_root / package_path / class_name
    controller_path = controller_path.with_suffix('.java')
    controller_path.parent.mkdir(parents=True, exist_ok=True)
    if not controller_path.exists():
        package_decl = '.'.join([base_package, logical_domain, 'web']).strip('.')
        controller_path.write_text(f'package {package_decl};\n', encoding='utf-8')
    return controller_path


def _ensure_vo_properties(vo_path: Path | None, props: List[str]) -> bool:
    if vo_path is None or not vo_path.exists() or not props:
        return False
    body = _read_text(vo_path)
    original = body
    existing_fields = set(re.findall(r'private\s+[A-Za-z0-9_<>\.]+\s+([A-Za-z_][A-Za-z0-9_]*)\s*;', body))
    additions: List[str] = []
    methods: List[str] = []
    for raw in props:
        prop = str(raw or '').strip()
        if not prop or prop in _GENERATION_METADATA_PROPS:
            continue
        low = prop.lower()
        if 'password' in low or low in {'passwd', 'pwd'}:
            continue
        candidate = prop if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', prop) else _snake_to_camel(prop)
        if not candidate or candidate in existing_fields:
            continue
        existing_fields.add(candidate)
        cap = candidate[:1].upper() + candidate[1:]
        additions.append(f'    private String {candidate};')
        if not re.search(rf'public\s+[A-Za-z0-9_<>\.]+\s+get{re.escape(cap)}\s*\(', body):
            methods.extend([
                '',
                f'    public String get{cap}() {{',
                f'        return {candidate};',
                '    }',
                '',
                f'    public void set{cap}(String {candidate}) {{',
                f'        this.{candidate} = {candidate};',
                '    }',
            ])
    if not additions and not methods:
        return False
    last_field = None
    for m in re.finditer(r'private\s+[A-Za-z0-9_<>\.]+\s+[A-Za-z_][A-Za-z0-9_]*\s*;', body):
        last_field = m
    if additions:
        field_block = '\n' + '\n'.join(additions) + '\n'
        if last_field:
            body = body[:last_field.end()] + field_block + body[last_field.end():]
        else:
            body = re.sub(r'(class\s+[A-Za-z0-9_]+(?:\s+extends\s+[A-Za-z0-9_<>\.]+)?(?:\s+implements\s+[A-Za-z0-9_, <>\.]+)?\s*\{)', r'\1\n' + '\n'.join(additions) + '\n', body, count=1)
    if methods:
        body = re.sub(r'\n\}\s*$', '\n' + '\n'.join(methods) + '\n}\n', body, count=1)
    if body != original:
        vo_path.write_text(body, encoding='utf-8')
        return True
    return False


def _remove_lines_with_markers(body: str, markers: List[str]) -> str:
    lines = body.splitlines()
    lowered = [m.lower() for m in markers if m]
    kept = [line for line in lines if not any(marker in line.lower() for marker in lowered)]
    return '\n'.join(kept) + ('\n' if body.endswith('\n') else '')


def _sanitize_ui_metadata_and_sensitive_refs(body: str, markers: List[str]) -> str:
    updated = body
    for marker in [m for m in markers if m]:
        updated = re.sub(rf"<c:out[^>]*value=([\"\'])\s*\$\{{[^}}]*{re.escape(marker)}[^}}]*\}}\s*\1\s*/>", '', updated, flags=re.IGNORECASE)
        updated = re.sub(rf"<[^>]*(?:name|id|for|path|items|value)\s*=\s*['\"][^'\"]*{re.escape(marker)}[^'\"]*['\"][^>]*>.*?</[^>]+>", '', updated, flags=re.IGNORECASE | re.DOTALL)
        updated = re.sub(rf"<[^>]*(?:name|id|for|path|value)\s*=\s*['\"][^'\"]*{re.escape(marker)}[^'\"]*['\"][^>]*/?>", '', updated, flags=re.IGNORECASE | re.DOTALL)
        updated = re.sub(rf'\$\{{[^}}]*{re.escape(marker)}[^}}]*\}}', '', updated, flags=re.IGNORECASE)
        updated = re.sub(rf'#\{{[^}}]*{re.escape(marker)}[^}}]*\}}', '', updated, flags=re.IGNORECASE)
        updated = re.sub(rf'.*{re.escape(marker)}.*(?:\n|$)', '', updated, flags=re.IGNORECASE)
    updated = _remove_lines_with_markers(updated, markers)
    updated = re.sub(r'\n{3,}', '\n\n', updated)
    return updated

def _primary_schema_path(project_root: Path | None, issue: Dict[str, Any] | None = None) -> Path | None:
    if project_root is None:
        return None
    root = Path(project_root)
    canonical = root / "src/main/resources/schema.sql"
    if canonical.exists():
        return canonical
    details = (issue or {}).get("details") or {}
    rel = _normalize_rel_path(details.get("schema_path") or "src/main/resources/schema.sql")
    candidate = root / rel
    if candidate.exists():
        return candidate
    db_fallback = root / "src/main/resources/db/schema.sql"
    if db_fallback.exists():
        return db_fallback
    return canonical


def _schema_variant_paths(project_root: Path | None) -> List[Path]:
    if project_root is None:
        return []
    db_dir = Path(project_root) / "src/main/resources/db"
    if not db_dir.exists():
        return []
    return sorted(p for p in db_dir.glob("schema*.sql") if p.is_file())


def _sync_schema_variants_from_primary(project_root: Path | None, primary_path: Path | None = None) -> bool:
    if project_root is None:
        return False
    root = Path(project_root)
    primary = primary_path or _primary_schema_path(root)
    if primary is None or not primary.exists():
        return False
    primary_text = _read_text(primary)
    changed = False

    canonical = root / "src/main/resources/schema.sql"
    if primary.resolve() != canonical.resolve():
        canonical.parent.mkdir(parents=True, exist_ok=True)
        if not canonical.exists() or _read_text(canonical) != primary_text:
            canonical.write_text(primary_text, encoding='utf-8')
            changed = True

    for variant in _schema_variant_paths(root):
        if variant.resolve() == primary.resolve():
            continue
        if not variant.exists() or _read_text(variant) != primary_text:
            variant.parent.mkdir(parents=True, exist_ok=True)
            variant.write_text(primary_text, encoding='utf-8')
            changed = True
    return changed


def _split_sql_columns(body: str) -> List[str]:
    return [chunk.strip() for chunk in re.split(r",\s*(?![^()]*\))", body or '') if chunk and chunk.strip()]



def _iter_create_table_matches(schema_text: str):
    start_pat = re.compile(r'create\s+table\s+(?:if\s+not\s+exists\s+)?[`\"]?([A-Za-z_][\w]*)[`\"]?\s*\(', re.IGNORECASE)
    pos = 0
    while True:
        match = start_pat.search(schema_text, pos)
        if not match:
            break
        idx = match.end()
        depth = 1
        in_single = False
        in_double = False
        while idx < len(schema_text):
            ch = schema_text[idx]
            prev = schema_text[idx - 1] if idx > 0 else ''
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
                        yield {
                            'match': match,
                            'table': match.group(1),
                            'columns_body': schema_text[match.end():idx],
                            'start': match.start(),
                            'end': idx + 1,
                        }
                        pos = idx + 1
                        break
            idx += 1
        else:
            break



def _parse_schema_table_ranges(schema_text: str) -> Dict[str, Dict[str, Any]]:
    tables: Dict[str, Dict[str, Any]] = {}
    for item in _iter_create_table_matches(schema_text):
        table = str(item.get('table') or '').strip().lower()
        block = item.get('columns_body') or ''
        columns: List[str] = []
        comments: Dict[str, str] = {}
        for raw in _split_sql_columns(block):
            stripped = raw.strip()
            if not stripped or stripped.startswith('--'):
                continue
            col_match = re.match(r'[`\"]?([A-Za-z_][\w]*)[`\"]?\s+', stripped)
            if not col_match:
                continue
            name = (col_match.group(1) or '').strip().lower()
            if name in {'primary', 'unique', 'constraint', 'foreign', 'key', 'index'}:
                continue
            if name not in columns:
                columns.append(name)
            cm = re.search(r"\bCOMMENT\s+'((?:[^']|''|\\')*)'", stripped, re.IGNORECASE)
            if cm:
                comments[name] = (cm.group(1) or '').replace("''", "'").strip()
        for cm in re.finditer(rf"comment\s+on\s+column\s+{re.escape(table)}\.([A-Za-z_][\w]*)\s+is\s+[\"']([^\"']*)[\"']", schema_text, re.IGNORECASE):
            comments[(cm.group(1) or '').strip().lower()] = (cm.group(2) or '').strip()
        tables[table] = {
            'columns': columns,
            'comments': comments,
            'match': item.get('match'),
            'start': item.get('start'),
            'end': item.get('end'),
        }
    return tables


_AUTH_RELATED_COLUMN_MARKERS = {'password', 'login_password', 'loginpassword', 'passwd', 'pwd', 'login_id', 'loginid', 'user_id', 'userid', 'role_cd', 'rolecd'}
_AUTH_TABLE_NAME_HINTS = ('login', 'user', 'account', 'member', 'auth', 'signin', 'signup', 'credential', 'session', 'jwt', 'cert')
_NON_AUTH_TABLE_NAME_HINTS = ('schedule', 'calendar', 'reservation', 'booking', 'meeting', 'board', 'notice', 'post', 'article', 'content')


def _looks_auth_table_name(name: str) -> bool:
    low = (name or '').strip().lower()
    if not low:
        return False
    if any(token in low for token in _NON_AUTH_TABLE_NAME_HINTS):
        return False
    return any(token in low for token in _AUTH_TABLE_NAME_HINTS)


def _split_insert_suffix(rest: str) -> tuple[str, str]:
    text = str(rest or '').strip()
    if not text:
        return '', ''
    depth = 0
    in_single = False
    in_double = False
    for idx, ch in enumerate(text):
        prev = text[idx - 1] if idx > 0 else ''
        if ch == "'" and not in_double and prev != '\\':
            in_single = not in_single
        elif ch == '"' and not in_single and prev != '\\':
            in_double = not in_double
        elif not in_single and not in_double:
            if ch == '(':
                depth += 1
            elif ch == ')' and depth > 0:
                depth -= 1
            elif depth == 0 and text[idx:idx + 5].lower() == 'where' and (idx == 0 or text[idx - 1].isspace()):
                return text[:idx].strip(), text[idx:].strip()
    return text, ''


def _rewrite_insert_statement_for_known_columns(stmt: str, known_columns: List[str]) -> str:
    match = re.match(r'^\s*insert\s+into\s+[`\"]?([A-Za-z_][\w]*)[`\"]?\s*\((.*?)\)\s*(select|values)\s*(.*)$', stmt.strip(), re.IGNORECASE | re.DOTALL)
    if not match:
        return stmt.strip().rstrip(';') + ';'
    table = (match.group(1) or '').strip()
    table_low = table.lower()
    cols = [c.strip(' `\"').strip() for c in _split_sql_columns(match.group(2) or '')]
    keyword = (match.group(3) or '').strip().lower()
    remainder = match.group(4) or ''
    normalized_cols = [c.lower() for c in cols]
    known = {str(col or '').strip().lower() for col in (known_columns or []) if str(col or '').strip()}
    invalid_indexes = [idx for idx, col in enumerate(normalized_cols) if col and col not in known]
    if not invalid_indexes:
        return stmt.strip().rstrip(';') + ';'
    has_auth_markers = any(col in _AUTH_RELATED_COLUMN_MARKERS for col in normalized_cols)
    if has_auth_markers and not _looks_auth_table_name(table_low):
        return ''
    if keyword == 'values':
        values_match = re.match(r'^\((.*)\)\s*(.*)$', remainder.strip(), re.IGNORECASE | re.DOTALL)
        if not values_match:
            return '' if has_auth_markers else stmt.strip().rstrip(';') + ';'
        value_items = [v.strip() for v in _split_sql_columns(values_match.group(1) or '')]
        suffix = (values_match.group(2) or '').strip()
    else:
        value_exprs, suffix = _split_insert_suffix(remainder)
        value_items = [v.strip() for v in _split_sql_columns(value_exprs or '')]
    if len(value_items) != len(cols):
        return '' if has_auth_markers else stmt.strip().rstrip(';') + ';'
    keep_indexes = [idx for idx in range(len(cols)) if idx not in invalid_indexes]
    if not keep_indexes:
        return ''
    kept_cols = [cols[idx] for idx in keep_indexes]
    kept_values = [value_items[idx] for idx in keep_indexes]
    if keyword == 'values':
        rebuilt = f"INSERT INTO {table} ({', '.join(kept_cols)}) VALUES ({', '.join(kept_values)})"
    else:
        rebuilt = f"INSERT INTO {table} ({', '.join(kept_cols)}) SELECT {', '.join(kept_values)}"
    if suffix:
        rebuilt += f" {suffix.strip()}"
    return rebuilt.strip().rstrip(';') + ';'


def _sanitize_data_sql_against_schema(data_path: Path, schema_path: Path | None) -> bool:
    if data_path is None or not data_path.exists() or schema_path is None or not schema_path.exists():
        return False
    schema_tables = _parse_schema_table_ranges(_read_text(schema_path))
    if not schema_tables:
        return False
    body = _read_text(data_path)
    statements = [chunk.strip() for chunk in re.split(r';\s*', body or '') if chunk.strip()]
    if not statements:
        return False
    updated: List[str] = []
    changed = False
    for stmt in statements:
        match = re.match(r'^\s*insert\s+into\s+[`\"]?([A-Za-z_][\w]*)[`\"]?', stmt, re.IGNORECASE)
        if not match:
            updated.append(stmt.rstrip(';') + ';')
            continue
        table = (match.group(1) or '').strip().lower()
        known_columns = list((schema_tables.get(table) or {}).get('columns') or [])
        if not known_columns:
            updated.append(stmt.rstrip(';') + ';')
            continue
        rewritten = _rewrite_insert_statement_for_known_columns(stmt, known_columns)
        if rewritten != stmt.strip().rstrip(';') + ';':
            changed = True
        if rewritten:
            updated.append(rewritten)
        else:
            changed = True
    rendered = '\n\n'.join(updated).strip()
    rendered = rendered + ('\n' if rendered else '')
    if changed and rendered != body:
        data_path.write_text(rendered, encoding='utf-8')
        return True
    return False



def _parse_mapper_contract_from_file(mapper_path: Path) -> Dict[str, Any]:
    body = _read_text(mapper_path)
    table_names: List[str] = []
    for pattern in (
        r'insert\s+into\s+[`\"]?([A-Za-z_][\w]*)[`\"]?',
        r'update\s+[`\"]?([A-Za-z_][\w]*)[`\"]?',
        r'delete\s+from\s+[`\"]?([A-Za-z_][\w]*)[`\"]?',
        r'from\s+[`\"]?([A-Za-z_][\w]*)[`\"]?',
    ):
        for m in re.finditer(pattern, body, re.IGNORECASE):
            name = (m.group(1) or '').strip().lower()
            if name and name not in table_names:
                table_names.append(name)
    table = table_names[0] if table_names else ''
    specs: List[tuple[str, str]] = []
    insert_pat = re.compile(r'insert\s+into\s+[`\"]?([A-Za-z_][\w]*)[`\"]?\s*\((.*?)\)\s*values\s*\((.*?)\)', re.IGNORECASE | re.DOTALL)
    for m in insert_pat.finditer(body):
        current_table = (m.group(1) or '').strip().lower()
        if table and current_table != table:
            continue
        cols = [c.strip(' `\"') for c in _split_sql_columns(m.group(2) or '')]
        vals = [v.strip() for v in _split_sql_columns(m.group(3) or '')]
        for col, val in zip(cols, vals):
            ph = re.search(r'#\{\s*([A-Za-z_][\w]*)\s*\}', val)
            prop = ph.group(1) if ph else ''
            if col:
                specs.append((prop or col, col))
    update_pat = re.compile(r'update\s+[`\"]?([A-Za-z_][\w]*)[`\"]?\s+set\s+(.*?)\s+where\s+', re.IGNORECASE | re.DOTALL)
    for m in update_pat.finditer(body):
        current_table = (m.group(1) or '').strip().lower()
        if table and current_table != table:
            continue
        for raw in _split_sql_columns(m.group(2) or ''):
            mm = re.search(r'[`\"]?([A-Za-z_][\w]*)[`\"]?\s*=\s*#\{\s*([A-Za-z_][\w]*)\s*\}', raw)
            if mm:
                specs.append((mm.group(2), mm.group(1)))
    result_pat = re.compile(r'<(?:id|result)\s+[^>]*property=[\"\']([A-Za-z_][\w]*)[\"\'][^>]*column=[\"\']([A-Za-z_][\w]*)[\"\']', re.IGNORECASE)
    for prop, col in result_pat.findall(body):
        specs.append((prop, col))
    columns: List[str] = []
    seen: set[str] = set()
    for _prop, col in specs:
        cl = (col or '').strip().lower()
        if cl and cl not in seen:
            seen.add(cl)
            columns.append(cl)
    return {'table': table, 'columns': columns}


def _is_generation_metadata_column(name: str) -> bool:
    low = str(name or '').strip().lower()
    compact = re.sub(r'[^a-z0-9_]+', '_', low).strip('_')
    return bool(compact) and (compact in _NON_AUTH_GENERATION_METADATA_MARKERS or compact in {'compile', 'compiled', 'build', 'runtime', 'startup', 'endpoint_smoke'})


def _sanitize_mapper_schema_columns(columns: Iterable[str]) -> List[str]:
    cleaned: List[str] = []
    suspicious_only = {'string', 'varchar', 'char', 'text', 'integer', 'number'}
    for col in columns or []:
        low = str(col or '').strip().lower()
        if not low or low in suspicious_only or _is_generation_metadata_column(low):
            continue
        if low not in cleaned:
            cleaned.append(low)
    return cleaned


def _guess_comment_for_column(column: str) -> str:
    column = (column or '').strip().lower()
    overrides = {'event_date': '행사일자', 'room_list': '회의실목록', 'check_result': '점검결과', 'title': '제목', 'start_datetime': '시작일시', 'end_datetime': '종료일시', 'status_cd': '상태코드', 'member_id': '회원 고유 ID', 'login_id': '로그인 아이디', 'member_name': '회원명', 'approval_status': '승인 상태', 'use_yn': '사용 여부', 'role_cd': '역할 코드', 'reg_dt': '등록일시'}
    if column in overrides:
        return overrides[column]
    return f'{column} 컬럼'


def _strip_comment_on_column_statements(body: str, table_names: Iterable[str] | None = None) -> str:
    names = [str(name or '').strip().lower() for name in (table_names or []) if str(name or '').strip()]
    if names:
        for name in names:
            body = re.sub(
                rf"\n?comment\s+on\s+column\s+{re.escape(name)}\.[A-Za-z_][\w]*\s+is\s+['\"](?:[^'\"]|''|\\['\"])*['\"]\s*;?",
                '',
                body,
                flags=re.IGNORECASE,
            )
        return body
    return re.sub(
        r"\n?comment\s+on\s+column\s+[A-Za-z_][\w]*\.[A-Za-z_][\w]*\s+is\s+['\"](?:[^'\"]|''|\\['\"])*['\"]\s*;?",
        '',
        body,
        flags=re.IGNORECASE,
    )


def _sync_schema_table_from_mapper(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None, cascade: bool = True) -> bool:
    if project_root is None:
        return False
    details = (issue or {}).get('details') or {}
    mapper_contract = _parse_mapper_contract_from_file(path) if path.exists() else {'table': '', 'columns': []}
    table = (details.get('table') or mapper_contract.get('table') or '').strip().lower()
    mapper_columns = _sanitize_mapper_schema_columns(details.get('mapper_columns') or mapper_contract.get('columns') or [])
    primary = _primary_schema_path(Path(project_root), issue)
    if not table or not mapper_columns or primary is None or not primary.exists():
        return False
    body = _read_text(primary)
    original = body
    tables = _parse_schema_table_ranges(body)

    info = tables.get(table)
    source_table = table
    if not info:
        alias_candidates: List[str] = []
        if table.startswith('tb_'):
            alias_candidates.append(table[3:])
        else:
            alias_candidates.append(f'tb_{table}')
        for candidate in alias_candidates:
            if candidate in tables:
                info = tables[candidate]
                source_table = candidate
                break
    existing_comments = dict((info or {}).get('comments') or {})
    escaped_comments = {col: (existing_comments.get(col) or _guess_comment_for_column(col)).replace("'", "''") for col in mapper_columns}
    column_lines = []
    for idx, column in enumerate(mapper_columns):
        suffix = ',' if idx < len(mapper_columns) - 1 else ''
        column_lines.append(f"    {column} VARCHAR(255) COMMENT '{escaped_comments[column]}'{suffix}")
    new_block = f'CREATE TABLE IF NOT EXISTS {table} (\n' + '\n'.join(column_lines) + '\n);'

    if info and info.get('start') is not None and info.get('end') is not None:
        body = body[:int(info['start'])] + new_block + body[int(info['end']):]
    else:
        body = body.rstrip() + '\n\n' + new_block + '\n'

    body = _strip_comment_on_column_statements(body, {table, source_table})

    changed = body != original
    if changed:
        primary.write_text(body, encoding='utf-8')
    variant_changed = _sync_schema_variants_from_primary(Path(project_root), primary)
    cascade_changed = False
    if cascade and (changed or variant_changed):
        cascade_changed = _harmonize_all_mapper_schema_tables(Path(project_root), table)
        if cascade_changed:
            _sync_schema_variants_from_primary(Path(project_root), _primary_schema_path(Path(project_root), issue))
    return bool(changed or variant_changed or cascade_changed)


def _harmonize_all_mapper_schema_tables(project_root: Path | None, preferred_table: str = "") -> bool:
    if project_root is None:
        return False
    root = Path(project_root)
    resources_root = root / "src/main/resources"
    if not resources_root.exists():
        return False
    changed = False
    mapper_paths = sorted(resources_root.rglob('*Mapper.xml'))
    preferred = (preferred_table or '').strip().lower()
    ordered: List[Path] = []
    if preferred:
        for mapper_path in mapper_paths:
            contract = _parse_mapper_contract_from_file(mapper_path)
            if (contract.get('table') or '').strip().lower() == preferred:
                ordered.append(mapper_path)
        for mapper_path in mapper_paths:
            if mapper_path not in ordered:
                ordered.append(mapper_path)
    else:
        ordered = mapper_paths
    for mapper_path in ordered:
        contract = _parse_mapper_contract_from_file(mapper_path)
        table = (contract.get('table') or '').strip().lower()
        columns = [str(c or '').strip().lower() for c in (contract.get('columns') or []) if str(c or '').strip()]
        if not table or not columns:
            continue
        fake_issue = {'details': {'table': table, 'mapper_columns': columns}}
        if _sync_schema_table_from_mapper(mapper_path, fake_issue, root, cascade=False):
            changed = True
    return changed


def _ensure_schema_column_comments(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    if project_root is None or issue is None:
        return False
    details = issue.get('details') or {}
    table = (details.get('table') or '').strip().lower()
    missing_comments = _sanitize_mapper_schema_columns(details.get('missing_comments') or [])
    primary = _primary_schema_path(Path(project_root), issue)
    if not table or not missing_comments or primary is None or not primary.exists():
        return False
    pre_sync_changed = _sync_schema_table_from_mapper(path, issue, project_root, cascade=False)
    body = _read_text(primary)
    original = body
    tables = _parse_schema_table_ranges(body)
    info = tables.get(table)
    if info and info.get('start') is not None and info.get('end') is not None:
        block_text = body[int(info['start']):int(info['end'])]
        updated_block = block_text
        for column in missing_comments:
            comment = _guess_comment_for_column(column).replace("'", "''")
            updated_block = re.sub(
                rf'([`\"]?{re.escape(column)}[`\"]?\s+[^,\n]*?)(\s+COMMENT\s+\'(?:[^\']|\'\')*\')?(\s*,|\s*$)',
                lambda m: f"{m.group(1)} COMMENT '{comment}'{m.group(3)}",
                updated_block,
                count=1,
                flags=re.IGNORECASE | re.MULTILINE,
            )
        body = body[:int(info['start'])] + updated_block + body[int(info['end']):]
    body = _strip_comment_on_column_statements(body, {table})
    changed = body != original
    if changed:
        primary.write_text(body, encoding='utf-8')
    variant_changed = _sync_schema_variants_from_primary(Path(project_root), primary)
    return bool(pre_sync_changed or changed or variant_changed)


def _inject_calendar_model_aliases(body: str) -> str:
    alias_specs = [
        ('calendarCells', 'calendarcells'),
        ('selectedDateSchedules', 'selecteddateschedules'),
        ('currentYear', 'currentyear'),
        ('currentMonth', 'currentmonth'),
        ('prevYear', 'prevyear'),
        ('prevMonth', 'prevmonth'),
        ('nextYear', 'nextyear'),
        ('nextMonth', 'nextmonth'),
    ]
    updated = body
    for source_key, alias_key in alias_specs:
        low = updated.lower()
        if f'model.addattribute("{alias_key}"' in low or f"model.addattribute('{alias_key}'" in low:
            continue
        pattern = re.compile(rf"(\s*model\.addAttribute\(\s*[\"']{re.escape(source_key)}[\"']\s*,\s*(.+?)\)\s*;)", re.DOTALL)
        match = pattern.search(updated)
        if not match:
            continue
        expr = (match.group(2) or '').strip()
        insertion = f'\n        model.addAttribute("{alias_key}", {expr});'
        updated = updated[:match.end(1)] + insertion + updated[match.end(1):]
    return updated

def _sanitize_button_attrs(attrs: str) -> str:
    attrs = (attrs or "").strip()
    if not attrs:
        return ""
    attrs = re.sub(r'\s+type\s*=\s*"[^"]*"', '', attrs, flags=re.IGNORECASE)
    attrs = re.sub(r"\s+type\s*=\s*'[^']*'", '', attrs, flags=re.IGNORECASE)
    attrs = re.sub(r'\s+formaction\s*=\s*"[^"]*"', '', attrs, flags=re.IGNORECASE)
    attrs = re.sub(r"\s+formaction\s*=\s*'[^']*'", '', attrs, flags=re.IGNORECASE)
    attrs = re.sub(r'\s+formmethod\s*=\s*"[^"]*"', '', attrs, flags=re.IGNORECASE)
    attrs = re.sub(r"\s+formmethod\s*=\s*'[^']*'", '', attrs, flags=re.IGNORECASE)
    attrs = re.sub(r'\s+', ' ', attrs).strip()
    return f" {attrs}" if attrs else ""


def _repair_duplicate_boolean_getters(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    body = _read_text(path)
    original = body
    body = _remove_non_auth_forbidden_ui_fields(body)
    for match in re.finditer(r'private\s+(Boolean|boolean)\s+(\w+)\s*;', body):
        prop = match.group(2)
        cap = prop[:1].upper() + prop[1:]
        body = re.sub(
            rf'\s*public\s+(?:Boolean|boolean)\s+is{re.escape(cap)}\s*\([^\)]*\)\s*\{{[^}}]*\}}\s*',
            '\n',
            body,
            flags=re.DOTALL,
        )
    if body != original:
        path.write_text(body, encoding="utf-8")
        return True
    return False


def _repair_temporal_inputs(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    body = _read_text(path)
    original = body
    body = _remove_non_auth_forbidden_ui_fields(body)

    def repl(match: re.Match[str]) -> str:
        tag = match.group(0)
        name = match.group(1)
        if "datetime" in name.lower():
            desired = 'type="datetime-local" data-autopj-temporal="datetime-local"'
        elif "date" in name.lower() and "time" not in name.lower():
            desired = 'type="date" data-autopj-temporal="date"'
        elif name.lower().endswith("time") and "date" not in name.lower():
            desired = 'type="time"'
        else:
            return tag
        if re.search(r'type="[^"]+"', tag, re.IGNORECASE):
            return re.sub(r'type="[^"]+"(?:\s+data-autopj-temporal="[^"]+")?', desired, tag, count=1, flags=re.IGNORECASE)
        return tag.replace("<input", f"<input {desired}", 1)

    body = re.sub(r'<input[^>]+name="([^"]*(?:date|time|datetime)[^"]*)"[^>]*>', repl, body, flags=re.IGNORECASE)
    if body != original:
        path.write_text(body, encoding="utf-8")
        return True
    return False


def _repair_delete_ui(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    """Add a delete action to the matching domain JSP when a delete endpoint exists."""
    details = (issue or {}).get("details") or {}
    message = str((issue or {}).get("message") or "")
    root = Path(project_root) if project_root is not None else None

    def _camel_from_stem(stem: str) -> str:
        base = stem[:-10] if stem.endswith('Controller') else stem
        return base[:1].lower() + base[1:] if base else ''

    def _first_mapping_route(ann_text: str) -> str:
        m = re.search(r"[\"'](/[^\"']+)[\"']", ann_text or '')
        return (m.group(1) or '').strip() if m else ''

    def _infer_from_controller(controller: Path) -> tuple[str, str, str]:
        if not controller.exists():
            return '', '', ''
        body = _read_text(controller)
        info = _controller_domain_and_prefix(body, controller)
        domain = str(info.get('domain') or _camel_from_stem(controller.stem)).strip()
        prefix = str(info.get('prefix') or (('/' + domain) if domain else '')).strip()
        route = ''
        id_param = ''
        for m in re.finditer(r'@(?:PostMapping|RequestMapping)\s*\((?P<ann>[^)]*)\)', body, re.IGNORECASE | re.DOTALL):
            ann = m.group('ann') or ''
            if 'delete' not in ann.lower() and 'remove' not in ann.lower():
                continue
            route = _combine_controller_route(prefix, _first_mapping_route(ann) or '/delete.do')
            chunk = body[m.end(): m.end() + 700]
            p1 = re.search(r"@RequestParam\s*\(\s*(?:value\s*=\s*)?[\"\']([^\"\']+)[\"\']", chunk)
            if p1:
                id_param = p1.group(1).strip()
            break
        if not route and domain:
            route = f'/{domain}/delete.do'
        if not id_param:
            id_param = str(details.get('id_prop') or details.get('field') or details.get('id_param') or '').strip()
        if not id_param:
            id_param = f'{domain}Id' if domain else 'id'
        return domain, route, id_param

    domain = str(details.get('domain') or '').strip()
    route = str(details.get('delete_route') or ((details.get('delete_routes') or [None])[0]) or '').strip()
    id_prop = str(details.get('id_prop') or details.get('field') or details.get('id_param') or '').strip()

    if not domain:
        m = re.search(r'\bin\s+([A-Za-z][A-Za-z0-9_]*)\b', message)
        if m:
            domain = m.group(1).strip()
    if path.suffix.lower() == '.java' or path.name.endswith('Controller.java'):
        c_domain, c_route, c_id = _infer_from_controller(path)
        domain = domain or c_domain
        route = route or c_route
        id_prop = id_prop or c_id
    if not domain:
        if path.suffix.lower() == '.jsp':
            rel = _normalize_rel_path(str(path))
            m = re.search(r'WEB-INF/views/([^/]+)/', rel, re.IGNORECASE)
            domain = m.group(1) if m else path.parent.name
        else:
            domain = _camel_from_stem(path.stem)
    if not route:
        route = f'/{domain}/delete.do' if domain else '/delete.do'
    if not id_prop:
        id_prop = f'{domain}Id' if domain else 'id'

    targets: List[Path] = []
    if path.suffix.lower() == '.jsp' and path.exists():
        targets.append(path)
    elif root is not None:
        view_root = root / 'src/main/webapp/WEB-INF/views'
        wanted = {domain.lower()} if domain else set()
        if view_root.exists() and wanted:
            for jsp_dir in view_root.rglob('*'):
                if jsp_dir.is_dir() and jsp_dir.name.lower() in wanted:
                    preferred: List[Path] = []
                    for suffix in ('List.jsp', 'Detail.jsp', 'Form.jsp'):
                        preferred.extend(sorted(jsp_dir.glob(f'*{suffix}')))
                    preferred.extend(sorted(jsp_dir.glob('*.jsp')))
                    for item in preferred:
                        if item not in targets:
                            targets.append(item)

    def _loop_var(body: str) -> str:
        m = re.search(r"<c:forEach\b[^>]*\bvar=[\"\']([^\"\']+)[\"\']", body, re.IGNORECASE)
        return (m.group(1) or 'item').strip() if m else 'item'

    def _form(loop_var: str) -> str:
        hidden_value = '${' + loop_var + '.' + id_prop + '}'
        return (
            f"<form method=\"post\" action=\"<c:url value='{route}' />\" class=\"autopj-delete-form\" style=\"display:inline;\">"
            f"<input type=\"hidden\" name=\"{id_prop}\" value=\"{hidden_value}\" />"
            "<button type=\"submit\" onclick=\"return confirm('삭제하시겠습니까?');\">삭제</button>"
            "</form>"
        )

    def _insert(body: str) -> str:
        if route.lower() in body.lower() or 'autopj-delete-form' in body.lower():
            return body
        form_html = _form(_loop_var(body))
        for_each = re.search(r'(?is)<c:forEach\b[^>]*>.*?</c:forEach>', body)
        if for_each:
            block = for_each.group(0)
            new_block = re.sub(r'(?is)(</tr>)(?!.*</tr>)', '<td>' + form_html + '</td>\\1', block, count=1)
            if new_block == block:
                new_block = block.replace('</c:forEach>', form_html + '</c:forEach>', 1)
            return body[:for_each.start()] + new_block + body[for_each.end():]
        if '</tr>' in body:
            return body.replace('</tr>', '<td>' + form_html + '</td></tr>', 1)
        if '</table>' in body:
            return body.replace('</table>', form_html + '\n</table>', 1)
        if '</form>' in body:
            return body.replace('</form>', form_html + '</form>', 1)
        return body.rstrip() + '\n' + form_html + '\n'

    changed = False
    for target in targets:
        body = _read_text(target)
        updated = _insert(body)
        if updated != body:
            target.write_text(updated, encoding='utf-8')
            changed = True
    return changed

def _normalize_delete_action_blocks(body: str) -> str:
    original = body
    nested_delete_re = re.compile(
        r'<c:if\s+test="(?P<test>[^"]+)">\s*'
        r"<form[^>]*action=\"<c:url\s+value=['\"](?P<route>[^'\"]+)['\"]\s*/>\"[^>]*>\s*"
        r'(?:<input[^>]*type="hidden"[^>]*name="(?P<name>[^"]+)"[^>]*value="(?P<value>[^"]*)"[^>]*/>\s*)?'
        r'<button(?P<button_attrs>[^>]*)>(?P<label>.*?)</button>\s*'
        r'</form>\s*</c:if>',
        re.IGNORECASE | re.DOTALL,
    )

    def nested_repl(match: re.Match[str]) -> str:
        button_attrs = (match.group("button_attrs") or "").strip()
        label = (match.group("label") or "Delete").strip()
        attrs = _sanitize_button_attrs(button_attrs)
        route = match.group("route")
        test_expr = match.group("test")
        return (
            f"<c:if test=\"{test_expr}\">\n"
            f"        <button type=\"submit\" formaction=\"<c:url value='{route}'/>\" formmethod=\"post\"{attrs}>{label}</button>\n"
            f"      </c:if>"
        )

    body = nested_delete_re.sub(nested_repl, body)

    broken_wrapper_re = re.compile(
        r'<c:if\s+test="(?P<test>[^"]+)">\s*'
        r"<(?:div|span|section|article)\b.*?action=\"<c:url\s+value=['\"](?P<route>[^'\"]+)['\"]/.*?>\s*"
        r'(?:<input[^>]*>\s*)*'
        r'<button(?P<button_attrs>[^>]*)>(?P<label>.*?)</button>\s*'
        r'</(?:div|span|section|article)>\s*</c:if>',
        re.IGNORECASE | re.DOTALL,
    )

    def wrapper_repl(match: re.Match[str]) -> str:
        button_attrs = (match.group("button_attrs") or "").strip()
        label = (match.group("label") or "Delete").strip()
        attrs = _sanitize_button_attrs(button_attrs)
        route = match.group("route")
        test_expr = match.group("test")
        return (
            f"<c:if test=\"{test_expr}\">\n"
            f"        <button type=\"submit\" formaction=\"<c:url value='{route}'/>\" formmethod=\"post\"{attrs}>{label}</button>\n"
            f"      </c:if>"
        )

    body = broken_wrapper_re.sub(wrapper_repl, body)
    body = re.sub(r'(<button[^>]*formaction="[^"]*"[^>]*?)\s+type="submit"', r'\1', body, flags=re.IGNORECASE)
    return body if body != original else original


def _flatten_nested_form_blocks(body: str) -> str:
    text = body
    nested_form_re = re.compile(
        r'(?P<prefix><form[^>]*>)(?P<outer_before>.*?)'
        r'<form(?P<inner_attrs>[^>]*)action="(?P<action>[^"]+)"(?P<inner_rest>[^>]*)method="(?P<method>[^"]+)"(?P<inner_tail>[^>]*)>'
        r'(?P<inner_body>.*?)</form>(?P<outer_after>.*?)</form>',
        re.IGNORECASE | re.DOTALL,
    )

    def repl(match: re.Match[str]) -> str:
        prefix = match.group('prefix') or '<form>'
        outer_before = match.group('outer_before') or ''
        inner_body = match.group('inner_body') or ''
        outer_after = match.group('outer_after') or ''
        action = (match.group('action') or '').strip()
        method = (match.group('method') or 'post').strip().lower()
        hidden_inputs = ''.join(re.findall(r'<input[^>]*type="hidden"[^>]*/?>', inner_body, flags=re.IGNORECASE))
        button_match = re.search(r'<button(?P<attrs>[^>]*)>(?P<label>.*?)</button>', inner_body, flags=re.IGNORECASE | re.DOTALL)
        if button_match:
            attrs = _sanitize_button_attrs(button_match.group('attrs') or '')
            label = (button_match.group('label') or 'Submit').strip()
        else:
            attrs = ''
            label = 'Submit'
        attrs = (attrs + f' formaction="{action}" formmethod="{method}"').strip()
        if attrs and not attrs.startswith(' '):
            attrs = ' ' + attrs
        replacement = f'<button type="submit"{attrs}>{label}</button>'
        return f'{prefix}{outer_before}{hidden_inputs}{replacement}{outer_after}</form>'

    previous = None
    while previous != text:
        previous = text
        text = nested_form_re.sub(repl, text, count=1)
    return text


def _repair_nested_form(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    body = _read_text(path)
    original = body
    body = _remove_non_auth_forbidden_ui_fields(body)
    body = _normalize_delete_action_blocks(body)
    body = _flatten_nested_form_blocks(body)
    if body != original:
        path.write_text(body, encoding="utf-8")
        return True
    return False


def _repair_invalid_action_wrapper(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    body = _read_text(path)
    original = body
    body = _remove_non_auth_forbidden_ui_fields(body)
    body = _normalize_delete_action_blocks(body)
    if body != original:
        path.write_text(body, encoding="utf-8")
        return True
    return False


def _repair_broken_c_url(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    return _repair_invalid_action_wrapper(path, issue, project_root)


def _choose_route_param_repair_target(expected: str, found_values: list[str]) -> str:
    expected = str(expected or '').strip()
    found = [str(item or '').strip() for item in (found_values or []) if str(item or '').strip()]
    unique: list[str] = []
    for item in found:
        if item not in unique:
            unique.append(item)
    if len(unique) == 1:
        actual = unique[0]
        # Prefer a concrete JSP/domain parameter over a generic id, but keep a concrete controller
        # parameter when the JSP only emitted generic id. This keeps the rule schema/domain driven.
        if actual.lower() != 'id':
            return actual
    return expected or (unique[0] if unique else '')


def _mapping_arg_contains_route(ann_args: str, route: str) -> bool:
    ann_args = ann_args or ''
    route = str(route or '').strip()
    if not route:
        return False
    suffix = '/' + route.strip('/').split('/')[-1]
    candidates = {route, suffix}
    for candidate in candidates:
        if re.search(r'["\']' + re.escape(candidate) + r'["\']', ann_args):
            return True
    return False


def _rewrite_controller_request_param_for_routes(body: str, route_to_param: dict[str, str]) -> str:
    if not route_to_param:
        return body
    method_re = re.compile(
        r'(@(?:GetMapping|PostMapping|RequestMapping)\((?P<args>[^)]*)\)\s*(?:\r?\n\s*@[^\r\n]+)*\s*(?:public|protected|private)\s+[^{;]+?\{)',
        re.DOTALL,
    )

    def replace_block(match: re.Match) -> str:
        block = match.group(1) or ''
        ann_args = match.group('args') or ''
        targets = [param for route, param in route_to_param.items() if _mapping_arg_contains_route(ann_args, route) and param]
        if not targets:
            return block
        target = targets[0]
        return re.sub(
            r'(@RequestParam\s*\(\s*(?:value\s*=\s*)?["\'])([^"\']+)(["\'])',
            lambda m: f'{m.group(1)}{target}{m.group(3)}',
            block,
            count=1,
        )

    return method_re.sub(replace_block, body)

def _repair_route_param_mismatch(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    details = (issue or {}).get("details") or {}
    domain = details.get("domain") or ""
    route_params = {str(k or "").strip(): str(v or "").strip() for k, v in (details.get("route_params") or {}).items() if str(k or "").strip() and str(v or "").strip()}
    jsp_paths = [str(item or "").strip() for item in (details.get("jsp_paths") or []) if str(item or "").strip()]
    if not project_root or not domain:
        return False

    root = Path(project_root)
    logical_domain = _logical_domain_name(str(domain or "").strip())
    changed = False

    controller_path = path if path.name.endswith("Controller.java") else (_find_domain_controller(root, logical_domain) or _find_domain_controller(root, str(domain or "").strip()))
    found_params_by_route = {
        str(k or "").strip(): [str(v or "").strip() for v in (vals or []) if str(v or "").strip()]
        for k, vals in (details.get("found_params") or {}).items()
        if str(k or "").strip()
    }
    canonical_route_params: Dict[str, str] = {}
    for route, expected in route_params.items():
        canonical = _choose_route_param_repair_target(expected, found_params_by_route.get(route, []))
        if canonical:
            canonical_route_params[route] = canonical
    if canonical_route_params:
        route_params = canonical_route_params

    if controller_path is not None and route_params:
        controller_body = _read_text(controller_path)
        rewritten_controller_body = _rewrite_controller_request_param_for_routes(controller_body, route_params)
        if rewritten_controller_body != controller_body:
            controller_path.write_text(rewritten_controller_body, encoding="utf-8")
            changed = True

    if controller_path is not None and _is_membership_like_domain(logical_domain):
        if _rewrite_membership_controller_to_safe_routes(controller_path, logical_domain):
            changed = True

    candidate_jsps: List[Path] = []
    if jsp_paths:
        for jsp_rel in jsp_paths:
            candidate = root / _normalize_rel_path(jsp_rel)
            if candidate.exists():
                candidate_jsps.append(candidate)
    jsp_dir = root / "src/main/webapp/WEB-INF/views" / logical_domain
    if jsp_dir.exists():
        candidate_jsps.extend(sorted(jsp_dir.glob("*.jsp")))

    normalized_expected: set[str] = {value for value in route_params.values() if value}
    if not normalized_expected and _is_membership_like_domain(logical_domain):
        normalized_expected.add('memberId' if 'member' in logical_domain.lower() else ('userId' if logical_domain.lower() == 'user' else 'accountId'))

    seen: set[str] = set()
    for jsp in candidate_jsps:
        key = str(jsp)
        if key in seen or not jsp.exists():
            continue
        seen.add(key)
        body = _read_text(jsp)
        original = body
        if _is_membership_like_domain(logical_domain):
            body = _normalize_membership_route_prefixes_in_jsp(
                body,
                logical_domain,
                include_signup_helpers=any(token in _normalize_rel_path(str(jsp)).lower() for token in ("signup.jsp", "register.jsp", "join.jsp")),
            )
        for route, expected in route_params.items():
            normalized_route = str(route or "").strip()
            if not normalized_route:
                continue
            suffix = "/" + normalized_route.strip("/").split("/")[-1]
            preferred_route = f"/{logical_domain}{suffix}"
            route_candidates = {normalized_route, preferred_route}
            for current_route in route_candidates:
                query_pattern = re.compile(rf'(<c:url\s+value=["\']{re.escape(current_route)}["\']\s*/>\?)([A-Za-z0-9_]+)=', re.IGNORECASE)
                body = query_pattern.sub(lambda m: f"{m.group(1)}{expected}=", body)
                href_pattern = re.compile(rf'({re.escape(current_route)}\?)([A-Za-z0-9_]+)=', re.IGNORECASE)
                body = href_pattern.sub(lambda m: f"{m.group(1)}{expected}=", body)
                form_pattern = re.compile(
                    rf'(<form[^>]*{re.escape(current_route)}[^>]*>.*?<input[^>]*type="hidden"[^>]*name=")([^"]+)(")',
                    re.IGNORECASE | re.DOTALL,
                )
                body = form_pattern.sub(lambda m: f"{m.group(1)}{expected}{m.group(3)}", body)
        for expected in normalized_expected:
            body = re.sub(rf'(<c:url\s+value=["\']/{re.escape(logical_domain)}/(?:detail|form|delete|save)\.do["\']\s*/>\?)(?:id|[A-Za-z0-9_]+)=', lambda m: f"{m.group(1)}{expected}=", body, flags=re.IGNORECASE)
            body = re.sub(rf'(/'+ re.escape(logical_domain) + r'/(?:detail|form|delete|save)\.do\?)(?:id|[A-Za-z0-9_]+)=', lambda m: f"{m.group(1)}{expected}=", body, flags=re.IGNORECASE)
            body = re.sub(rf'(<form[^>]*{re.escape("/" + logical_domain + "/delete.do")}[^>]*>.*?<input[^>]*type="hidden"[^>]*name=")(?:id|[A-Za-z0-9_]+)(")', lambda m: f"{m.group(1)}{expected}{m.group(2)}", body, flags=re.IGNORECASE | re.DOTALL)
        if body != original:
            jsp.write_text(body, encoding="utf-8")
            changed = True
    return changed


def _parse_form_fields(form_body: str) -> List[str]:
    names: List[str] = []
    seen = set()
    for pattern in (
        r'<input[^>]+name="([^"]+)"',
        r'<select[^>]+name="([^"]+)"',
        r'<textarea[^>]+name="([^"]+)"',
    ):
        for m in re.finditer(pattern, form_body, re.IGNORECASE):
            name = (m.group(1) or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
    return names


def _repair_missing_view(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    details = (issue or {}).get("details") or {}
    missing_view = details.get("missing_view") or ""
    if not project_root or not missing_view:
        return False
    jsp_path = Path(project_root) / "src/main/webapp/WEB-INF/views" / f"{missing_view}.jsp"
    if jsp_path.exists():
        return False
    jsp_dir = jsp_path.parent
    missing_leaf = jsp_path.stem.lower()
    if missing_leaf in {'register', 'signup', 'join'}:
        form_candidates = sorted(jsp_dir.glob('*Form.jsp'))
        if form_candidates:
            controller_body = _read_text(path)
            target_view = str((jsp_dir.name + '/' + form_candidates[0].stem))
            updated_controller = re.sub(
                rf"return\s+[\"']{re.escape(missing_view)}[\"']\s*;",
                f'return "{target_view}";',
                controller_body,
            )
            if updated_controller != controller_body:
                path.write_text(updated_controller, encoding='utf-8')
                return True
            redirect_body = f'''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<% response.sendRedirect(request.getContextPath() + "/{jsp_dir.name}/form.do"); %>
'''
            jsp_path.parent.mkdir(parents=True, exist_ok=True)
            jsp_path.write_text(redirect_body, encoding='utf-8')
            return True
    domain = jsp_dir.name
    field_names: List[str] = []
    for form in jsp_dir.glob("*Form.jsp"):
        field_names = _parse_form_fields(_read_text(form))
        if field_names:
            break
    if not field_names:
        field_names = ["id"]
    rows = []
    for name in field_names:
        label = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', name).replace('_', ' ').strip().title()
        rows.append(f'        <div class="autopj-field"><span class="autopj-field__label">{label}</span><div class="autopj-field__value"><c:out value="${{item.{name}}}"/></div></div>')
    body = f'''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/><title>{jsp_path.stem}</title></head>
<body>
<%@ include file="/WEB-INF/views/common/header.jsp" %>
<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>
<section class="page-shell master-detail-shell autopj-detail-page">
  <div class="autopj-form-hero page-card">
    <div>
      <p class="autopj-eyebrow">{domain}</p>
      <h2 class="autopj-form-title">{jsp_path.stem}</h2>
      <p class="autopj-form-subtitle">상세 정보를 카드 레이아웃으로 확인합니다.</p>
    </div>
  </div>
  <c:if test="${{not empty item}}">
    <div class="detail-card autopj-form-card">
      <div class="autopj-form-grid">
{chr(10).join(rows)}
      </div>
      <div class="autopj-form-actions">
        <a class="btn btn-secondary" href="<c:url value='/{domain}/list.do'/>">목록으로</a>
      </div>
    </div>
  </c:if>
</section>
</body>
</html>
'''
    jsp_path.parent.mkdir(parents=True, exist_ok=True)
    jsp_path.write_text(body, encoding="utf-8")
    return True


def _ensure_import(body: str, fqcn: str) -> str:
    if f"import {fqcn};" in body:
        return body
    m = re.search(r'package\s+[A-Za-z0-9_.]+\s*;\s*', body)
    if m:
        return body[:m.end()] + f"\nimport {fqcn};" + body[m.end():]
    return f"import {fqcn};\n" + body


def _repair_calendar_controller(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    details = (issue or {}).get("details") or {}
    expected_view = details.get("expected_view") or ""
    if not expected_view:
        return False
    body = _read_text(path)
    original = body
    body = _remove_non_auth_forbidden_ui_fields(body)
    lower = body.lower()
    if '@getmapping("/calendar.do")' in lower or "@getmapping('/calendar.do')" in lower:
        body = re.sub(r'return\s+"[^"]*calendar[^"]*"\s*;', f'return "{expected_view}";', body, count=1, flags=re.IGNORECASE)
    else:
        list_method = re.search(
            r'@GetMapping\(\s*"/list\.do"\s*\)\s*public\s+String\s+\w+\s*\((.*?)\)\s*(throws\s+[^{]+)?\{(.*?)return\s+"[^"]+"\s*;\s*\}',
            body,
            re.DOTALL,
        )
        if list_method:
            params = list_method.group(1) or "Model model"
            throws_clause = (list_method.group(2) or "").strip()
            method_body = list_method.group(3) or ""
            throws_part = f" {throws_clause}" if throws_clause else ""
            new_method = f'''\n\n    @GetMapping("/calendar.do")\n    public String calendar({params}){throws_part}{{{method_body}return "{expected_view}";\n    }}\n'''
            body = body.replace(list_method.group(0), list_method.group(0) + new_method, 1)
        else:
            body = _ensure_import(body, "org.springframework.ui.Model")
            insert_at = body.rfind("}")
            if insert_at != -1:
                body = body[:insert_at] + f'''\n\n    @GetMapping("/calendar.do")\n    public String calendar(Model model) throws Exception {{\n        return "{expected_view}";\n    }}\n''' + body[insert_at:]
    if body != original:
        path.write_text(body, encoding="utf-8")
        return True
    return False


def _repair_duplicate_schema_initializer(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    if path.exists():
        path.unlink()
        return True
    return False


def _repair_duplicate_table_definition(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    if not path.exists():
        return False
    body = _read_text(path)
    updated = _dedupe_create_table_statements(body)
    if updated == body:
        return False
    path.write_text(updated, encoding='utf-8')
    if project_root is not None:
        _sync_schema_variants_from_primary(Path(project_root), path)
    return True


def _repair_calendar_controller_missing(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    if not path.exists() or path.suffix.lower() != '.jsp' or not path.name.endswith('Calendar.jsp'):
        return False
    try:
        path.unlink()
        return True
    except Exception:
        return False


def _repair_schema_variant_conflict(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    details = (issue or {}).get("details") or {}
    primary = details.get("primary") or ""
    variants = details.get("variants") or []
    if not project_root or not primary or not variants:
        return False
    primary_path = Path(project_root) / _normalize_rel_path(primary)
    if not primary_path.exists():
        return False
    return _sync_schema_variants_from_primary(Path(project_root), primary_path)


def _repair_controller_signature_alignment(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    body = _read_text(path)
    original = body
    body = _remove_non_auth_forbidden_ui_fields(body)
    details = (issue or {}).get('details') or {}
    current_type = (details.get('current_type') or '').strip()
    expected_type = (details.get('expected_type') or '').strip()
    current_var_name = (details.get('current_var_name') or details.get('arg_name') or 'id').strip()
    expected_var_name = (details.get('expected_var_name') or details.get('expected_request_param_name') or current_var_name).strip()
    current_request_param_name = (details.get('current_request_param_name') or current_var_name).strip()
    expected_request_param_name = (details.get('expected_request_param_name') or expected_var_name).strip()
    service_method = (details.get('service_method') or '').strip()
    service_var = (details.get('service_var') or '').strip()

    if expected_type.lower() in {'boolean', 'bool'} and current_type.lower() == 'string':
        expected_type = current_type

    if current_type and expected_type and current_type != expected_type:
        body = re.sub(
            rf'(@RequestParam\(([^)]*)\)\s+){re.escape(current_type)}(\s+){re.escape(current_var_name)}\b',
            lambda m: f"{m.group(1)}{expected_type}{m.group(3)}{expected_var_name}",
            body,
        )
        body = re.sub(
            rf'(?<![A-Za-z0-9_$.]){re.escape(current_type)}(\s+){re.escape(current_var_name)}\b',
            lambda m: f"{expected_type}{m.group(1)}{expected_var_name}",
            body,
        )

    if current_request_param_name and expected_request_param_name and current_request_param_name != expected_request_param_name:
        body = re.sub(
            rf"@RequestParam\(([^)]*[\"\']){re.escape(current_request_param_name)}([\"\'][^)]*)\)",
            lambda m: f"@RequestParam({m.group(1)}{expected_request_param_name}{m.group(2)})",
            body,
        )

    if current_var_name and expected_var_name and current_var_name != expected_var_name:
        body = re.sub(rf'\b{re.escape(current_var_name)}\b', expected_var_name, body)

    if service_var and service_method and expected_var_name:
        body = re.sub(
            rf'\b{re.escape(service_var)}\.{re.escape(service_method)}\s*\(\s*[A-Za-z_][A-Za-z0-9_]*\s*\)',
            f'{service_var}.{service_method}({expected_var_name})',
            body,
        )

    if body != original:
        path.write_text(body, encoding='utf-8')
        return True
    return False



def _pick_entry_redirect_route(project_root: Path) -> str:
    java_root = Path(project_root) / "src/main/java"
    preferred: List[str] = []
    fallback: List[str] = []
    if java_root.exists():
        for controller in java_root.rglob("*Controller.java"):
            body = _read_text(controller)
            for route in re.findall(r'@GetMapping\(\s*["\']([^"\']+)["\']\s*\)', body):
                route = (route or '').strip()
                if not route or '{' in route or '}' in route or route in {'/', '/index.do'}:
                    continue
                norm = route.lower()
                if any(token in norm for token in ('/calendar.do', '/list.do', '/login', '/dashboard', '/main')):
                    preferred.append(route)
                else:
                    fallback.append(route)
            for route in re.findall(r'return\s+["\']redirect:([^"\']+)["\']', body):
                route = (route or '').strip()
                if route and route not in {'/', '/index.do'}:
                    preferred.append(route)
    for bucket in (preferred, fallback):
        for route in bucket:
            if route:
                return route if route.startswith('/') else '/' + route
    return '/'


def _repair_index_entrypoint_controller(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    if path.name != 'IndexController.java' and path.stem.lower() not in {'indexcontroller', 'homecontroller', 'maincontroller'}:
        return False
    root = Path(project_root) if project_root else path.parents[4]
    package_match = re.search(r'package\s+([A-Za-z0-9_.]+)\s*;', _read_text(path))
    package_name = package_match.group(1) if package_match else 'egovframework.app.index.web'
    route = _pick_entry_redirect_route(root)
    body = f"""package {package_name};

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class {path.stem} {{

    @GetMapping({{"/", "/index.do"}})
    public String index() {{
        return \"redirect:{route}\";
    }}
}}
"""
    original = _read_text(path)
    if original.strip() == body.strip():
        return False
    path.write_text(body, encoding='utf-8')
    return True

def _repair_optional_param_guard_mismatch(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    body = _read_text(path)
    original = body
    body = _remove_non_auth_forbidden_ui_fields(body)
    details = (issue or {}).get('details') or {}
    var_name = (details.get('current_var_name') or '').strip()
    current_type = (details.get('current_type') or '').strip().split('.')[-1]
    expected_guard = (details.get('expected_guard') or '').strip()
    if not var_name or not expected_guard:
        return False

    guard_patterns = [
        rf'if\s*\(\s*{re.escape(var_name)}\s*!=\s*null\s*&&\s*{re.escape(var_name)}\.longValue\(\)\s*!=\s*0L\s*\)',
        rf'if\s*\(\s*{re.escape(var_name)}\s*!=\s*null\s*&&\s*{re.escape(var_name)}\.intValue\(\)\s*!=\s*0\s*\)',
        rf'if\s*\(\s*{re.escape(var_name)}\s*!=\s*null\s*&&\s*!\s*{re.escape(var_name)}\.isBlank\(\)\s*\)',
        rf'if\s*\(\s*{re.escape(var_name)}\s*!=\s*0L\s*\)',
        rf'if\s*\(\s*{re.escape(var_name)}\s*!=\s*0\s*\)',
    ]
    replacement = f'if ({expected_guard})'
    for pattern in guard_patterns:
        body = re.sub(pattern, replacement, body)

    if current_type == 'String':
        body = re.sub(rf'\b{re.escape(var_name)}\.longValue\(\)', var_name, body)
        body = re.sub(rf'\b{re.escape(var_name)}\.intValue\(\)', var_name, body)

    if body != original:
        path.write_text(body, encoding='utf-8')
        return True
    return False


def _select_replacement_prop(missing_prop: str, available_props: List[str], suggested: str = '') -> str:
    available = [str(p or '').strip() for p in (available_props or []) if str(p or '').strip()]
    if suggested and suggested in available:
        return suggested
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
    hit = low_map.get(low_missing)
    if hit:
        return hit
    close = difflib.get_close_matches(missing_prop, available, n=1, cutoff=0.72)
    return close[0] if close else ''


def _replace_jsp_missing_property(body: str, var_name: str, missing_prop: str, replacement_prop: str = '') -> str:
    if replacement_prop:
        body = body.replace(f'{var_name}.{missing_prop}', f'{var_name}.{replacement_prop}')
        body = re.sub(rf'\$\{{\s*{re.escape(var_name)}\.{re.escape(missing_prop)}\s*\}}', '${' + var_name + '.' + replacement_prop + '}', body)
        body = re.sub(rf'#\{{\s*{re.escape(var_name)}\.{re.escape(missing_prop)}\s*\}}', '#{' + var_name + '.' + replacement_prop + '}', body)
        return body

    body = re.sub(
        rf"value\s*=\s*([\"'])\s*<c:out\s+value=([\"'])\s*\$\{{\s*{re.escape(var_name)}\.{re.escape(missing_prop)}\s*\}}\s*\2\s*/>\s*\1",
        'value=""',
        body,
        flags=re.IGNORECASE,
    )
    body = re.sub(
        rf"<c:out\s+value=([\"'])\s*\$\{{\s*{re.escape(var_name)}\.{re.escape(missing_prop)}\s*\}}\s*\1\s*/>",
        '<c:out value=""/>',
        body,
        flags=re.IGNORECASE,
    )
    body = re.sub(
        rf"test=([\"'])\s*\$\{{\s*not\s+empty\s+{re.escape(var_name)}\.{re.escape(missing_prop)}\s*\}}\s*\1",
        'test="false"',
        body,
        flags=re.IGNORECASE,
    )
    body = re.sub(
        rf"test=([\"'])\s*\$\{{\s*empty\s+{re.escape(var_name)}\.{re.escape(missing_prop)}\s*\}}\s*\1",
        'test="true"',
        body,
        flags=re.IGNORECASE,
    )
    body = re.sub(rf'\$\{{\s*{re.escape(var_name)}\.{re.escape(missing_prop)}\s*\}}', '', body)
    body = re.sub(rf'#\{{\s*{re.escape(var_name)}\.{re.escape(missing_prop)}\s*\}}', '', body)
    return body


def _repair_jsp_vo_property_mismatch(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    body = _read_text(path)
    original = body
    body = _remove_non_auth_forbidden_ui_fields(body)
    details = (issue or {}).get('details') or {}
    missing_props = [str(p or '').strip() for p in (details.get('missing_props') or []) if str(p or '').strip()]
    rel_low = _normalize_rel_path(str(path)).lower()
    if project_root is not None and any(_is_non_auth_forbidden_field(prop) or str(prop).strip().lower() == 'id' for prop in missing_props):
        root = Path(project_root)
        rel = _normalize_rel_path(str(path.relative_to(root)))
        schema = _infer_schema_for_jsp_repair(path, root)
        available_props = [str(p or '').strip() for p in (details.get('available_props') or []) if str(p or '').strip()]
        mapper_props = [str(p or '').strip() for p in (details.get('mapper_props') or []) if str(p or '').strip()]
        candidate_props: List[str] = []
        for prop in available_props + mapper_props:
            if not prop or _is_non_auth_forbidden_field(prop) or prop.lower() == 'id':
                continue
            if prop not in candidate_props:
                candidate_props.append(prop)
        is_signup_like = _is_signup_route_jsp_path(path) or any(token in rel_low for token in ('signup.jsp', 'register.jsp', 'join.jsp'))
        preferred_id_props = ['memberId', 'userId', 'accountId', 'loginId']
        replacement_id = next((cand for cand in preferred_id_props + candidate_props if cand in candidate_props), '')
        if is_signup_like and replacement_id:
            missing_by_var = details.get('missing_props_by_var') or {'item': ['id'], 'member': ['id'], 'signup': ['id']}
            for var_name, props in missing_by_var.items():
                for missing_prop in props or []:
                    if str(missing_prop or '').strip().lower() == 'id':
                        body = _replace_jsp_missing_property(body, str(var_name or '').strip() or 'item', 'id', replacement_id)
            if body != original:
                path.write_text(body, encoding='utf-8')
                return True
        base_fields = [field for field in list(getattr(schema, 'fields', []) or []) if not _is_non_auth_forbidden_field((field[0] if isinstance(field, (list, tuple)) and field else '')) and not _is_non_auth_forbidden_field((field[1] if isinstance(field, (list, tuple)) and len(field) > 1 else '')) and str((field[0] if isinstance(field, (list, tuple)) and field else '')).strip().lower() != 'id']
        if candidate_props:
            existing = {str((field[0] if isinstance(field, (list, tuple)) and field else '')).strip() for field in base_fields}
            for prop in candidate_props:
                if prop in existing:
                    continue
                base_fields.append((prop, _snake_case_from_prop(prop) or prop, 'String'))
        safe_schema = schema_for(
            getattr(schema, 'entity', None) or path.parent.name[:1].upper() + path.parent.name[1:] or 'Item',
            inferred_fields=base_fields or [('name', 'name', 'String'), ('regDt', 'reg_dt', 'String')],
            table=getattr(schema, 'table', None) or path.parent.name or 'item',
            feature_kind=FEATURE_KIND_CRUD,
        )
        if rel_low.endswith('list.jsp') and _rewrite_list_jsp_from_schema(root, rel, safe_schema):
            return True
        if rel_low.endswith('detail.jsp') and _rewrite_detail_jsp_from_schema(root, rel, safe_schema):
            return True
        if rel_low.endswith('form.jsp') and _rewrite_form_jsp_from_schema(root, rel, safe_schema):
            return True
        if rel_low.endswith('calendar.jsp'):
            rendered = builtin_file(f'jsp/{path.parent.name}/{path.name}', 'egovframework.app', safe_schema)
            if rendered and rendered.strip():
                path.write_text(rendered, encoding='utf-8')
                return True
    details = (issue or {}).get('details') or {}
    available_props = [str(p or '').strip() for p in (details.get('available_props') or []) if str(p or '').strip()]
    mapper_props = [str(p or '').strip() for p in (details.get('mapper_props') or []) if str(p or '').strip()]
    for prop in mapper_props:
        if prop and prop not in available_props:
            available_props.append(prop)
    vo_rel = _normalize_rel_path(details.get('vo_path') or '')
    vo_path = (Path(project_root) / vo_rel) if (project_root and vo_rel) else None
    missing_by_var = details.get('missing_props_by_var') or {}
    suggestions = details.get('suggested_replacements') or {}

    mapper_backed_missing = [prop for prop in missing_props if prop in mapper_props and prop not in _GENERATION_METADATA_PROPS]
    changed_vo = _ensure_vo_properties(vo_path, mapper_backed_missing) if vo_path else False
    if changed_vo:
        for prop in mapper_backed_missing:
            if prop not in available_props:
                available_props.append(prop)

    metadata_markers = sorted(set([prop for prop in missing_props if prop in _GENERATION_METADATA_PROPS] + list(_GENERATION_METADATA_PROPS)))
    sensitive_markers = sorted(set([prop for prop in missing_props if prop in _AUTH_SENSITIVE_PROPS] + list(_AUTH_SENSITIVE_PROPS)))
    synthetic_markers = sorted({prop for prop in missing_props if _SYNTHETIC_PLACEHOLDER_RE.match(prop or '')})
    body = _sanitize_ui_metadata_and_sensitive_refs(body, metadata_markers + sensitive_markers + synthetic_markers)

    if not missing_by_var:
        for missing_prop in missing_props:
            body = _replace_jsp_missing_property(body, 'item', missing_prop, _select_replacement_prop(missing_prop, available_props, str(suggestions.get(missing_prop) or '')))
    else:
        for var_name, props in missing_by_var.items():
            for missing_prop in props or []:
                normalized_missing = str(missing_prop or '').strip()
                if normalized_missing in _GENERATION_METADATA_PROPS or normalized_missing in _AUTH_SENSITIVE_PROPS or _SYNTHETIC_PLACEHOLDER_RE.match(normalized_missing):
                    replacement = ''
                elif normalized_missing in available_props:
                    replacement = normalized_missing
                else:
                    replacement = _select_replacement_prop(normalized_missing, available_props, str(suggestions.get(normalized_missing) or ''))
                body = _replace_jsp_missing_property(body, str(var_name or '').strip() or 'item', normalized_missing, replacement)
    if body != original:
        path.write_text(body, encoding='utf-8')
        return True
    return changed_vo


def _repair_undefined_vo_getter_usage(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    body = _read_text(path)
    original = body
    body = _remove_non_auth_forbidden_ui_fields(body)
    details = (issue or {}).get('details') or {}
    date_getter = (details.get('suggested_date_getter') or '').strip()
    status_getter = (details.get('suggested_status_getter') or '').strip()
    priority_getter = (details.get('suggested_priority_getter') or '').strip()
    id_getter = (details.get('suggested_id_getter') or '').strip()

    if '.getId()' not in body:
        return False

    if date_getter:
        body = re.sub(r'_extractDate\(\s*([A-Za-z_][A-Za-z0-9_]*)\.getId\(\)\s*\)', lambda m: f'_extractDate({m.group(1)}.{date_getter}())', body)

    if status_getter:
        status_codes = ('OPEN', 'CLOSED', 'CANCEL', 'CANCELED', 'CANCELLED', 'ACTIVE', 'INACTIVE', 'AVAILABLE', 'RESERVED', 'PENDING', 'APPROVED', 'REJECTED', 'CONFIRMED', 'DONE', 'COMPLETE')
        code_alt = '|'.join(status_codes)
        body = re.sub(r'_matchesCode\(\s*([A-Za-z_][A-Za-z0-9_]*)\.getId\(\)\s*,\s*"(' + code_alt + r')"\s*\)', lambda m: f'_matchesCode({m.group(1)}.{status_getter}(), "{m.group(2)}")', body)

    if priority_getter:
        priority_codes = ('HIGH', 'MEDIUM', 'LOW', 'URGENT', 'NORMAL')
        code_alt = '|'.join(priority_codes)
        body = re.sub(r'_matchesCode\(\s*([A-Za-z_][A-Za-z0-9_]*)\.getId\(\)\s*,\s*"(' + code_alt + r')"\s*\)', lambda m: f'_matchesCode({m.group(1)}.{priority_getter}(), "{m.group(2)}")', body)
    else:
        body = re.sub(r'model\.addAttribute\(\s*"highPriorityCount"\s*,\s*[^;]*?\.filter\(\s*[A-Za-z_][A-Za-z0-9_]*\s*->\s*_matchesCode\(\s*[A-Za-z_][A-Za-z0-9_]*\.getId\(\)\s*,\s*"HIGH"\s*\)\s*\)\.count\(\)\s*\);', 'model.addAttribute("highPriorityCount", 0L);', body)

    if id_getter:
        body = re.sub(r'([A-Za-z_][A-Za-z0-9_]*)\.getId\(\)', lambda m: f'{m.group(1)}.{id_getter}()', body)

    if body != original:
        path.write_text(body, encoding='utf-8')
        return True
    return False





def _camel_prop_from_column(name: str) -> str:
    parts = [p for p in re.split(r'[^A-Za-z0-9]+', str(name or '').strip()) if p]
    if not parts:
        return ''
    head = parts[0].lower()
    tail_parts: List[str] = []
    for token in parts[1:]:
        piece = str(token or '').strip()
        if not piece:
            continue
        if piece.isdigit():
            tail_parts.append('_' + piece)
        else:
            tail_parts.append(piece[:1].upper() + piece[1:].lower())
    return head + ''.join(tail_parts)


def _java_type_for_column(column: str) -> str:
    return 'String'


def _render_vo_body_from_columns(package_name: str, class_name: str, columns: List[str]) -> str:
    props = []
    seen = set()
    for col in columns or []:
        prop = _camel_prop_from_column(col)
        if not prop or prop in seen:
            continue
        seen.add(prop)
        props.append((prop, _java_type_for_column(col)))
    lines: List[str] = []
    lines.append(f'package {package_name};')
    lines.append('')
    lines.append(f'public class {class_name} {{')
    lines.append('    private static final long serialVersionUID = 1L;')
    lines.append('')
    for prop, type_name in props:
        lines.append(f'    private {type_name} {prop};')
    if props:
        lines.append('')
    for idx, (prop, type_name) in enumerate(props):
        cap = prop[:1].upper() + prop[1:]
        lines.append(f'    public {type_name} get{cap}() {{')
        lines.append(f'        return {prop};')
        lines.append('    }')
        lines.append('')
        lines.append(f'    public void set{cap}({type_name} {prop}) {{')
        lines.append(f'        this.{prop} = {prop};')
        lines.append('    }')
        if idx != len(props) - 1:
            lines.append('')
    lines.append('}')
    return '\n'.join(lines) + '\n'


def _repair_mapper_vo_column_mismatch(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    details = (issue or {}).get('details') or {}
    vo_rel = _normalize_rel_path(details.get('vo_path') or '')
    columns = [str(c or '').strip().lower() for c in (details.get('mapper_columns') or []) if str(c or '').strip()]
    if not project_root or not vo_rel or not columns:
        return False
    vo_path = Path(project_root) / vo_rel
    if not vo_path.exists():
        return False
    original = _read_text(vo_path)
    pkg_match = re.search(r'package\s+([A-Za-z0-9_.]+)\s*;', original)
    package_name = pkg_match.group(1) if pkg_match else 'egovframework.app'
    rendered = _render_vo_body_from_columns(package_name, vo_path.stem, columns)
    if rendered.strip() == original.strip():
        return False
    vo_path.write_text(rendered, encoding='utf-8')
    return True




def _remove_non_auth_forbidden_ui_fields(body: str) -> str:
    result = body
    markers = list(_GENERATION_METADATA_PROPS) + list(_AUTH_SENSITIVE_PROPS)
    for marker in markers:
        marker_pat = re.escape(marker)
        result = re.sub(rf"(?is)<([A-Za-z0-9:_-]+)[^>]*(?:name|id|for|path|items|value|data-field|data-name)\s*=\s*[\"'][^\"']*{marker_pat}[^\"']*[\"'][^>]*>.*?</\1>", '', result)
        result = re.sub(rf"(?is)<(?:input|select|textarea|option|button|label|div|span|p|td|th)[^>]*(?:name|id|for|path|value|data-field|data-name)\s*=\s*[\"'][^\"']*{marker_pat}[^\"']*[\"'][^>]*/?>", '', result)
        result = re.sub(rf'(?im)^.*\b{marker_pat}\b.*(?:\n|$)', '', result)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result

def _repair_form_fields_incomplete(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    if project_root is None or not path.exists():
        return False
    root = Path(project_root)
    rel = _normalize_rel_path(str(path.relative_to(root)))
    schema = _infer_schema_for_jsp_repair(path, root)
    rel_low = rel.lower()
    if rel_low.endswith('form.jsp'):
        return _rewrite_form_jsp_from_schema(root, rel, schema)
    is_signup_like = _is_signup_route_jsp_path(path) or any(
        token in rel_low for token in ('/signup/', '/register/', '/join/', 'signupdetail.jsp', 'registerdetail.jsp', 'joindetail.jsp')
    )
    if is_signup_like:
        changed = _rewrite_signup_jsp_to_safe_routes(path, root)
        details = (issue or {}).get('details') or {}
        wanted = [
            str(x or '').strip()
            for x in ((details.get('vo_props') or []) + (details.get('missing_fields') or []))
            if str(x or '').strip() and not _is_non_auth_forbidden_field(str(x or '').strip())
        ]
        if not wanted:
            return changed
        body = _read_text(path)
        existing = set()
        for pattern in (
            r'<input[^>]+name="([^"]+)"',
            r"<input[^>]+name='([^']+)'",
            r'<select[^>]+name="([^"]+)"',
            r"<select[^>]+name='([^']+)'",
            r'<textarea[^>]+name="([^"]+)"',
            r"<textarea[^>]+name='([^']+)'",
        ):
            existing.update(m.group(1).strip() for m in re.finditer(pattern, body, re.IGNORECASE) if (m.group(1) or '').strip())
        to_add = [name for name in wanted if name not in existing]
        if not to_add:
            return changed
        hidden_block = ''.join('\n      <input type="hidden" name="{}"/>'.format(name) for name in to_add)
        updated = re.sub(r'(<form\b[^>]*>)', lambda m: m.group(1) + hidden_block, body, count=1, flags=re.IGNORECASE)
        if updated != body:
            path.write_text(updated, encoding='utf-8')
            return True
        return changed
    return False


def _repair_table_prefix_missing(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    root = Path(project_root) if project_root is not None else path.parents[3]
    details = (issue or {}).get('details') or {}
    old_table = str(details.get('table') or '').strip().lower()
    if not old_table:
        return False
    new_table = str(details.get('canonical_table') or _ensure_tb_table_name(old_table)).strip().lower()
    changed = False
    candidates = [
        root / 'src/main/resources/schema.sql',
        root / 'src/main/resources/db/schema.sql',
        root / 'src/main/resources/login-schema.sql',
        root / 'src/main/resources/db/login-schema.sql',
        root / 'src/main/resources/db/schema-mysql.sql',
    ]
    sql_patterns = [
        (re.compile(rf'(?i)(create\s+table\s+(?:if\s+not\s+exists\s+)?)`?{re.escape(old_table)}`?'), rf'\1`{new_table}`'),
        (re.compile(rf'(?i)(drop\s+table\s+(?:if\s+exists\s+)?)`?{re.escape(old_table)}`?'), rf'\1`{new_table}`'),
        (re.compile(rf'(?i)(insert\s+into\s+)`?{re.escape(old_table)}`?'), rf'\1{new_table}'),
        (re.compile(rf'(?i)(update\s+)`?{re.escape(old_table)}`?'), rf'\1{new_table}'),
        (re.compile(rf'(?i)(delete\s+from\s+)`?{re.escape(old_table)}`?'), rf'\1{new_table}'),
        (re.compile(rf'(?i)(from\s+)`?{re.escape(old_table)}`?'), rf'\1{new_table}'),
        (re.compile(rf'(?i)(join\s+)`?{re.escape(old_table)}`?'), rf'\1{new_table}'),
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        body = _read_text(candidate)
        original = body
        for pat, repl in sql_patterns:
            body = pat.sub(repl, body)
        if body != original:
            candidate.write_text(body, encoding='utf-8')
            changed = True
    res_root = root / 'src/main/resources'
    if res_root.exists():
        mapper_patterns = [
            (re.compile(rf'(?i)(insert\s+into\s+)`?{re.escape(old_table)}`?'), rf'\1{new_table}'),
            (re.compile(rf'(?i)(update\s+)`?{re.escape(old_table)}`?'), rf'\1{new_table}'),
            (re.compile(rf'(?i)(delete\s+from\s+)`?{re.escape(old_table)}`?'), rf'\1{new_table}'),
            (re.compile(rf'(?i)(from\s+)`?{re.escape(old_table)}`?'), rf'\1{new_table}'),
            (re.compile(rf'(?i)(join\s+)`?{re.escape(old_table)}`?'), rf'\1{new_table}'),
        ]
        for mapper in res_root.rglob('*Mapper.xml'):
            body = _read_text(mapper)
            original = body
            for pat, repl in mapper_patterns:
                body = pat.sub(repl, body)
            if body != original:
                mapper.write_text(body, encoding='utf-8')
                changed = True
    return changed



def _repair_missing_delete_ui(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    if project_root is not None and (path.suffix.lower() != '.jsp' or path.name.lower().endswith('controller.java')):
        changed = _repair_delete_ui(path, issue, project_root)
        if changed:
            return True
    body = _read_text(path)
    original = body
    if not body:
        return False
    low = body.lower()
    if '/delete.do' in low or 'autopj-delete-form' in low:
        return False
    details = (issue or {}).get('details') or {}
    explicit_route = str(details.get('delete_route') or ((details.get('delete_routes') or [None])[0]) or '').strip()
    domain = str(details.get('domain') or '').strip()
    if not domain:
        rel = _normalize_rel_path(str(path))
        m = re.search(r'WEB-INF/views/([^/]+)/', rel, re.IGNORECASE)
        domain = m.group(1) if m else ''
    domain = domain or 'member'
    route = explicit_route or f'/{domain}/delete.do'
    param_name = str(details.get('id_prop') or details.get('field') or details.get('id_param') or '').strip() or _infer_id_param_name_from_domain(domain)
    hidden_name = param_name or 'id'
    hidden_value = '${item.' + hidden_name + '}' if '${item.' in body else '${' + hidden_name + '}'
    form_html = (
        f"<form method=\"post\" action=\"<c:url value='{route}' />\" class=\"autopj-delete-form\" style=\"display:inline;\">"
        f"<input type=\"hidden\" name=\"{hidden_name}\" value=\"{hidden_value}\" />"
        "<button type=\"submit\">삭제</button>"
        "</form>"
    )
    if '</td>' in body:
        body = body.replace('</td>', form_html + '</td>', 1)
    elif '</tr>' in body:
        body = body.replace('</tr>', '<td>' + form_html + '</td></tr>', 1)
    elif '</table>' in body:
        body = body.replace('</table>', form_html + '\n</table>', 1)
    else:
        body = body.rstrip() + '\n' + form_html + '\n'
    if body != original:
        path.write_text(body, encoding='utf-8')
        return True
    return False

def _search_field_is_temporal(name: str) -> bool:
    low = str(name or '').strip().lower()
    return bool(low) and ('datetime' in low or low.endswith('date') or low.endswith('dt') or 'date' in low)


def _search_field_is_covered(name: str, existing: set[str]) -> bool:
    base = str(name or '').strip()
    if not base:
        return True
    existing_low = {str(item or '').strip().lower() for item in (existing or set()) if str(item or '').strip()}
    if base.lower() in existing_low:
        return True
    if _search_field_is_temporal(base):
        for start, end in (
            (f'{base}From'.lower(), f'{base}To'.lower()),
            (f'{base}Start'.lower(), f'{base}End'.lower()),
            (f'{base}Begin'.lower(), f'{base}Finish'.lower()),
        ):
            if start in existing_low and end in existing_low:
                return True
    return False


def _render_search_field_markup(name: str) -> str:
    low = str(name or '').strip().lower()
    label = name[:1].upper() + name[1:]
    if low.endswith('yn'):
        control = f'<select name="{name}"><option value="">전체</option><option value="Y">Y</option><option value="N">N</option></select>'
        return f'<label>{label}</label>{control}'
    if _search_field_is_temporal(name):
        return (
            f'<label>{label} From</label><input type="date" name="{name}From" />'
            f'<label>{label} To</label><input type="date" name="{name}To" />'
        )
    control = f'<input type="text" name="{name}" />'
    return f'<label>{label}</label>{control}'


def _repair_search_fields_incomplete(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    body = _read_text(path)
    original = body
    body = _remove_non_auth_forbidden_ui_fields(body)
    details = (issue or {}).get('details') or {}
    missing = [str(x or '').strip() for x in (details.get('missing_fields') or []) if str(x or '').strip() and not _is_non_auth_forbidden_field(str(x or '').strip())]
    if not missing:
        return False

    def _collect_names(src: str) -> set[str]:
        found: set[str] = set()
        for pattern in (
            r'<input[^>]+name="([^"]+)"',
            r"<input[^>]+name='([^']+)'",
            r'<select[^>]+name="([^"]+)"',
            r"<select[^>]+name='([^']+)'",
            r'<textarea[^>]+name="([^"]+)"',
            r"<textarea[^>]+name='([^']+)'",
        ):
            found.update(m.group(1).strip() for m in re.finditer(pattern, src, re.IGNORECASE) if (m.group(1) or '').strip())
        return found

    existing = _collect_names(body)
    to_add = [name for name in missing if not _search_field_is_covered(name, existing) and not _is_non_auth_forbidden_field(name)]
    if not to_add:
        return False

    chunks: List[str] = [_render_search_field_markup(name) for name in to_add]
    block = '\n  <div class="autopj-search-fields">\n    ' + '\n    '.join(chunks) + '\n  </div>\n'

    def _clean_form(match: re.Match[str]) -> str:
        form_text = match.group(0)
        open_tag = match.group(1) or ''
        inner = match.group(2) or ''
        close_tag = match.group(3) or ''
        if 'autopj-search-fields' not in inner.lower():
            return form_text
        method_match = re.search(r'\bmethod\s*=\s*["\']([^"\']+)["\']', open_tag, re.IGNORECASE)
        method = (method_match.group(1) if method_match else '').strip().lower()
        id_match = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', open_tag, re.IGNORECASE)
        form_id = (id_match.group(1) if id_match else '').strip().lower()
        if method == 'get' or form_id == 'searchform':
            return form_text
        cleaned_inner = re.sub(r'(?is)<div[^>]*class=["\'][^"\']*autopj-search-fields[^"\']*["\'][^>]*>.*?</div>', '', inner)
        return open_tag + cleaned_inner + close_tag

    body = re.sub(r'(?is)(<form\b[^>]*>)(.*?)(</form>)', _clean_form, body)

    search_form_re = re.compile(r'(?is)<form\b[^>]*id\s*=\s*["\']searchform["\'][^>]*>.*?</form>')
    existing_search = search_form_re.search(body)
    if existing_search:
        search_form = existing_search.group(0)
        if 'autopj-search-fields' in search_form.lower():
            search_form = re.sub(r'(?is)<div[^>]*class=["\'][^"\']*autopj-search-fields[^"\']*["\'][^>]*>.*?</div>', block.strip(), search_form, count=1)
        else:
            search_form = re.sub(r'(?is)</form>', block + '  </form>', search_form, count=1)
        body = body[:existing_search.start()] + search_form + body[existing_search.end():]
    else:
        search_form = '<form id="searchForm" class="searchForm autopj-search-form" method="get">' + block + '</form>\n'
        lower = body.lower()
        insert_at = -1
        choose_idx = lower.find('<c:choose')
        table_idx = lower.find('<table')
        if choose_idx != -1 and table_idx != -1:
            insert_at = min(choose_idx, table_idx)
        elif choose_idx != -1:
            insert_at = choose_idx
        elif table_idx != -1:
            insert_at = table_idx
        elif '</section>' in lower:
            insert_at = lower.find('</section>')
        elif '</body>' in lower:
            insert_at = lower.rfind('</body>')
        if insert_at >= 0:
            body = body[:insert_at] + search_form + body[insert_at:]
        else:
            body = body.rstrip() + '\n' + search_form

    if body != original:
        path.write_text(body, encoding='utf-8')
        return True
    return False


def _ensure_jquery_include(body: str) -> str:
    low = (body or '').lower()
    if 'jquery' in low and ('<script' in low or 'src=' in low):
        return body
    include = '<script src="${pageContext.request.contextPath}/js/jquery.min.js"></script>'
    lower = body.lower()
    if '</body>' in lower:
        idx = lower.rfind('</body>')
        return body[:idx] + include + "\n" + body[idx:]
    return body.rstrip() + "\n" + include + "\n"

def _ensure_fn_taglib(body: str) -> str:
    if 'uri="http://java.sun.com/jsp/jstl/functions"' in body or "uri='http://java.sun.com/jsp/jstl/functions'" in body:
        return body
    lines = body.splitlines()
    insert_at = 1 if lines and lines[0].lstrip().startswith('<%@ page') else 0
    lines.insert(insert_at, '<%@ taglib prefix="fn" uri="http://java.sun.com/jsp/jstl/functions"%>')
    return "\n".join(lines)


_JAVA_KEYWORDS = {"abstract","assert","boolean","break","byte","case","catch","char","class","const","continue","default","do","double","else","enum","extends","final","finally","float","for","goto","if","implements","import","instanceof","int","interface","long","native","new","package","private","protected","public","return","short","static","strictfp","super","switch","synchronized","this","throw","throws","transient","try","void","volatile","while","true","false","null","record","sealed","permits","var","yield"}

def _sanitize_package_segment(value: str) -> str:
    token = re.sub(r'[^a-zA-Z0-9_]+', '', str(value or '').strip().lower())
    token = re.sub(r'^[^a-zA-Z_]+', '', token)
    return token or 'app'


def _expected_project_base_root(project_root: Path, cfg: Any | None = None) -> str:
    project_name = ''
    if cfg is not None:
        project_name = str(getattr(cfg, 'project_name', '') or '').strip()
    if not project_name:
        project_name = Path(project_root).name
    return f"egovframework.{_sanitize_package_segment(project_name)}"


def _observed_project_roots(project_root: Path) -> List[str]:
    roots: List[str] = []
    seen = set()
    java_root = Path(project_root) / 'src/main/java'
    if java_root.exists():
        for java_file in java_root.rglob('*.java'):
            body = _read_text(java_file)
            match = re.search(r'package\s+([A-Za-z0-9_.]+)\s*;', body)
            if not match:
                continue
            pkg = (match.group(1) or '').strip()
            parts = [p for p in pkg.split('.') if p]
            if len(parts) >= 2 and parts[0] == 'egovframework':
                root_pkg = '.'.join(parts[:2])
                if root_pkg not in seen:
                    seen.add(root_pkg)
                    roots.append(root_pkg)
    return roots


def _replace_project_root_tokens(body: str, old_root: str, new_root: str) -> str:
    if not body or old_root == new_root:
        return body
    body = body.replace(old_root + '.', new_root + '.')
    body = body.replace(old_root + '"', new_root + '"')
    body = body.replace(old_root + "'", new_root + "'")
    body = body.replace(old_root.replace('.', '/'), new_root.replace('.', '/'))
    return body


def normalize_project_package_roots(project_root: Path, cfg: Any | None = None) -> List[str]:
    root = Path(project_root)
    expected_root = _expected_project_base_root(root, cfg)
    observed = [item for item in _observed_project_roots(root) if item != expected_root]
    if not observed:
        return []
    changed: List[str] = []
    text_targets = []
    for pattern in ('*.java', '*.xml', '*.jsp', '*.properties', '*.yml', '*.yaml'):
        text_targets.extend(root.rglob(pattern))
    seen_paths = set()
    for path in text_targets:
        if not path.is_file() or path in seen_paths or '.autopj_debug' in path.parts:
            continue
        seen_paths.add(path)
        try:
            body = _read_text(path)
        except Exception:
            continue
        original = body
        for old_root in observed:
            body = _replace_project_root_tokens(body, old_root, expected_root)
        if body != original:
            path.write_text(body, encoding='utf-8')
            try:
                changed.append(str(path.relative_to(root)).replace('\\', '/'))
            except Exception:
                pass
    java_root = root / 'src/main/java'
    if java_root.exists():
        for java_file in list(java_root.rglob('*.java')):
            body = _read_text(java_file)
            match = re.search(r'package\s+([A-Za-z0-9_.]+)\s*;', body)
            if not match:
                continue
            pkg = (match.group(1) or '').strip()
            new_rel = Path('src/main/java') / Path(*pkg.split('.')) / java_file.name
            new_abs = root / new_rel
            if new_abs == java_file:
                continue
            new_abs.parent.mkdir(parents=True, exist_ok=True)
            new_abs.write_text(body, encoding='utf-8')
            try:
                java_file.unlink()
            except Exception:
                pass
            rel = str(new_rel).replace('\\', '/')
            if rel not in changed:
                changed.append(rel)
    return changed


def _safe_schedule_schema_for_domain(project_root: Path, domain: str, entity_hint: str = ""):
    root = Path(project_root)
    entity = (entity_hint or domain or "Schedule").strip()
    entity = entity[:1].upper() + entity[1:] if entity else "Schedule"
    ops = []
    java_root = root / 'src/main/java'
    resources_root = root / 'src/main/resources'
    patterns = {entity, domain[:1].upper() + domain[1:] if domain else entity}
    for pattern in patterns:
        if not pattern:
            continue
        for candidate in list(java_root.rglob(f'{pattern}*.java')) + list(resources_root.rglob(f'{pattern}*.xml')):
            ops.append({'path': str(candidate.relative_to(root)).replace('\\', '/'), 'content': _read_text(candidate)})
    for candidate in resources_root.rglob('*.sql'):
        ops.append({'path': str(candidate.relative_to(root)).replace('\\', '/'), 'content': _read_text(candidate)})
    try:
        base_schema = infer_schema_from_file_ops(ops, entity=entity) if ops else schema_for(entity)
        base_fields = list(getattr(base_schema, 'fields', []) or [])
        if base_fields:
            return schema_for(entity, inferred_fields=base_fields, table=getattr(base_schema, 'table', None), feature_kind=FEATURE_KIND_SCHEDULE, strict_fields=True)
        return schema_for(entity, feature_kind=FEATURE_KIND_SCHEDULE)
    except Exception:
        return schema_for(entity, feature_kind=FEATURE_KIND_SCHEDULE)


def _infer_base_package_for_controller(path: Path, schema: Any) -> str:
    body = _read_text(path) if path.exists() else ''
    match = re.search(r'package\s+([A-Za-z0-9_.]+)\s*;', body)
    if not match:
        return 'egovframework.app'
    pkg = (match.group(1) or '').strip()
    if pkg.endswith('.web'):
        pkg = pkg[:-4]
    entity_var = str(getattr(schema, 'entity_var', '') or '').strip()
    if entity_var and pkg.endswith(f'.{entity_var}'):
        pkg = pkg[:-(len(entity_var) + 1)]
    return pkg or 'egovframework.app'


def _repair_calendar_ssr_missing(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    if project_root is None:
        return False
    details = (issue or {}).get('details') or {}
    domain = (details.get('domain') or path.parent.name or 'schedule').strip()
    entity = domain[:1].upper() + domain[1:] if domain else 'Schedule'
    schema = _safe_schedule_schema_for_domain(Path(project_root), domain, entity)
    logical = f'jsp/{domain}/{domain}Calendar.jsp'
    body = builtin_file(logical, 'egovframework.app', schema)
    if not body:
        return False
    original = _read_text(path)
    if body != original:
        path.write_text(body, encoding='utf-8')
        return True
    return False


def _repair_calendar_data_contract(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    original = _read_text(path)
    body = _inject_calendar_model_aliases(original)
    if body != original:
        path.write_text(body, encoding='utf-8')
        return True
    if project_root is None:
        return False
    details = (issue or {}).get('details') or {}
    domain = (details.get('domain') or '').strip()
    entity_match = re.match(r'([A-Za-z0-9_]+)Controller$', path.stem)
    entity = entity_match.group(1) if entity_match else (domain[:1].upper() + domain[1:] if domain else 'Schedule')
    schema = _safe_schedule_schema_for_domain(Path(project_root), domain, entity)
    base_package = _infer_base_package_for_controller(path, schema)
    logical = f'java/controller/{entity}Controller.java'
    body = builtin_file(logical, base_package, schema)
    if not body:
        return False
    body = _inject_calendar_model_aliases(body)
    if body != original:
        path.write_text(body, encoding='utf-8')
        return True
    return False


def _repair_jsp_dependency_missing(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    details = (issue or {}).get('details') or {}
    kind = (details.get('kind') or '').strip()
    body = _read_text(path)
    original = body
    body = _remove_non_auth_forbidden_ui_fields(body)
    if kind == 'fn_taglib':
        body = _ensure_fn_taglib(body)
        if body != original:
            path.write_text(body, encoding='utf-8')
            return True
        return False
    if kind == 'jquery':
        body = _ensure_jquery_include(body)
        if body != original:
            path.write_text(body, encoding='utf-8')
            return True
        return False
    if path.name.endswith('Calendar.jsp') and project_root is not None:
        domain = path.parent.name
        entity = domain[:1].upper() + domain[1:] if domain else 'Schedule'
        ops = []
        root = Path(project_root)
        for candidate in list((root / 'src/main/java').rglob(f'{entity}*.java')) + list((root / 'src/main/resources').rglob(f'{entity}*.xml')) + list((root / 'src/main/resources').rglob('*.sql')):
            ops.append({'path': str(candidate.relative_to(root)).replace('\\', '/'), 'content': _read_text(candidate)})
        try:
            base_schema = infer_schema_from_file_ops(ops, entity=entity) if ops else schema_for(entity)
            safe_schema = schema_for(entity, inferred_fields=list(getattr(base_schema, 'fields', []) or []), table=getattr(base_schema, 'table', None), feature_kind=FEATURE_KIND_SCHEDULE)
        except Exception:
            safe_schema = schema_for(entity, feature_kind=FEATURE_KIND_SCHEDULE)
        logical = f'jsp/{domain}/{domain}Calendar.jsp' if domain else 'jsp/schedule/scheduleCalendar.jsp'
        body = builtin_file(logical, '.'.join(path.parts[path.parts.index('java')+1:-1]) if 'java' in path.parts else 'egovframework.app', safe_schema) or body
        if body != original:
            path.write_text(body, encoding='utf-8')
            return True
    return False


def _controller_domain_from_path(path: Path) -> str:
    rel = _normalize_rel_path(str(path))
    m = re.search(r'/([A-Za-z0-9_]+)/web/[^/]+Controller\.java$', rel)
    if m:
        return m.group(1).strip()
    stem = path.stem[:-10] if path.stem.endswith('Controller') else path.stem
    return stem[:1].lower() + stem[1:] if stem else ''





def _membership_request_mapping_aliases(domain: str) -> List[str]:
    normalized = str(domain or '').strip().strip('/')
    if not normalized:
        return ['/member']
    aliases: List[str] = []
    for candidate in (
        normalized,
        _logical_domain_name(normalized),
        _controller_domain_from_path(Path(f'{normalized}Controller.java')),
    ):
        cand = str(candidate or '').strip().strip('/')
        if not cand:
            continue
        if not cand.startswith('/'):
            cand = '/' + cand
        if cand not in aliases:
            aliases.append(cand)
    tokens = _split_domain_tokens(normalized)
    if tokens and set(tokens) == {'admin', 'member'}:
        for cand in ('/adminMember', '/memberAdmin', '/tbMemberAdmin', '/tbmemberadmin'):
            if cand not in aliases:
                aliases.append(cand)
    if tokens and set(tokens) == {'member'}:
        for cand in ('/member', '/tbMember', '/tbmember'):
            if cand not in aliases:
                aliases.append(cand)
    if tokens and set(tokens) == {'member', 'auth'}:
        for cand in ('/memberAuth', '/tbMemberAuth', '/tbmemberauth'):
            if cand not in aliases:
                aliases.append(cand)
    return aliases



def _infer_project_root_from_path(path: Path) -> Path | None:
    current = path.resolve()
    for parent in [current.parent, *current.parents]:
        if (parent / "src/main/java").exists() or (parent / "src/main/webapp").exists():
            return parent
    return None


def _infer_route_identity_param_from_existing_artifacts(path: Path, domain: str, fallback: str) -> str:
    domain = str(domain or '').strip()
    fallback = str(fallback or 'id').strip() or 'id'
    candidates: list[str] = []

    controller_body = _read_text(path)
    for m in re.finditer(r'@RequestParam\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']', controller_body):
        name = (m.group(1) or '').strip()
        if name and name.lower().endswith('id'):
            candidates.append(name)

    root = _infer_project_root_from_path(path)
    if root is not None and domain:
        jsp_dir = root / "src/main/webapp/WEB-INF/views" / domain
        if jsp_dir.exists():
            for jsp in jsp_dir.glob("*.jsp"):
                body = _read_text(jsp)
                for pattern in (
                    r'[?&]([A-Za-z][A-Za-z0-9_]*Id)=',
                    r'<input[^>]+name=["\']([A-Za-z][A-Za-z0-9_]*Id)["\']',
                    r'<form:[A-Za-z]+[^>]+path=["\']([A-Za-z][A-Za-z0-9_]*Id)["\']',
                ):
                    for m in re.finditer(pattern, body, re.IGNORECASE):
                        candidates.append((m.group(1) or '').strip())

    preferred_prefix = re.sub(r'[^A-Za-z0-9]', '', domain)
    if preferred_prefix:
        preferred = preferred_prefix[:1].lower() + preferred_prefix[1:] + 'Id'
        for name in candidates:
            if name == preferred:
                return name
    for name in candidates:
        if name and name.lower() != 'id':
            return name
    return fallback

def _rewrite_membership_controller_to_safe_routes(path: Path, domain: str) -> bool:
    body = _read_text(path)
    package_match = re.search(r'^\s*package\s+([A-Za-z0-9_.]+)\s*;', body, flags=re.MULTILINE)
    package_decl = package_match.group(1) if package_match else ''
    class_name = path.stem or f"{domain[:1].upper() + domain[1:]}Controller"
    normalized_domain = _logical_domain_name(domain[:1].lower() + domain[1:] if domain else 'member')
    view_base = f'{normalized_domain}/{normalized_domain}'
    form_view = f'{view_base}Form'
    list_view = f'{view_base}List'
    detail_view = f'{view_base}Detail'
    normalized_lower = normalized_domain.lower()
    if 'member' in normalized_lower or normalized_lower == 'admin':
        id_param = 'memberId'
    elif normalized_lower == 'user':
        id_param = 'userId'
    elif normalized_lower == 'account':
        id_param = 'accountId'
    else:
        id_param = 'id'
    id_param = _infer_route_identity_param_from_existing_artifacts(path, normalized_domain, id_param)
    request_aliases = _membership_request_mapping_aliases(normalized_domain)
    request_mapping_decl = f'@RequestMapping("{request_aliases[0]}")' if len(request_aliases) == 1 else '@RequestMapping({' + ', '.join(f'"{item}"' for item in request_aliases) + '})'
    lines: list[str] = []
    if package_decl:
        lines.append(f"package {package_decl};")
        lines.append('')
    imports = [
        'org.springframework.stereotype.Controller;',
        'org.springframework.ui.Model;',
        'org.springframework.web.bind.annotation.GetMapping;',
        'org.springframework.web.bind.annotation.PostMapping;',
        'org.springframework.web.bind.annotation.RequestMapping;',
        'org.springframework.web.bind.annotation.RequestParam;',
        'org.springframework.web.bind.annotation.ResponseBody;',
        'java.util.LinkedHashMap;',
        'java.util.Map;',
    ]
    lines.extend([f'import {item}' if not item.startswith('import ') else item for item in imports])
    lines.append('')
    lines.append('@Controller')
    lines.append(request_mapping_decl)
    lines.append('// AUTOPJ_SAFE_VIEW_CONTROLLER')
    lines.append(f'public class {class_name} {{')
    lines.append('')
    lines.append('    @GetMapping({"/register.do", "/signup.do", "/form.do"})')
    lines.append('    public String registerForm(Model model) throws Exception {')
    lines.append(f'        return "{form_view}";')
    lines.append('    }')
    lines.append('')
    lines.append('    @GetMapping({"/detail.do", "/view.do"})')
    lines.append(f'    public String detail(@RequestParam(value = "{id_param}", required = false) String {id_param}, Model model) throws Exception {{')
    lines.append(f'        return "{detail_view}";')
    lines.append('    }')
    lines.append('')
    lines.append('    @GetMapping("/checkLoginId.do")')
    lines.append('    @ResponseBody')
    lines.append('    public Map<String, Object> checkLoginId(@RequestParam(value = "loginId", required = false) String loginId) throws Exception {')
    lines.append('        Map<String, Object> result = new LinkedHashMap<>();')
    lines.append('        result.put("available", Boolean.TRUE);')
    lines.append('        result.put("loginId", loginId == null ? "" : loginId);')
    lines.append('        result.put("message", "사용 가능한 아이디입니다.");')
    lines.append('        return result;')
    lines.append('    }')
    lines.append('')
    lines.append('    @PostMapping({"/actionRegister.do", "/save.do"})')
    lines.append('    public String actionRegister(Model model) throws Exception {')
    lines.append(f'        return "redirect:/{normalized_domain}/list.do";')
    lines.append('    }')
    lines.append('')
    lines.append('    @PostMapping("/delete.do")')
    lines.append(f'    public String delete(@RequestParam(value = "{id_param}", required = false) String {id_param}) throws Exception {{')
    lines.append(f'        return "redirect:/{normalized_domain}/list.do";')
    lines.append('    }')
    lines.append('')
    if 'admin' in normalized_domain.lower():
        lines.append('    @GetMapping({"/list.do", "/approval/list.do", "/admin/list.do"})')
    else:
        lines.append('    @GetMapping("/list.do")')
    lines.append('    public String memberList(Model model) throws Exception {')
    lines.append(f'        return "{list_view}";')
    lines.append('    }')
    lines.append('}')
    new_body = "\n".join(lines) + "\n"
    if new_body != body:
        path.write_text(new_body, encoding='utf-8')
        return True
    return False



def _rewrite_signup_controller_to_minimal_routes(path: Path, domain: str) -> bool:
    body = _read_text(path)
    package_match = re.search(r'^\s*package\s+([A-Za-z0-9_.]+)\s*;', body, flags=re.MULTILINE)
    package_decl = package_match.group(1) if package_match else ''
    class_name = path.stem or f"{domain[:1].upper() + domain[1:]}Controller"
    entity_name = class_name[:-10] if class_name.endswith('Controller') else (domain[:1].upper() + domain[1:])
    vo_package = ''
    if package_decl:
        base_pkg = package_decl.rsplit('.', 1)[0]
        vo_package = f"{base_pkg}.service.vo.{entity_name}VO"
    view_base = f"{domain}/{domain}"
    lines = []
    if package_decl:
        lines.append(f"package {package_decl};")
        lines.append('')
    imports = [
        'org.springframework.stereotype.Controller;',
        'org.springframework.ui.Model;',
        'org.springframework.web.bind.annotation.GetMapping;',
        'org.springframework.web.bind.annotation.PostMapping;',
        'org.springframework.web.bind.annotation.RequestMapping;',
    ]
    if vo_package:
        imports.append(f'import {vo_package};')
    lines.extend([f'import {item}' if not item.startswith('import ') else item for item in imports])
    lines.append('')
    lines.append('@Controller')
    lines.append(f'@RequestMapping("/{domain}")')
    lines.append(f'public class {class_name} {{')
    lines.append('')
    if vo_package:
        lines.append('    @GetMapping({"/form.do", "/signup.do", "/register.do"})')
        lines.append(f'    public String signupForm({entity_name}VO vo, Model model) throws Exception {{')
        lines.append('        if (model != null) {')
        lines.append(f'            model.addAttribute("item", vo == null ? new {entity_name}VO() : vo);')
        lines.append('        }')
        lines.append(f'        return "{view_base}Form";')
        lines.append('    }')
        lines.append('')
        lines.append('    @PostMapping("/save.do")')
        lines.append(f'    public String saveSignup({entity_name}VO vo, Model model) throws Exception {{')
        lines.append('        if (model != null) {')
        lines.append('            model.addAttribute("item", vo);')
        lines.append('        }')
        lines.append('        return "redirect:/' + domain + '/form.do";')
        lines.append('    }')
    else:
        lines.append('    @GetMapping({"/form.do", "/signup.do", "/register.do"})')
        lines.append('    public String signupForm(Model model) throws Exception {')
        lines.append(f'        return "{view_base}Form";')
        lines.append('    }')
        lines.append('')
        lines.append('    @PostMapping("/save.do")')
        lines.append('    public String saveSignup(Model model) throws Exception {')
        lines.append('        return "redirect:/' + domain + '/form.do";')
        lines.append('    }')
    lines.append('')
    lines.append('    @GetMapping("/list.do")')
    lines.append('    public String signupList(Model model) throws Exception {')
    lines.append(f'        return "{view_base}List";')
    lines.append('    }')
    lines.append('}')
    new_body = "\n".join(lines) + "\n"
    if new_body != body:
        path.write_text(new_body, encoding='utf-8')
        return True
    return False

def _repair_ambiguous_request_mapping(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    body = _read_text(path)
    details = (issue or {}).get('details') or {}
    route = str(details.get('route') or '').strip()
    routes = [str(item).strip() for item in (details.get('routes') or []) if str(item).strip()]
    root = Path(project_root) if project_root is not None else None
    domain = _controller_domain_from_path(path)

    def _resolve_conflicting_controller() -> Path | None:
        raw = _normalize_rel_path(str(details.get('conflicting_path') or ''))
        if not raw:
            return None
        if root is not None:
            candidate = root / raw
            if candidate.exists():
                return candidate
            name = Path(raw).name
            if name:
                matches = sorted(p for p in root.rglob(name) if p.is_file())
                if len(matches) == 1:
                    return matches[0]
                suffix = tuple(Path(raw).parts[-4:])
                for match in matches:
                    rel_parts = match.relative_to(root).parts
                    if tuple(rel_parts[-len(suffix):]) == suffix:
                        return match
        return None

    if domain == 'login':
        conflicting = _resolve_conflicting_controller()
        if conflicting is not None:
            conflicting_domain = _controller_domain_from_path(conflicting)
            if conflicting_domain and conflicting_domain != 'login':
                return _repair_ambiguous_request_mapping(conflicting, issue, project_root=root)
        return False
    if not domain:
        return False

    logical_domain = _logical_domain_name(domain)
    conflicting = _resolve_conflicting_controller()
    if root is not None and logical_domain and logical_domain != domain:
        canonical_candidates = []
        if conflicting is not None and conflicting != path:
            canonical_candidates.append(conflicting)
        preferred = _find_domain_controller(root, logical_domain)
        if preferred is not None and preferred != path:
            canonical_candidates.append(preferred)
        for candidate in canonical_candidates:
            candidate_domain = _logical_domain_name(_controller_domain_from_path(candidate))
            if candidate_domain != logical_domain:
                continue
            try:
                path.unlink(missing_ok=True)
                parent = path.parent
                while parent != root and parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
                return True
            except Exception:
                break

    def _looks_like_login_conflict(source: str) -> bool:
        squashed = re.sub(r'\s+', '', source or '').lower()
        login_tokens = (
            '@requestmapping("/login")',
            '@requestmapping(value="/login")',
            '@requestmapping(path="/login")',
            '@requestmapping("login")',
            '@requestmapping(value="login")',
            '@requestmapping(path="login")',
            '/login/actionlogin.do',
            '/login/process.do',
            '"/actionlogin.do"',
            '"/process.do"',
            "'/actionlogin.do'",
            "'/process.do'",
            'return"login/login"',
            "return'login/login'",
            'redirect:/login/actionmain.do',
            'redirect:/login/logout.do',
            'publicstringactionlogin(',
            'publicstringloginform(',
        )
        return any(token in squashed for token in login_tokens)

    conflicting_path = str(details.get('conflicting_path') or '').strip().lower()
    issue_message = str(details.get('message') or (issue or {}).get('message') or '').strip().lower()
    signup_like_domain = bool(set(_split_domain_tokens(domain)) & {'signup', 'join', 'register'})
    membership_like_domain = _is_membership_like_domain(domain)
    login_conflict = (
        route.startswith('/login/')
        or any(item.startswith('/login/') for item in routes)
        or '/login/' in conflicting_path
        or _looks_like_login_conflict(body)
        or (membership_like_domain and 'request mapping conflict' in issue_message)
        or signup_like_domain
    )
    member_like_domain = _is_membership_like_domain(domain)
    if member_like_domain and (
        login_conflict
        or 'request mapping conflict' in issue_message
        or route.startswith(f'/{domain}/')
        or any(item.startswith(f'/{domain}/') for item in routes)
    ):
        rewritten = _rewrite_membership_controller_to_safe_routes(path, domain)
        if rewritten:
            return True
    changed = False
    form_view = f'{domain}/{domain}Form'
    list_view = f'{domain}/{domain}List'

    def _swap(pattern: str, repl: str, flags: int = 0) -> None:
        nonlocal body, changed
        body2 = re.sub(pattern, repl, body, flags=flags)
        if body2 != body:
            body = body2
            changed = True

    def _rewrite_login_mapping_annotations() -> None:
        nonlocal body, changed
        annotation_re = re.compile(r'@(RequestMapping|GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping)\((.*?)\)', re.DOTALL)
        save_routes = ('/actionLogin.do', '/process.do', '/login/actionLogin.do', '/login/process.do')
        form_routes = ('/login.do', '/login/login.do')
        list_routes = ('/actionMain.do', '/login/actionMain.do', '/actionLogout.do', '/logout.do', '/login/actionLogout.do', '/login/logout.do')

        def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
            squashed = re.sub(r'\s+', '', text)
            return any(token.replace(' ', '') in squashed for token in needles)

        def _replacement(match: re.Match[str]) -> str:
            ann = match.group(1) or 'RequestMapping'
            inner = match.group(2) or ''
            if _contains_any(inner, save_routes):
                return '@PostMapping("/save.do")'
            if _contains_any(inner, form_routes):
                return '@GetMapping("/form.do")'
            if _contains_any(inner, list_routes):
                return '@GetMapping("/list.do")'
            if ann == 'RequestMapping' and _contains_any(inner, ('/login', '"/login"', "'/login'")):
                return f'@RequestMapping("/{domain}")'
            return match.group(0)

        body2 = annotation_re.sub(_replacement, body)
        if body2 != body:
            body = body2
            changed = True

    _swap(r'@RequestMapping\(\s*(?:value\s*=\s*)?["\'](/?login)["\']\s*\)', f'@RequestMapping("/{domain}")')
    _swap(r'@RequestMapping\(\s*path\s*=\s*["\'](/?login)["\']\s*\)', f'@RequestMapping(path = "/{domain}")')
    _swap(r'@RequestMapping\(\s*(?:value|path)\s*=\s*\{[^)]*["\']/login["\'][^)]*\}\s*\)', f'@RequestMapping("/{domain}")', flags=re.DOTALL)
    _swap(r'@RequestMapping\(\s*\{[^)]*["\']/login["\'][^)]*\}\s*\)', f'@RequestMapping("/{domain}")', flags=re.DOTALL)
    _rewrite_login_mapping_annotations()
    _swap(r'@PostMapping\(\s*\{\s*"(?:/login/)?actionLogin\.do"\s*,\s*"(?:/login/)?process\.do"\s*\}\s*\)', '@PostMapping("/save.do")')
    _swap(r"@PostMapping\(\s*\{\s*'(?:/login/)?actionLogin\.do'\s*,\s*'(?:/login/)?process\.do'\s*\}\s*\)", '@PostMapping("/save.do")')
    _swap(r'@PostMapping\(\s*"(?:/login/)?actionLogin\.do"\s*\)', '@PostMapping("/save.do")')
    _swap(r"@PostMapping\(\s*'(?:/login/)?actionLogin\.do'\s*\)", '@PostMapping("/save.do")')
    _swap(r'@PostMapping\(\s*"(?:/login/)?process\.do"\s*\)', '@PostMapping("/save.do")')
    _swap(r"@PostMapping\(\s*'(?:/login/)?process\.do'\s*\)", '@PostMapping("/save.do")')
    _swap(r'@GetMapping\(\s*"(?:/login/)?login\.do"\s*\)', '@GetMapping("/form.do")')
    _swap(r"@GetMapping\(\s*'(?:/login/)?login\.do'\s*\)", '@GetMapping("/form.do")')
    _swap(r'@GetMapping\(\s*"(?:/login/)?actionMain\.do"\s*\)', '@GetMapping("/list.do")')
    _swap(r"@GetMapping\(\s*'(?:/login/)?actionMain\.do'\s*\)", '@GetMapping("/list.do")')
    _swap(r'@GetMapping\(\s*\{\s*"(?:/login/)?actionLogout\.do"\s*,\s*"(?:/login/)?logout\.do"\s*\}\s*\)', '@GetMapping("/list.do")')
    _swap(r'@RequestMapping\(\s*method\s*=\s*RequestMethod\.POST\s*,\s*(?:value|path)\s*=\s*\{\s*"(?:/login/)?actionLogin\.do"\s*,\s*"(?:/login/)?process\.do"\s*\}\s*\)', '@PostMapping("/save.do")')
    _swap(r'@RequestMapping\(\s*(?:value|path)\s*=\s*\{\s*"(?:/login/)?actionLogin\.do"\s*,\s*"(?:/login/)?process\.do"\s*\}\s*,\s*method\s*=\s*RequestMethod\.POST\s*\)', '@PostMapping("/save.do")')
    _swap(r'@RequestMapping\(\s*method\s*=\s*RequestMethod\.POST\s*,\s*(?:value|path)\s*=\s*"(?:/login/)?actionLogin\.do"\s*\)', '@PostMapping("/save.do")')
    _swap(r'@RequestMapping\(\s*(?:value|path)\s*=\s*"(?:/login/)?actionLogin\.do"\s*,\s*method\s*=\s*RequestMethod\.POST\s*\)', '@PostMapping("/save.do")')
    _swap(r'@RequestMapping\(\s*method\s*=\s*RequestMethod\.POST\s*,\s*(?:value|path)\s*=\s*"(?:/login/)?process\.do"\s*\)', '@PostMapping("/save.do")')
    _swap(r'@RequestMapping\(\s*(?:value|path)\s*=\s*"(?:/login/)?process\.do"\s*,\s*method\s*=\s*RequestMethod\.POST\s*\)', '@PostMapping("/save.do")')
    _swap(r'@RequestMapping\(\s*method\s*=\s*RequestMethod\.GET\s*,\s*(?:value|path)\s*=\s*"(?:/login/)?login\.do"\s*\)', '@GetMapping("/form.do")')
    _swap(r'@RequestMapping\(\s*(?:value|path)\s*=\s*"(?:/login/)?login\.do"\s*,\s*method\s*=\s*RequestMethod\.GET\s*\)', '@GetMapping("/form.do")')
    _swap(r'@RequestMapping\(\s*method\s*=\s*RequestMethod\.GET\s*,\s*(?:value|path)\s*=\s*"(?:/login/)?actionMain\.do"\s*\)', '@GetMapping("/list.do")')
    _swap(r'@RequestMapping\(\s*(?:value|path)\s*=\s*"(?:/login/)?actionMain\.do"\s*,\s*method\s*=\s*RequestMethod\.GET\s*\)', '@GetMapping("/list.do")')
    _swap(r'public\s+String\s+actionLogin\s*\(', 'public String saveSignup(', flags=re.MULTILINE)
    _swap(r'public\s+String\s+loginForm\s*\(', 'public String signupForm(', flags=re.MULTILINE)
    _swap(r'public\s+String\s+actionMain\s*\(', 'public String signupList(', flags=re.MULTILINE)
    _swap(r'public\s+String\s+actionLogout\s*\(', 'public String signupList(', flags=re.MULTILINE)
    _swap(r'(["\'])/login/actionLogin\.do\1', '"/save.do"')
    _swap(r'(["\'])/login/process\.do\1', '"/save.do"')
    _swap(r'(["\'])/actionLogin\.do\1', '"/save.do"')
    _swap(r'(["\'])/process\.do\1', '"/save.do"')
    _swap(r'(["\'])/login/login\.do\1', '"/form.do"')
    _swap(r'(["\'])/login/actionMain\.do\1', '"/list.do"')
    _swap(r'(["\'])login/login\1', f'"{form_view}"')
    _swap(r'(["\'])login/main\1', f'"{list_view}"')

    body2 = body.replace('return "login/login";', f'return "{form_view}";')
    if body2 != body:
        body = body2
        changed = True
    body2 = body.replace("return 'login/login';", f'return "{form_view}";')
    if body2 != body:
        body = body2
        changed = True
    body2 = body.replace('return "login/main";', f'return "{list_view}";')
    if body2 != body:
        body = body2
        changed = True
    body2 = body.replace('redirect:/login/actionMain.do', f'redirect:/{domain}/list.do')
    if body2 != body:
        body = body2
        changed = True

    if login_conflict and signup_like_domain:
        class_mapping_match = re.search(
            r'@RequestMapping\((.*?)\)\s*(?=public\s+class\s+\w+)',
            body,
            flags=re.DOTALL,
        )
        if class_mapping_match and 'login' in re.sub(r'\s+', '', class_mapping_match.group(1).lower()):
            start, end = class_mapping_match.span()
            body2 = body[:start] + f'@RequestMapping("/{domain}")\n' + body[end:]
            if body2 != body:
                body = body2
                changed = True

        generic_replacements = (
            ('/login/actionLogin.do', '/save.do'),
            ('/login/process.do', '/save.do'),
            ('/actionLogin.do', '/save.do'),
            ('/process.do', '/save.do'),
            ('/login/login.do', '/form.do'),
            ('/login/actionMain.do', '/list.do'),
            ('/login/actionLogout.do', '/list.do'),
            ('/login/logout.do', '/list.do'),
            ('login/login', form_view),
            ('login/main', list_view),
            ('redirect:/login/actionMain.do', f'redirect:/{domain}/list.do'),
            ('redirect:/login/logout.do', f'redirect:/{domain}/list.do'),
            ('actionLogin(', 'saveSignup('),
            ('loginForm(', 'signupForm('),
            ('actionMain(', 'signupList('),
            ('actionLogout(', 'signupList('),
        )
        for src, dst in generic_replacements:
            body2 = body.replace(src, dst)
            if body2 != body:
                body = body2
                changed = True

    if login_conflict and signup_like_domain:
        aggressive_before = body
        # Last-resort blanket normalization for signup controllers that still retain login namespace fragments.
        body = body.replace('/login/', '/')
        body = body.replace('"/login"', f'"/{domain}"')
        body = body.replace("'/login'", f'"/{domain}"')
        body = body.replace('value = "/login"', f'value = "/{domain}"')
        body = body.replace('path = "/login"', f'path = "/{domain}"')
        body = body.replace('value="/login"', f'value="/{domain}"')
        body = body.replace('path="/login"', f'path="/{domain}"')
        body = body.replace('login/login', form_view)
        body = body.replace('login/main', list_view)
        body = body.replace('redirect:/login/actionMain.do', f'redirect:/{domain}/list.do')
        body = body.replace('redirect:/login/logout.do', f'redirect:/{domain}/list.do')
        body = body.replace('redirect:/actionMain.do', f'redirect:/{domain}/list.do')
        body = body.replace('redirect:/logout.do', f'redirect:/{domain}/list.do')
        body = body.replace('actionLogin(', 'saveSignup(')
        body = body.replace('loginForm(', 'signupForm(')
        body = body.replace('actionMain(', 'signupList(')
        body = body.replace('actionLogout(', 'signupList(')
        body = re.sub(r'@RequestMapping\(([^)]*)\)\s*(?=public\s+class\s+\w+)', f'@RequestMapping("/{domain}")\n', body, count=1, flags=re.DOTALL)
        body = re.sub(r'@PostMapping\(([^)]*actionLogin\.do[^)]*)\)', '@PostMapping("/save.do")', body, flags=re.DOTALL)
        body = re.sub(r'@PostMapping\(([^)]*process\.do[^)]*)\)', '@PostMapping("/save.do")', body, flags=re.DOTALL)
        body = re.sub(r'@GetMapping\(([^)]*login\.do[^)]*)\)', '@GetMapping("/form.do")', body, flags=re.DOTALL)
        body = re.sub(r'@GetMapping\(([^)]*actionMain\.do[^)]*)\)', '@GetMapping("/list.do")', body, flags=re.DOTALL)
        body = re.sub(r'@RequestMapping\(([^)]*actionLogin\.do[^)]*)\)', '@PostMapping("/save.do")', body, flags=re.DOTALL)
        body = re.sub(r'@RequestMapping\(([^)]*process\.do[^)]*)\)', '@PostMapping("/save.do")', body, flags=re.DOTALL)
        body = re.sub(r'@RequestMapping\(([^)]*login\.do[^)]*)\)', '@GetMapping("/form.do")', body, flags=re.DOTALL)
        body = re.sub(r'@RequestMapping\(([^)]*actionMain\.do[^)]*)\)', '@GetMapping("/list.do")', body, flags=re.DOTALL)
        if body != aggressive_before:
            changed = True

    signup_route_incomplete = login_conflict and (membership_like_domain or signup_like_domain) and (
        ('/login' in body.lower())
        or ('actionlogin' in body.lower())
        or ('loginform' in body.lower())
        or ('actionmain' in body.lower())
        or ('actionlogout' in body.lower())
        or ('@postmapping("/save.do")' not in body.lower())
        or ('@getmapping("/form.do")' not in body.lower() and '@getmapping({"/form.do"' not in body.lower())
    )
    if signup_route_incomplete:
        if _is_membership_like_domain(domain):
            rewritten = _rewrite_membership_controller_to_safe_routes(path, domain)
        else:
            rewritten = _rewrite_signup_controller_to_minimal_routes(path, domain)
        if rewritten:
            return True
    if changed:
        path.write_text(body, encoding='utf-8')
        return True
    if login_conflict and membership_like_domain:
        if _is_membership_like_domain(domain):
            return _rewrite_membership_controller_to_safe_routes(path, domain)
        return _rewrite_signup_controller_to_minimal_routes(path, domain)
    if membership_like_domain and 'request mapping conflict' in issue_message:
        if _is_membership_like_domain(domain):
            return _rewrite_membership_controller_to_safe_routes(path, domain)
        return _rewrite_signup_controller_to_minimal_routes(path, domain)
    return changed

def _repair_mapper_namespace_mismatch(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    if project_root is None:
        return False
    changed = normalize_project_package_roots(Path(project_root))
    body = _read_text(path)
    original = body
    body = _remove_non_auth_forbidden_ui_fields(body)
    mapper_name = path.stem
    java_root = Path(project_root) / 'src/main/java'
    matches = list(java_root.rglob(f'{mapper_name}.java')) if java_root.exists() else []
    expected_ns = ''
    for mapper_java in matches:
        pkg_match = re.search(r'package\s+([A-Za-z0-9_.]+)\s*;', _read_text(mapper_java))
        if pkg_match:
            expected_ns = f"{pkg_match.group(1)}.{mapper_name}"
            break
    if expected_ns:
        body = re.sub(r'(<mapper[^>]+namespace=")([^"]+)(")', rf'\g<1>{expected_ns}\g<3>', body, count=1)
    changed_here = body != original
    if changed_here:
        path.write_text(body, encoding='utf-8')
    return bool(changed or changed_here)



def _snake_case_from_prop(name: str) -> str:
    prop = str(name or '').strip()
    if not prop:
        return ''
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', prop)
    s2 = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1)
    return s2.replace('__', '_').lower()




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
    domain = stem[:1].lower() + stem[1:] if stem else ''
    return [f'/{domain}'] if domain else []


def _controller_domain_and_prefix(body: str, controller: Path) -> Dict[str, str]:
    aliases = _controller_request_mapping_aliases(body, controller)
    prefix = aliases[0] if aliases else ""
    domain = prefix.strip('/').split('/')[-1] if prefix.strip('/') else ''
    if not domain:
        stem = controller.stem[:-10] if controller.stem.endswith('Controller') else controller.stem
        domain = stem[:1].lower() + stem[1:] if stem else ''
        prefix = f'/{domain}' if domain else ''
    return {'domain': domain, 'prefix': prefix}


def _discover_primary_login_route(project_root: Path) -> str:
    java_root = Path(project_root) / 'src/main/java'
    if not java_root.exists():
        return ''
    candidates: List[str] = []
    helpers: List[str] = []
    class_map_re = re.compile(r'@RequestMapping\(([^)]*)\)')
    for controller in java_root.rglob('*Controller.java'):
        body = _read_text(controller)
        class_base = ''
        class_match = class_map_re.search(body)
        if class_match:
            class_base_match = re.search(r"[\"'](/[^\"']+)[\"']", class_match.group(0))
            if class_base_match:
                class_base = class_base_match.group(1).strip()
        for ann in re.finditer(r'@(GetMapping|RequestMapping)\(([^)]*)\)', body, re.DOTALL):
            block = ann.group(0)
            route_match = re.search(r"[\"'](/[^\"']+)[\"']", block)
            if not route_match:
                continue
            route = route_match.group(1).strip()
            full_route = _combine_controller_route(class_base, route)
            low = full_route.lower()
            if not low.endswith('.do'):
                continue
            if any(token in low for token in ('integratedcallback', 'integrationguide', 'integratedlogin', 'ssologin', 'certlogin', 'jwtlogin', 'actionmain')):
                helpers.append(full_route)
                continue
            if 'login' in low:
                candidates.append(full_route)
    ordered = candidates + helpers
    return next((item for item in ordered if item), '')



def _discover_signup_route(project_root: Path) -> str:
    """Discover the primary signup/register route from controller mappings without fixed-domain hardcoding."""
    routes = sorted(_discover_controller_routes(project_root))
    if not routes:
        return ""
    preferred = (
        "/member/register.do",
        "/member/signup.do",
        "/signup/register.do",
        "/signup/signup.do",
        "/login/register.do",
        "/login/signup.do",
        "/adminMember/register.do",
        "/adminMember/signup.do",
    )
    for route in preferred:
        if route in routes:
            return route

    def _score(route: str) -> tuple[int, int, int, str]:
        low = route.lower()
        positive = 0
        if "register" in low:
            positive += 40
        if "signup" in low or "sign-up" in low:
            positive += 35
        if "join" in low:
            positive += 25
        if "member" in low or "user" in low or "account" in low:
            positive += 10
        negative = 0
        if any(token in low for token in ("check", "duplicate", "exists", "loginid", "password", "approve", "approval", "delete", "save")):
            negative += 30
        if not low.endswith(".do"):
            negative += 10
        depth_penalty = max(0, route.count("/") - 2)
        return (positive - negative, -depth_penalty, -len(route), route)

    candidates = [route for route in routes if any(token in route.lower() for token in ("register", "signup", "sign-up", "join"))]
    if not candidates:
        return ""
    candidates.sort(key=_score, reverse=True)
    best = candidates[0]
    return best if _score(best)[0] > 0 else ""


def _discover_primary_logout_route(project_root: Path) -> str:
    routes = sorted(_discover_controller_routes(project_root))
    preferred = ('/login/logout.do', '/logout.do', '/actionLogout.do', '/login/actionLogout.do')
    for route in preferred:
        if route in routes:
            return route
    for route in routes:
        low = route.lower()
        if low.endswith('.do') and 'logout' in low:
            return route
    return ''


def _discover_primary_menu_route(project_root: Path) -> str:
    routes = sorted(_discover_controller_routes(project_root))
    preferred_suffixes = ('/list.do', '/calendar.do', '/form.do', '/detail.do')

    def _route_score(route: str) -> tuple[int, int, int, int, str]:
        low = route.lower()
        parts = [part for part in route.strip('/').split('/') if part]
        plain_list = 1 if re.fullmatch(r'/[^/]+/list\.do', route) else 0
        admin_penalty = 1 if '/admin/' in low or '/approval/' in low else 0
        entry_penalty = 1 if any(token in low for token in ('/login/', '/signup/', '/register/', '/join/')) else 0
        first_tokens = _split_domain_tokens(parts[0] if parts else '')
        canonical_admin_member = 1 if first_tokens[:2] == ['admin', 'member'] else 0
        return (plain_list, canonical_admin_member, -admin_penalty, -entry_penalty, route)

    for suffix in preferred_suffixes:
        candidates = [route for route in routes if route.lower().endswith(suffix) and '/login/' not in route.lower()]
        if not candidates:
            continue
        candidates.sort(key=_route_score, reverse=True)
        return candidates[0]
    return _discover_primary_login_route(project_root) or '/'


def _ensure_common_css_partial(project_root: Path) -> bool:
    rel = 'src/main/webapp/WEB-INF/views/common/css.jsp'
    path = Path(project_root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    desired = (
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<link rel="stylesheet" href="${pageContext.request.contextPath}/css/common.css"/>\n'
    )
    existing = path.read_text(encoding='utf-8') if path.exists() else ''
    if existing != desired:
        path.write_text(desired, encoding='utf-8')
        return True
    return False

def _render_specific_auth_jsp(path: Path, project_root: Path, schema: Any) -> bool:
    basename = path.name.lower()
    virtual_rel_map = {
        'login.jsp': 'jsp/login/login.jsp',
        'main.jsp': 'jsp/login/main.jsp',
        'integrationguide.jsp': 'jsp/login/integrationGuide.jsp',
        'certlogin.jsp': 'jsp/login/certLogin.jsp',
        'jwtlogin.jsp': 'jsp/login/jwtLogin.jsp',
    }
    virtual_rel = virtual_rel_map.get(basename)
    if not virtual_rel:
        return False
    routes = _discover_controller_routes(project_root)
    fields = list(getattr(schema, 'fields', []) or [])
    normalized_schema = schema_for(
        'Login',
        inferred_fields=fields,
        table=getattr(schema, 'table', None) or 'tb_login',
        feature_kind=FEATURE_KIND_AUTH,
        unified_auth=bool(getattr(schema, 'unified_auth', False)),
        cert_login=bool(getattr(schema, 'cert_login', False)),
        jwt_login=bool(getattr(schema, 'jwt_login', False)),
    )
    rendered = builtin_file(virtual_rel, 'egovframework.app', normalized_schema)
    if rendered and rendered.strip() and rendered != _read_text(path):
        path.write_text(rendered, encoding='utf-8')
        return True
    return False

def _repair_common_layout_routes(path: Path, project_root: Path) -> bool:
    body = _read_text(path)
    original = body
    login_route = _discover_primary_login_route(project_root) or '/login/login.do'
    logout_route = _discover_primary_logout_route(project_root) or login_route
    menu_route = _discover_primary_menu_route(project_root) or '/'
    replacements = {
        '/logout': logout_route,
        '/logout.do': logout_route,
        '/menu': menu_route,
        '/menu.do': menu_route,
        '/main': menu_route,
        '/main.do': menu_route,
        '/index': menu_route,
        '/index.do': menu_route,
        '/index/list.do': menu_route,
        '/home': menu_route,
        '/home.do': menu_route,
        '/home/list.do': menu_route,
        '/main/list.do': menu_route,
    }
    for src, dst in replacements.items():
        body = body.replace(f'<c:url value="{src}"/>', f'<c:url value="{dst}"/>')
        body = body.replace(f"<c:url value='{src}'/>", f"<c:url value='{dst}'/>")
        body = body.replace(f'<c:url value="{src}" />', f'<c:url value="{dst}" />')
        body = body.replace(f"<c:url value='{src}' />", f"<c:url value='{dst}' />")
        body = body.replace(f'"{src}"', f'"{dst}"')
        body = body.replace(f"'{src}'", f"'{dst}'")
    changed = body != original
    if '/WEB-INF/views/common/css.jsp' in body:
        changed = _ensure_common_css_partial(project_root) or changed
    if body != original:
        path.write_text(body, encoding='utf-8')
    return changed


def _infer_schema_for_jsp_repair(path: Path, project_root: Path | None = None):
    root = Path(project_root) if project_root is not None else path.parents[4]
    rel = _normalize_rel_path(str(path.relative_to(root)))
    rel_low = rel.lower()
    parts = rel.split('/')
    domain = parts[-2] if len(parts) >= 2 else path.parent.name
    entity = domain[:1].upper() + domain[1:] if domain else 'Item'
    stem_low = path.stem.lower()
    compact_stem = re.sub(r'[^a-z0-9]+', '', stem_low)
    collection_like = compact_stem.endswith(('list', 'detail', 'calendar'))
    auth_like = False
    if not collection_like:
        auth_exact = {'login', 'signin', 'signup', 'register', 'join', 'auth', 'certlogin', 'jwtlogin', 'integratedlogin', 'ssologin'}
        auth_like = (
            compact_stem in auth_exact
            or any(compact_stem.endswith(token) for token in auth_exact if len(token) > 4)
            or '/login/' in rel_low
            or '/auth/' in rel_low
        )
    feature_kind = FEATURE_KIND_AUTH if auth_like else FEATURE_KIND_CRUD
    vo_candidates: List[Path] = []
    java_root = root / 'src/main/java'
    if java_root.exists():
        for candidate in java_root.rglob('*VO.java'):
            low = candidate.as_posix().lower()
            if f'/{domain.lower()}/' in low or candidate.stem.lower() == f'{domain.lower()}vo':
                vo_candidates.append(candidate)
        if not vo_candidates:
            vo_candidates.extend(list(java_root.rglob(f'{entity}VO.java')))
    fields: List[tuple[str, str, str]] = []
    if vo_candidates:
        vo_fields = _parse_vo_field_types(vo_candidates[0])
        for col, jt in vo_fields.items():
            prop = _camel_prop_from_column(col)
            if not prop:
                continue
            fields.append((prop, col, jt or _java_type_for_column(col)))
    if feature_kind == FEATURE_KIND_AUTH:
        if not fields:
            fields = [('loginId', 'login_id', 'String'), ('loginPassword', 'login_password', 'String'), ('userName', 'user_name', 'String')]
        return schema_for(entity if entity else 'Login', inferred_fields=fields, table=domain or 'login', feature_kind=FEATURE_KIND_AUTH)
    if not fields:
        fields = [('name', 'name', 'String'), ('useYn', 'use_yn', 'String'), ('regDt', 'reg_dt', 'String')]
    return schema_for(entity or 'Item', inferred_fields=fields, table=domain or _snake_case_from_prop(entity), feature_kind=FEATURE_KIND_CRUD)

def _auth_alias_kind_for_jsp_path(path: Path | str) -> str:
    raw = _normalize_rel_path(str(path)).lower()
    basename = Path(raw).name
    stem = basename.rsplit('.', 1)[0]
    compact = re.sub(r'[^a-z0-9]+', '', stem)
    suffixes = ('list', 'detail', 'form', 'calendar', 'view', 'edit')
    suffix = next((item for item in suffixes if compact.endswith(item)), '')
    base = compact[:-len(suffix)] if suffix else compact
    joined = raw.replace('/', '')
    if compact in {'signup', 'register', 'join'}:
        return 'signup'
    if suffix in ('form', 'view', 'edit', 'detail') and (any(tok in base for tok in ('signup', 'register', 'join')) or any(f'/{tok}/' in raw for tok in ('signup', 'register', 'join'))):
        return 'signup'
    if any(tok in base for tok in ('login', 'signin')) or '/login/' in raw or '/auth/' in raw or 'login' in joined or 'signin' in joined:
        return 'login'
    return ''


def _rewrite_auth_alias_collection_jsp(path: Path, project_root: Path) -> bool:
    kind = _auth_alias_kind_for_jsp_path(path)
    if not kind:
        return False
    root = Path(project_root)
    rel = _normalize_rel_path(str(path.relative_to(root)))
    schema = _infer_schema_for_jsp_repair(path, root)
    base_package = 'egovframework.app'
    if kind == 'login':
        if path.name.lower() in {'login.jsp', 'main.jsp', 'integrationguide.jsp', 'certlogin.jsp', 'jwtlogin.jsp'}:
            if _render_specific_auth_jsp(path, root, schema):
                return True
        fields = [field for field in list(getattr(schema, 'fields', []) or []) if not _is_non_auth_forbidden_field((field[0] if isinstance(field, (list, tuple)) and field else ''))]
        login_fields = list(fields)
        existing_props = {str((field[0] if isinstance(field, (list, tuple)) and field else '')).strip() for field in login_fields}
        for prop, col in (('loginId', 'login_id'), ('password', 'password'), ('loginPassword', 'login_password')):
            if prop not in existing_props:
                login_fields.append((prop, col, 'String'))
        auth_schema = schema_for('Login', inferred_fields=login_fields, table=getattr(schema, 'table', None) or 'login', feature_kind=FEATURE_KIND_AUTH)
        rendered = builtin_file('jsp/login/login.jsp', base_package, auth_schema)
        if rendered and rendered.strip() and rendered != _read_text(path):
            path.write_text(rendered, encoding='utf-8')
            return True
        return False
    if kind == 'signup':
        return _rewrite_signup_jsp_to_safe_routes(path, root)
    return False


def _discover_controller_routes(project_root: Path) -> set[str]:
    java_root = Path(project_root) / 'src/main/java'
    routes: set[str] = set()
    if not java_root.exists():
        return routes
    for controller in java_root.rglob('*Controller.java'):
        body = _read_text(controller)
        prefixes = _controller_request_mapping_aliases(body, controller)
        class_decl = re.search(r'\bclass\s+[A-Za-z0-9_]+', body)
        method_scan_body = body[class_decl.start():] if class_decl else body
        for match in re.finditer(r'@(GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\(([^)]*)\)', method_scan_body, re.DOTALL):
            ann = match.group(0) or ''
            method_routes = [
                (path_match.group(1) or '').strip()
                for path_match in re.finditer(r"[\"'](/[^\"']+)[\"']", ann)
                if (path_match.group(1) or '').strip()
            ]
            if not method_routes:
                continue
            for prefix in prefixes or ['']:
                for route in method_routes:
                    full = _combine_controller_route(prefix, route)
                    if full:
                        routes.add(full)
    return routes

def _is_signup_route_jsp_path(path: Path | str) -> bool:
    raw = _normalize_rel_path(str(path)).lower()
    if any(token in raw for token in ('signup.jsp', 'register.jsp', 'join.jsp')):
        return True
    return _auth_alias_kind_for_jsp_path(raw) == 'signup'



def _normalize_membership_route_prefixes_in_jsp(body: str, route_domain: str, include_signup_helpers: bool = False) -> str:
    domain = str(route_domain or '').strip().strip('/')
    if not domain:
        return body
    prefixes = ('member', 'tbMember', 'tbmember', 'user', 'account', 'admin', 'tbAdmin', 'tbadmin', 'adminMember', 'memberAdmin', 'memberAuth', 'tbMemberAdmin', 'tbmemberadmin', 'tbMemberAuth', 'tbmemberauth')
    suffixes = ['list.do', 'detail.do', 'form.do', 'save.do', 'delete.do']
    if include_signup_helpers:
        suffixes.extend(['actionRegister.do', 'checkLoginId.do', 'checkId.do', 'checkIdDupl.do'])
    normalized = body
    for prefix in prefixes:
        for suffix in suffixes:
            normalized = re.sub(
                rf'(?<![A-Za-z0-9_])/{re.escape(prefix)}/{re.escape(suffix)}(?=(?:\?|[^A-Za-z0-9_]|$))',
                f'/{domain}/{suffix}',
                normalized,
                flags=re.IGNORECASE,
            )
    return normalized


def _rewrite_signup_jsp_to_safe_routes(path: Path, project_root: Path) -> bool:
    rel_low = _normalize_rel_path(str(path)).lower()
    if not _is_signup_route_jsp_path(rel_low):
        return False
    domain = path.parent.name or 'member'
    routes = _discover_controller_routes(project_root)
    logical_domain = _logical_domain_name(domain) or domain
    if not any(route.lower().startswith(f'/{logical_domain.lower()}/') for route in routes):
        controller_path = _find_domain_controller(project_root, logical_domain) or _find_domain_controller(project_root, domain)
        if controller_path is not None and _rewrite_membership_controller_to_safe_routes(controller_path, logical_domain):
            routes = _discover_controller_routes(project_root)
    login_route = _discover_primary_login_route(project_root) or '/login/login.do'
    preferred_domains = [domain, 'member', 'members', 'user', 'users', 'account', 'accounts', 'signup', 'join', 'register']
    save_suffixes = ('save.do', 'actionRegister.do', 'signup.do', 'register.do', 'join.do')
    candidate_save: List[str] = []
    for dom in preferred_domains:
        dom = (dom or '').strip('/')
        if not dom:
            continue
        candidate_save.extend([f'/{dom}/{suffix}' for suffix in save_suffixes])
    def _is_adminish(route: str) -> bool:
        first = str(route or '').strip('/').split('/', 1)[0].lower()
        return 'admin' in first or first in {'approval'}

    save_route = next((route for route in candidate_save if route in routes and not route.lower().startswith('/login/') and not _is_adminish(route)), '')
    if not save_route:
        save_route = next((route for route in candidate_save if route in routes and not _is_adminish(route)), '')
    if not save_route:
        save_route = next((route for route in routes if any(route.lower().endswith('/' + suffix.lower()) for suffix in save_suffixes) and not route.lower().startswith('/login/') and not _is_adminish(route)), '')
    if not save_route:
        save_route = next((route for route in routes if any(route.lower().endswith('/' + suffix.lower()) for suffix in save_suffixes) and not _is_adminish(route)), '')
    if not save_route:
        save_route = f'/member/save.do'
    candidate_check: List[str] = []
    for dom in preferred_domains:
        dom = (dom or '').strip('/')
        if not dom:
            continue
        candidate_check.extend([f'/{dom}/checkLoginId.do', f'/{dom}/checkId.do', f'/{dom}/checkIdDupl.do'])
    check_route = next((route for route in candidate_check if route in routes and not route.lower().startswith('/login/') and not _is_adminish(route)), '')
    if not check_route:
        check_route = next((route for route in candidate_check if route in routes and not _is_adminish(route)), '')
    if not check_route:
        check_route = '/member/checkLoginId.do'

    schema = _infer_schema_for_jsp_repair(path, project_root)
    schema_fields = [field for field in list(getattr(schema, 'fields', []) or []) if isinstance(field, (list, tuple)) and field and str(field[0] or '').strip()]
    field_map = {str(field[0]).strip(): field for field in schema_fields}

    def _pick_prop(preferred: tuple[str, ...], contains: tuple[str, ...] = ()) -> str:
        for cand in preferred:
            if cand in field_map:
                return cand
        for prop in field_map:
            low = prop.lower()
            if any(token in low for token in contains):
                return prop
        return ''

    def _is_signup_forbidden_field(prop: str) -> bool:
        key = _normalize_guard_field(prop)
        return key in _NON_AUTH_GENERATION_METADATA_MARKERS

    login_id_prop = _pick_prop(('loginId', 'memberId', 'userId', 'accountId'), ('loginid', 'memberid', 'userid', 'accountid')) or 'loginId'
    password_prop = _pick_prop(('loginPassword', 'password', 'loginPwd', 'passwd', 'pwd'), ('password', 'passwd', 'pwd')) or 'loginPassword'
    name_prop = _pick_prop(('memberName', 'memberNm', 'userName', 'userNm', 'name'), ('membername', 'membernm', 'username', 'usernm', 'name'))

    button = '<button type="button" onclick="return autopjCheckLoginId();">중복 확인</button>' if check_route and login_id_prop else ''
    script = ''
    if check_route and login_id_prop:
        script_lines = [
            '<script>',
            'async function autopjCheckLoginId() {',
            f'  var field = document.getElementById("{login_id_prop}");',
            '  var loginId = (field && field.value || "").trim();',
            '  if (!loginId) { alert("아이디를 입력하세요."); return false; }',
            '  try {',
            f'    var resp = await fetch("${{pageContext.request.contextPath}}{check_route}?loginId=" + encodeURIComponent(loginId), {{ headers: {{ "X-Requested-With": "XMLHttpRequest" }} }});',
            '    var text = await resp.text();',
            '    alert(text && text.indexOf("false") >= 0 ? "이미 사용 중인 아이디입니다." : "사용 가능한 아이디입니다.");',
            '  } catch (e) {',
            '    alert("아이디 중복 확인에 실패했습니다.");',
            '  }',
            '  return false;',
            '}',
            '</script>',
        ]
        script = '\n'.join(script_lines) + '\n'

    def _field_label(prop: str) -> str:
        comments = getattr(schema, 'field_comments', {}) or {}
        field = field_map.get(prop, ('', prop, 'String'))
        comment = str(comments.get(prop) or comments.get(field[1]) or '').strip() if prop else ''
        if comment:
            return comment
        labels = {
            'loginId': '로그인 아이디', 'memberId': '회원 아이디', 'userId': '사용자 아이디', 'accountId': '계정 아이디',
            'loginPassword': '비밀번호', 'password': '비밀번호', 'memberName': '회원명', 'memberNm': '회원명',
            'userName': '사용자명', 'userNm': '사용자명', 'email': '이메일', 'phone': '전화번호', 'phoneNo': '전화번호',
            'mobile': '휴대폰번호', 'mobileNo': '휴대폰번호', 'tel': '전화번호', 'telNo': '전화번호',
            'roleCd': '권한코드', 'useYn': '사용여부',
        }
        return labels.get(prop, prop[:1].upper() + prop[1:])

    def _is_system_hidden(prop: str) -> bool:
        low = str(prop or '').strip().lower()
        return any(token in low for token in ('created', 'updated', 'modified', 'regdt', 'regdate', 'upddt', 'lastmodified', 'searchcondition', 'searchkeyword', 'pageindex', 'pagesize', 'recordcount'))

    def _input_type(prop: str, java_type: str) -> str:
        low = str(prop or '').strip().lower()
        jt = str(java_type or '').strip().lower()
        if any(token in low for token in ('password', 'passwd', 'pwd')):
            return 'password'
        if 'email' in low:
            return 'email'
        if any(token in low for token in ('phone', 'mobile', 'tel')):
            return 'tel'
        if 'datetime' in low:
            return 'datetime-local'
        if low.endswith('date') or low.endswith('dt') or 'date' in low:
            return 'date'
        if jt in {'int', 'integer', 'long', 'float', 'double', 'bigdecimal'}:
            return 'number'
        return 'text'

    visible_props: List[str] = []
    hidden_props: List[str] = []
    for prop, _col, _jt in schema_fields:
        if _is_signup_forbidden_field(prop):
            continue
        low = prop.lower()
        if low in {'searchcondition', 'searchkeyword', 'id'}:
            continue
        if _is_system_hidden(prop) or low in {'lastmodifiedby'}:
            hidden_props.append(prop)
            continue
        visible_props.append(prop)

    ordered_visible: List[str] = []
    for prop in (login_id_prop, password_prop, name_prop, 'email', 'phone', 'phoneNo', 'mobile', 'mobileNo', 'tel', 'telNo'):
        if prop and prop in visible_props and prop not in ordered_visible:
            ordered_visible.append(prop)
    for prop in visible_props:
        if prop not in ordered_visible:
            ordered_visible.append(prop)

    rendered_names: set[str] = set()
    field_chunks: List[str] = []
    for prop in ordered_visible:
        field = field_map.get(prop, (prop, prop, 'String'))
        jt = field[2] if len(field) > 2 else 'String'
        required_attr = ' required' if prop in {login_id_prop, password_prop, name_prop} else ''
        extra = f' id="{prop}"' if prop == login_id_prop else ''
        lines = [
            '        <label class="autopj-field">',
            f'          <span class="autopj-field__label">{_field_label(prop)}</span>',
            f'          <input type="{_input_type(prop, jt)}" name="{prop}"{extra} class="form-control"{required_attr} />',
        ]
        if prop == login_id_prop and button:
            lines.append(f'          {button}')
        lines.append('        </label>')
        field_chunks.append('\n'.join(lines))
        rendered_names.add(prop)

    confirm_name = f'{password_prop}Confirm'
    if password_prop:
        field_chunks.append('\n'.join([
            '        <label class="autopj-field">',
            '          <span class="autopj-field__label">비밀번호 확인</span>',
            f'          <input type="password" name="{confirm_name}" class="form-control" required autocomplete="new-password" />',
            '        </label>',
        ]))

    hidden_inputs: List[str] = []
    for prop in hidden_props:
        if prop in rendered_names or _is_signup_forbidden_field(prop):
            continue
        hidden_inputs.append(f'      <input type="hidden" name="{prop}"/>')
        rendered_names.add(prop)
    for prop, _col, _jt in schema_fields:
        if prop in rendered_names or _is_signup_forbidden_field(prop):
            continue
        hidden_inputs.append(f'      <input type="hidden" name="{prop}"/>')
        rendered_names.add(prop)

    compare_expr = f'(this.{password_prop}.value === this.{confirm_name}.value)' if password_prop else 'true'
    body_lines = [
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>',
        '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>',
        '<!DOCTYPE html>',
        '<html>',
        '<head>',
        '  <meta charset="UTF-8"/>',
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>',
        '  <title>회원가입</title>',
        '</head>',
        '<body>',
        '<%@ include file="/WEB-INF/views/common/header.jsp" %>',
        '<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>',
        '  <div class="page-card autopj-form-page">',
        '    <div class="page-header">',
        '      <div>',
        '        <h2 class="schedule-page__title">회원가입</h2>',
        '        <p class="schedule-page__desc">기존 로그인과 연동되는 회원가입 화면입니다.</p>',
        '      </div>',
        '    </div>',
        f"    <form class=\"autopj-form-card form-card\" action=\"<c:url value='{save_route}'/>\" method=\"post\" onsubmit=\"return {compare_expr};\">",
    ]
    body_lines.extend(hidden_inputs)
    body_lines.append('      <div class="autopj-form-grid">')
    body_lines.extend(field_chunks)
    body_lines.extend([
        '      </div>',
        '      <div class="autopj-form-actions">',
        '        <button type="submit">가입 완료</button>',
        f"        <a class=\"btn btn-secondary\" href=\"<c:url value='{login_route}'/>\">로그인으로 이동</a>",
        '      </div>',
        '    </form>',
        '  </div>',
    ])
    if script:
        body_lines.append(script.rstrip())
    body_lines.extend(['</body>', '</html>', ''])
    body = '\n'.join(body_lines)
    target_signup_domain = (save_route.strip('/').split('/', 1)[0] if save_route.startswith('/') and '/' in save_route.strip('/') else domain)
    body = _normalize_membership_route_prefixes_in_jsp(body, target_signup_domain, include_signup_helpers=True)
    if body != _read_text(path):
        path.write_text(body, encoding='utf-8')
        return True
    return False

def _sanitize_selectorless_style_blocks(body: str) -> str:
    if '<style' not in body.lower():
        return body

    def _fix_style(match: re.Match) -> str:
        open_tag = match.group(1)
        style_body = match.group(2)
        close_tag = match.group(3)
        if not re.search(r'(?m)^\s*(?:width|height|min-width|min-height|max-width|max-height|margin|padding|border|background|font|color)\s*:', style_body):
            return match.group(0)

        plain_style = re.sub(r'/\*.*?\*/', '', style_body, flags=re.DOTALL)
        prop_line_re = re.compile(
            r'(?m)^\s*(?:width|height|min-width|min-height|max-width|max-height|margin|padding|'
            r'border(?:-[\w-]+)?|background(?:-[\w-]+)?|font(?:-[\w-]+)?|color)\s*:\s*[^;{}]+;?\s*$'
        )
        if '{' not in plain_style and '}' not in plain_style:
            lines = [line.rstrip() for line in style_body.splitlines() if line.strip()]
            decls = [line.strip() for line in lines if prop_line_re.match(line)]
            if decls:
                indented = '\n'.join(
                    f"  {line if line.endswith(';') else line + ';'}" for line in decls
                )
                style_body_fixed = f"\nbody {{\n{indented}\n}}\n"
                return f'{open_tag}{style_body_fixed}{close_tag}'
            return ''

        fixed_lines = []
        depth = 0
        for line in style_body.splitlines():
            if depth == 0 and prop_line_re.match(line):
                continue
            fixed_lines.append(line)
            depth += line.count('{') - line.count('}')
            if depth < 0:
                depth = 0
        fixed_body = '\n'.join(fixed_lines)
        return f'{open_tag}{fixed_body}{close_tag}'

    return re.sub(r'(?is)(<style\b[^>]*>)(.*?)(</style>)', _fix_style, body)

def _repair_malformed_jsp_structure(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    if project_root is None:
        return False
    root = Path(project_root)
    rel = _normalize_rel_path(str(path.relative_to(root)))
    rel_low = rel.lower()
    if rel_low.endswith('/common/css.jsp'):
        return _ensure_common_css_partial(root)
    entry_only_domains = {'index', 'home', 'main', 'landing', 'root'}
    stem_low = path.stem.lower()
    parent_low = path.parent.name.lower()
    is_entry_view = (
        any(f'/web-inf/views/{name}/' in rel_low for name in entry_only_domains)
        or parent_low in entry_only_domains
        or stem_low in entry_only_domains
        or any(stem_low.startswith(f'{name}form') for name in entry_only_domains)
    )
    if is_entry_view:
        target_route = _discover_primary_menu_route(root) or _discover_primary_login_route(root) or '/'
        rendered = _render_entry_only_redirect_jsp(target_route)
        if rendered.strip() != _read_text(path).strip():
            path.write_text(rendered, encoding='utf-8')
            return True
    schema = _infer_schema_for_jsp_repair(path, root)
    auth_alias_kind = _auth_alias_kind_for_jsp_path(path)
    if auth_alias_kind:
        if path.name.lower() in {'login.jsp', 'main.jsp', 'integrationguide.jsp', 'certlogin.jsp', 'jwtlogin.jsp'} and _render_specific_auth_jsp(path, root, schema):
            return True
        return _rewrite_auth_alias_collection_jsp(path, root)
    if rel_low.endswith('calendar.jsp'):
        auth_calendar_tokens = {'auth', 'login', 'signup', 'join', 'register', 'member', 'admin', 'user', 'account', 'cert'}
        scan = (rel_low.replace('/', ' ') + ' ' + parent_low + ' ' + stem_low)
        if any(token in scan for token in auth_calendar_tokens):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            return True
        domain = path.parent.name
        entity = domain[:1].upper() + domain[1:] if domain else 'Schedule'
        safe_schema = _safe_schedule_schema_for_domain(root, domain, entity)
        logical = f'jsp/{domain}/{path.name}' if domain else f'jsp/schedule/{path.name}'
        rendered = builtin_file(logical, 'egovframework.app', safe_schema)
        if rendered and rendered.strip():
            discovered_routes = sorted(_discover_controller_routes(root))
            if discovered_routes:
                def _calendar_route_swap(match: re.Match) -> str:
                    route = (match.group(1) or '').strip()
                    route_only, query = (route.split('?', 1) + [''])[:2]
                    route_low = route_only.lower()
                    suffix_aliases = {
                        '/calendar.do': ('/calendar.do',),
                        '/detail.do': ('/detail.do', '/view.do'),
                        '/form.do': ('/form.do', '/edit.do', '/signup.do', '/register.do', '/join.do'),
                        '/delete.do': ('/delete.do',),
                        '/list.do': ('/list.do',),
                    }
                    for canonical, aliases in suffix_aliases.items():
                        if any(route_low.endswith(alias) for alias in aliases):
                            candidate = next((item for item in discovered_routes if item.lower().endswith(canonical)), '')
                            if not candidate and canonical == '/calendar.do':
                                candidate = next((item for item in discovered_routes if item.lower().endswith('/list.do')), '')
                            if candidate:
                                return candidate + ((('?' + query)) if query else '')
                    return route
                rendered = re.sub(r"(/[^\"'\s>]+(?:\?[^\"'\s>]*)?)", lambda m: _calendar_route_swap(m), rendered)
            if rendered != _read_text(path):
                path.write_text(rendered, encoding='utf-8')
                return True
    if (rel_low.endswith('list.jsp') or stem_low.endswith('manage')) and _rewrite_list_jsp_from_schema(root, rel, schema):
        return True
    if rel_low.endswith('form.jsp') and _rewrite_form_jsp_from_schema(root, rel, schema):
        return True
    if rel_low.endswith('detail.jsp') and _rewrite_detail_jsp_from_schema(root, rel, schema):
        return True
    if any(token in rel_low for token in ('signup.jsp', 'register.jsp', 'join.jsp')):
        if _rewrite_signup_jsp_to_safe_routes(path, root):
            return True
    if rel_low.endswith('login.jsp'):
        virtual_rel = 'jsp/' + rel.split('/WEB-INF/views/', 1)[-1] if '/WEB-INF/views/' in rel else 'jsp/' + Path(rel).name
        rendered = builtin_file(virtual_rel, 'egovframework.app', schema)
        if rendered and rendered.strip() and rendered != _read_text(path):
            path.write_text(rendered, encoding='utf-8')
            return True
    original_body = _read_text(path)
    cleaned = _cleanup_orphan_jsp_closing_tags(original_body)
    sanitized = _sanitize_selectorless_style_blocks(cleaned)
    balanced = _balance_form_tags(sanitized)
    if balanced != original_body:
        path.write_text(balanced, encoding='utf-8')
        return True
    return False



def _render_entry_only_redirect_jsp(target_route: str) -> str:
    route = target_route or '/'
    return f'''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8"/>
  <meta http-equiv="X-UA-Compatible" content="IE=edge"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>진입 전용 화면</title>
</head>
<body>
  <div style="padding:32px;font-family:Malgun Gothic, sans-serif;">
    <h2>진입 전용 화면</h2>
    <p>이 화면은 직접 CRUD 처리를 하지 않고 생성된 대표 화면으로 이동합니다.</p>
    <p><a href="<c:url value='{route}' />">이동하기</a></p>
  </div>
  <script>location.replace("${{pageContext.request.contextPath}}{route}");</script>
</body>
</html>
'''


def _is_structural_views_jsp(path: Path, project_root: Path) -> bool:
    try:
        rel_low = _normalize_rel_path(str(path.relative_to(project_root))).lower()
    except Exception:
        rel_low = _normalize_rel_path(str(path)).lower()
    if '/web-inf/views/views/' not in rel_low:
        return False
    name = path.name.lower()
    return any(name.endswith(suffix) for suffix in ('list.jsp', 'detail.jsp', 'form.jsp', 'calendar.jsp', 'view.jsp', 'edit.jsp'))




def _repair_jsp_structural_views_artifact(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    root = Path(project_root) if project_root is not None else None
    if root is not None and _is_structural_views_jsp(path, root):
        path.unlink(missing_ok=True)
        return True
    return False

def _repair_jsp_missing_route_reference(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    if project_root is None or not path.exists():
        return False
    root = Path(project_root)
    if _is_structural_views_jsp(path, root):
        path.unlink(missing_ok=True)
        return True
    rel_low = _normalize_rel_path(str(path.relative_to(root))).lower()
    details = (issue or {}).get("details") or {}
    missing_routes = [str(route).strip() for route in (details.get("missing_routes") or []) if str(route).strip()]
    entry_only_domains = {'index', 'home', 'main'}
    is_entry_view = any(f'/web-inf/views/{name}/' in rel_low for name in entry_only_domains)
    if is_entry_view and missing_routes:
        target_route = _discover_primary_menu_route(root) or _discover_primary_login_route(root) or '/'
        rendered = _render_entry_only_redirect_jsp(target_route)
        if rendered.strip() != _read_text(path).strip():
            path.write_text(rendered, encoding='utf-8')
            return True
    details = (issue or {}).get("details") or {}
    if '/web-inf/views/common/' in rel_low:
        return _repair_auth_nav_route_mismatch(path, issue, project_root)
    if _rewrite_auth_alias_collection_jsp(path, root):
        return True
    calendar_rewritten = False
    if path.name.endswith('Calendar.jsp'):
        calendar_rewritten = _repair_malformed_jsp_structure(path, issue, project_root)
        if calendar_rewritten and not path.exists():
            return True
    if any(token in rel_low for token in ('signup.jsp', 'register.jsp', 'join.jsp')):
        if _rewrite_signup_jsp_to_safe_routes(path, root):
            return True
    body = _read_text(path)
    original = body
    view_domain = path.parent.name
    logical_view_domain = _logical_domain_name(view_domain)
    controller_rewritten = False
    discovered_routes = [str(route).strip() for route in (details.get("discovered_routes") or []) if str(route).strip()]
    missing_routes = [str(route).strip() for route in (details.get("missing_routes") or []) if str(route).strip()]
    if _is_membership_like_domain(view_domain):
        controller_path = _find_domain_controller(root, logical_view_domain) or _find_domain_controller(root, view_domain)
        missing_route_set = {str(route).split('?', 1)[0].strip().lower() for route in missing_routes}
        expected_suffixes = {'/list.do', '/form.do', '/detail.do', '/delete.do', '/save.do', '/actionregister.do', '/checkloginid.do'}
        has_crud_gap = bool(missing_route_set and any(any(item.endswith(suffix) for suffix in expected_suffixes) for item in missing_route_set))
        include_signup_helpers = _is_signup_route_jsp_path(path) or any(item.endswith('/actionregister.do') or item.endswith('/checkloginid.do') for item in missing_route_set)
        normalized_body = _normalize_membership_route_prefixes_in_jsp(body, logical_view_domain, include_signup_helpers=include_signup_helpers)
        if normalized_body != body:
            body = normalized_body
        if controller_path is None and has_crud_gap:
            controller_path = _ensure_membership_controller_path(root, logical_view_domain)
        if controller_path is not None and (has_crud_gap or include_signup_helpers or 'admin' in logical_view_domain.lower()):
            if _rewrite_membership_controller_to_safe_routes(controller_path, logical_view_domain):
                controller_rewritten = True
                discovered_routes = sorted(_discover_controller_routes(root))
        elif controller_path is not None and ('manage' in path.stem.lower() or 'admin' in logical_view_domain.lower()):
            if _rewrite_membership_controller_to_safe_routes(controller_path, logical_view_domain):
                controller_rewritten = True
                discovered_routes = sorted(_discover_controller_routes(root))
        elif has_crud_gap and logical_view_domain != view_domain:
            normalized_body = _normalize_membership_route_prefixes_in_jsp(body, logical_view_domain, include_signup_helpers=include_signup_helpers)
            if normalized_body != body:
                body = normalized_body
        if has_crud_gap:
            schema = _infer_schema_for_jsp_repair(path, root)
            if rel_low.endswith('list.jsp') and _rewrite_list_jsp_from_schema(root, _normalize_rel_path(str(path.relative_to(root))), schema):
                return True
            if rel_low.endswith('detail.jsp') and _rewrite_detail_jsp_from_schema(root, _normalize_rel_path(str(path.relative_to(root))), schema):
                return True
            if rel_low.endswith('form.jsp') and _rewrite_form_jsp_from_schema(root, _normalize_rel_path(str(path.relative_to(root))), schema):
                return True
    if calendar_rewritten and discovered_routes:
        route_refs = set(missing_routes)
        patterns = [
            r"""<c:url\s+value=["'](/[^"']+)["']""",
            r"""\b(?:action|href|src)=["'](?:\$\{pageContext\.request\.contextPath\})?(/[^"']+)["']""",
            r"""(?:location\.href|window\.location(?:\.href)?|fetch|url)\s*[:=,(]\s*["'](?:\$\{pageContext\.request\.contextPath\})?(/[^"']+)["']""",
            r"""["']\$\{pageContext\.request\.contextPath\}(/[^"']+)["']""",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, body, re.IGNORECASE):
                route = (match.group(1) or '').strip()
                if route and not route.startswith(('/css/', '/js/', '/images/', '/webjars/', '/favicon', '/error')) and '://' not in route and not route.endswith(('.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico')):
                    route_refs.add(route)
        missing_routes = sorted(route for route in route_refs if route not in discovered_routes)
    def _match_route_by_suffix(target: str) -> str:
        target = (target or '').strip()
        target_only, query = (target.split('?', 1) + [''])[:2]
        target_low = target_only.lower()
        domain_candidate = _logical_domain_name(view_domain).lower()
        domain_adjusted = ''
        if domain_candidate and any(token in target_low for token in ('/member/', '/tbmember/', '/user/', '/account/', '/adminmember/')):
            parts = target_only.strip('/').split('/')
            if len(parts) >= 2:
                parts[0] = domain_candidate
                domain_adjusted = '/' + '/'.join(parts)
        suffix_aliases = {
            '/login.do': ('/login.do',),
            '/list.do': ('/list.do',),
            '/detail.do': ('/detail.do', '/view.do'),
            '/form.do': ('/form.do', '/edit.do', '/signup.do', '/register.do', '/join.do'),
            '/save.do': ('/save.do',),
            '/delete.do': ('/delete.do',),
            '/calendar.do': ('/calendar.do',),
        }
        for canonical, aliases in suffix_aliases.items():
            if any(target_low.endswith(alias) for alias in aliases):
                candidate = ''
                if domain_adjusted:
                    adjusted_low = domain_adjusted.lower()
                    candidate = next((route for route in discovered_routes if route.lower() == adjusted_low), '')
                    if not candidate:
                        adjusted_suffix = adjusted_low.rsplit('/', 1)[-1]
                        candidate = next((route for route in discovered_routes if route.lower().endswith('/' + adjusted_suffix) and f'/{domain_candidate}/' in route.lower()), '')
                if not candidate:
                    candidate = next((route for route in discovered_routes if route.lower().endswith(canonical) and (not domain_candidate or f'/{domain_candidate}/' in route.lower() or route.lower().startswith(f'/{domain_candidate}/'))), '')
                if not candidate:
                    candidate = next((route for route in discovered_routes if route.lower().endswith(canonical)), '')
                if not candidate and canonical == '/calendar.do':
                    candidate = next((route for route in discovered_routes if route.lower().endswith('/list.do')), '')
                if candidate:
                    return candidate + ((('?' + query)) if query else '')
        if '/login' in target_low:
            candidate = _discover_primary_login_route(root) or ''
            return candidate + ((('?' + query)) if candidate and query else '')
        return ''
    if discovered_routes:
        for missing in missing_routes:
            replacement = _match_route_by_suffix(missing) or _semantic_route_replacement(missing, discovered_routes, path)
            if replacement and replacement != missing:
                body = body.replace(missing, replacement)
    if body != original:
        path.write_text(body, encoding="utf-8")
        return True
    return bool(calendar_rewritten or controller_rewritten)

def _nav_link_with_label_exists(body: str, labels: tuple[str, ...]) -> bool:
    if not body:
        return False
    pattern = '|'.join(re.escape(label) for label in labels if label)
    if not pattern:
        return False
    return bool(re.search(r'<a\b[^>]*>.*?(?:' + pattern + r').*?</a>', body, re.IGNORECASE | re.DOTALL))

def _nav_route_present(body: str, route: str) -> bool:
    return bool(body) and bool(route) and route.lower() in body.lower()


def _rewrite_first_nav_link_route(body: str, labels: tuple[str, ...], route: str) -> str:
    # PATCH: semantic auth-anchor route replacement.
    # It rewrites an existing login/signup anchor instead of appending duplicates.
    if not body or not route:
        return body
    pattern = '|'.join(re.escape(label) for label in labels if label)
    if not pattern:
        return body

    def replace_anchor(match):
        anchor = match.group(0)
        if not re.search(pattern, anchor, re.IGNORECASE | re.DOTALL):
            return anchor
        href_re = re.compile(r'href\s*=\s*([\"\'])(.*?)(\1)', re.IGNORECASE | re.DOTALL)
        if href_re.search(anchor):
            return href_re.sub(lambda hm: f"href={hm.group(1)}<c:url value='{route}' />{hm.group(1)}", anchor, count=1)
        return re.sub(r'<a\b', f"<a href=\"<c:url value='{route}' />\"", anchor, count=1, flags=re.IGNORECASE)

    anchor_re = re.compile(r'<a\b[^>]*>.*?</a>', re.IGNORECASE | re.DOTALL)
    return anchor_re.sub(replace_anchor, body, count=1)


def _repair_auth_nav_route_mismatch(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    """Repair a single common JSP authentication navigation file.

    The function appends required login/signup entries based on issue details or
    discovered controller routes. It intentionally avoids domain-specific constants
    and avoids destructive removal of optional authentication links.
    """
    if project_root is None or not path.exists():
        return False
    root = Path(project_root)
    details = (issue or {}).get('details') or {}
    login_route = str(details.get('login_route') or _discover_primary_login_route(root) or '').strip()
    signup_route = str(details.get('signup_route') or _discover_signup_route(root) or '').strip()
    body = _read_text(path)
    original = body

    def c_url(route: str) -> str:
        return f"<c:url value='{route}' />"

    def append_item(label: str, route: str) -> None:
        nonlocal body
        if not route:
            return
        item = f'    <li><a href="{c_url(route)}">{label}</a></li>\n'
        lower = body.lower()
        for close_tag in ('</ul>', '</nav>', '</div>', '</header>'):
            idx = lower.rfind(close_tag)
            if idx >= 0:
                body = body[:idx] + item + body[idx:]
                return
        body = body.rstrip() + '\n' + item

    # PATCH: rewrite semantic auth anchors first; append only if the anchor is absent.
    if login_route:
        body = _rewrite_first_nav_link_route(body, ('로그인', 'login'), login_route)
        if not _nav_link_with_label_exists(body, ('로그인', 'login')):
            append_item('로그인', login_route)
    if signup_route:
        body = _rewrite_first_nav_link_route(body, ('회원가입', 'signup', 'register', 'join'), signup_route)
        if not _nav_link_with_label_exists(body, ('회원가입', 'signup', 'register', 'join')):
            append_item('회원가입', signup_route)

    if body != original:
        path.write_text(body, encoding='utf-8')
        return True
    return False

def _parse_vo_field_types(vo_path: Path) -> Dict[str, str]:
    body = _read_text(vo_path) if vo_path.exists() else ''
    out: Dict[str, str] = {}
    for m in re.finditer(r'private\s+([A-Za-z0-9_$.<>]+)\s+(\w+)\s*;', body):
        type_name = (m.group(1) or '').strip()
        prop = (m.group(2) or '').strip()
        if not prop or prop == 'serialVersionUID':
            continue
        out[_snake_case_from_prop(prop)] = type_name
    return out


def _sanitize_alignment_columns(mapper_columns: List[str], schema_columns: List[str], vo_columns: List[str]) -> List[str]:
    mapper_cols = [str(c or '').strip().lower() for c in (mapper_columns or []) if str(c or '').strip()]
    schema_cols = [str(c or '').strip().lower() for c in (schema_columns or []) if str(c or '').strip()]
    vo_cols = [str(c or '').strip().lower() for c in (vo_columns or []) if str(c or '').strip()]
    suspicious_only = {'string', 'varchar', 'char', 'text', 'integer', 'number'}
    if not mapper_cols:
        return _sanitize_mapper_schema_columns(schema_cols or vo_cols)
    schema_set = set(schema_cols)
    vo_set = set(vo_cols)
    cleaned: List[str] = []
    for col in mapper_cols:
        if _is_generation_metadata_column(col):
            continue
        if col in suspicious_only and (schema_set or vo_set) and col not in schema_set and col not in vo_set:
            continue
        if col not in cleaned:
            cleaned.append(col)
    fallback = _sanitize_mapper_schema_columns(schema_cols or vo_cols or mapper_cols)
    return cleaned or fallback


def _infer_base_package_for_path(path: Path, fallback: str = 'egovframework.app') -> str:
    body = _read_text(path) if path.exists() else ''
    pkg_match = re.search(r'package\s+([A-Za-z0-9_.]+)\s*;', body)
    if pkg_match:
        pkg = (pkg_match.group(1) or '').strip()
        for suffix in ('.web', '.service.vo', '.service.mapper', '.service.impl', '.service'):
            if pkg.endswith(suffix):
                return pkg[:-len(suffix)]
        return pkg
    ns_match = re.search(r'<mapper[^>]+namespace="([A-Za-z0-9_.]+)"', body)
    if ns_match:
        ns = (ns_match.group(1) or '').strip()
        if ns.endswith('.' + path.stem):
            ns = ns[:-(len(path.stem) + 1)]
        for suffix in ('.service.mapper', '.service', '.web'):
            if ns.endswith(suffix):
                return ns[:-len(suffix)]
        return ns
    return fallback


def _crud_schema_for_alignment(entity: str, table: str, columns: List[str], vo_path: Path | None = None):
    type_hints = _parse_vo_field_types(vo_path) if vo_path is not None else {}
    inferred_fields = []
    for column in columns or []:
        prop = _camel_prop_from_column(column)
        if not prop:
            continue
        inferred_fields.append((prop, column, type_hints.get(column) or _java_type_for_column(column)))
    return schema_for(entity, inferred_fields=inferred_fields, table=table, feature_kind=FEATURE_KIND_CRUD)


def _regenerate_mapper_and_vo_from_alignment(path: Path, issue: Dict[str, Any] | None, project_root: Path | None) -> bool:
    if project_root is None:
        return False
    details = (issue or {}).get('details') or {}
    mapper_contract = _parse_mapper_contract_from_file(path) if path.exists() else {'table': '', 'columns': []}
    table = str(details.get('table') or mapper_contract.get('table') or '').strip().lower()
    mapper_cols = [str(c or '').strip().lower() for c in (details.get('mapper_columns') or mapper_contract.get('columns') or []) if str(c or '').strip()]
    schema_cols = [str(c or '').strip().lower() for c in (details.get('schema_columns') or []) if str(c or '').strip()]
    vo_cols = [str(c or '').strip().lower() for c in (details.get('vo_columns') or []) if str(c or '').strip()]
    vo_rel = _normalize_rel_path(details.get('vo_path') or '')
    vo_path = (Path(project_root) / vo_rel) if vo_rel else None
    columns = _sanitize_alignment_columns(mapper_cols, schema_cols, vo_cols)
    if not table or not columns:
        return False
    stem = path.stem[:-6] if path.stem.endswith('Mapper') else path.stem
    entity = stem[:1].upper() + stem[1:] if stem else (table[:1].upper() + table[1:] if table else 'Item')
    schema = _crud_schema_for_alignment(entity, table, columns, vo_path)
    changed = False
    base_package = _infer_base_package_for_path(path)
    mapper_body = builtin_file(f'mapper/{schema.entity_var}/{entity}Mapper.xml', base_package, schema)
    if mapper_body and mapper_body.strip() != _read_text(path).strip():
        path.write_text(mapper_body, encoding='utf-8')
        changed = True
    if vo_path is not None and vo_path.exists():
        vo_body = builtin_file(f'java/service/vo/{entity}VO.java', _infer_base_package_for_path(vo_path, base_package), schema)
        if vo_body and vo_body.strip() != _read_text(vo_path).strip():
            vo_path.write_text(vo_body, encoding='utf-8')
            changed = True
    return changed


_old_sync_schema_table_from_mapper = _sync_schema_table_from_mapper

def _sync_schema_table_from_mapper(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None, cascade: bool = True) -> bool:
    details = (issue or {}).get('details') or {}
    patched_issue = dict(issue or {})
    patched_details = dict(details)
    mapper_contract = _parse_mapper_contract_from_file(path) if path.exists() else {'table': '', 'columns': []}
    patched_details['mapper_columns'] = _sanitize_alignment_columns(
        details.get('mapper_columns') or mapper_contract.get('columns') or [],
        details.get('schema_columns') or [],
        details.get('vo_columns') or [],
    )
    patched_issue['details'] = patched_details
    return _old_sync_schema_table_from_mapper(path, patched_issue, project_root, cascade)


_old_repair_mapper_vo_column_mismatch = _repair_mapper_vo_column_mismatch

def _repair_mapper_vo_column_mismatch(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    if _regenerate_mapper_and_vo_from_alignment(path, issue, project_root):
        return True
    return _old_repair_mapper_vo_column_mismatch(path, issue, project_root)


_old_repair_calendar_controller = _repair_calendar_controller

def _repair_calendar_controller(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    details = (issue or {}).get('details') or {}
    expected_view = details.get('expected_view') or ''
    if not expected_view:
        return False
    body = _read_text(path)
    original = body
    body = _remove_non_auth_forbidden_ui_fields(body)
    body = _ensure_import(body, 'org.springframework.ui.Model')
    method_lines = [
        '    @GetMapping("/calendar.do")',
        '    public String calendar(Model model) throws Exception {',
        '        java.time.LocalDate today = java.time.LocalDate.now();',
        '        int targetYear = today.getYear();',
        '        int targetMonth = today.getMonthValue();',
        '        java.time.YearMonth yearMonth = java.time.YearMonth.of(targetYear, targetMonth);',
        '        java.time.LocalDate firstDay = yearMonth.atDay(1);',
        '        java.time.LocalDate gridStart = firstDay.with(java.time.temporal.TemporalAdjusters.previousOrSame(java.time.DayOfWeek.SUNDAY));',
        '        java.util.List<java.util.Map<String, Object>> calendarCells = new java.util.ArrayList<>();',
        '        for (int i = 0; i < 42; i++) {',
        '            java.time.LocalDate cellDate = gridStart.plusDays(i);',
        '            java.util.Map<String, Object> cell = new java.util.LinkedHashMap<>();',
        '            cell.put("date", cellDate);',
        '            cell.put("day", cellDate.getDayOfMonth());',
        '            cell.put("currentMonth", cellDate.getMonthValue() == targetMonth);',
        '            cell.put("today", cellDate.equals(today));',
        '            cell.put("events", java.util.Collections.emptyList());',
        '            cell.put("eventCount", 0);',
        '            calendarCells.add(cell);',
        '        }',
        '        java.util.List<Object> selectedDateSchedules = java.util.Collections.emptyList();',
        '        model.addAttribute("calendarCells", calendarCells);',
        '        model.addAttribute("calendarcells", calendarCells);',
        '        model.addAttribute("selectedDateSchedules", selectedDateSchedules);',
        '        model.addAttribute("selecteddateschedules", selectedDateSchedules);',
        '        model.addAttribute("currentYear", targetYear);',
        '        model.addAttribute("currentyear", targetYear);',
        '        model.addAttribute("currentMonth", targetMonth);',
        '        model.addAttribute("currentmonth", targetMonth);',
        '        model.addAttribute("prevYear", yearMonth.minusMonths(1).getYear());',
        '        model.addAttribute("prevyear", yearMonth.minusMonths(1).getYear());',
        '        model.addAttribute("prevMonth", yearMonth.minusMonths(1).getMonthValue());',
        '        model.addAttribute("prevmonth", yearMonth.minusMonths(1).getMonthValue());',
        '        model.addAttribute("nextYear", yearMonth.plusMonths(1).getYear());',
        '        model.addAttribute("nextyear", yearMonth.plusMonths(1).getYear());',
        '        model.addAttribute("nextMonth", yearMonth.plusMonths(1).getMonthValue());',
        '        model.addAttribute("nextmonth", yearMonth.plusMonths(1).getMonthValue());',
        f'        return "{expected_view}";',
        '    }',
    ]
    method_source = "\n".join(method_lines)
    if '@getmapping("/calendar.do")' in body.lower() or "@getmapping('/calendar.do')" in body.lower():
        cal_pat = re.compile(r"@GetMapping\(\s*[\"']\/calendar\.do[\"']\s*\)\s*public\s+String\s+\w+\s*\([^)]*\)\s*(?:throws\s+[^\{]+)?\{.*?\n\s*\}", re.DOTALL)
        body = cal_pat.sub(method_source, body, count=1)
    else:
        insert_at = body.rfind('}')
        if insert_at != -1:
            body = body[:insert_at] + '\n\n' + method_source + '\n' + body[insert_at:]
    if body != original:
        path.write_text(body, encoding='utf-8')
        return True
    return _old_repair_calendar_controller(path, issue, project_root)


def _repair_startup_sql_schema_issue(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    target_rel = _normalize_rel_path(str(path))
    if _is_framework_internal_path(target_rel):
        return False
    if path.name == 'schema.sql' and path.exists():
        body = _read_text(path)
        updated = _dedupe_alter_add_column_statements(body)
        if updated != body:
            path.write_text(updated, encoding='utf-8')
            return True
        return False
    if path.name in {'data.sql', 'login-data.sql'} and path.exists() and project_root is not None:
        schema_path = _primary_schema_path(project_root, issue)
        if _sanitize_data_sql_against_schema(path, schema_path):
            return True
        return False
    if path.name.endswith('Initializer.java') and path.exists() and project_root is not None:
        try:
            from app.io.execution_core_apply import _write_auth_database_initializer
        except Exception:
            return False
        body = _read_text(path)
        if 'schema.sql' not in body and 'login-schema.sql' not in body and 'ResourceDatabasePopulator' not in body and 'member_account' not in body:
            return False
        base_package = _extract_base_package_from_initializer(path)
        if not base_package:
            return False
        before = body
        rewritten = _write_auth_database_initializer(Path(project_root), base_package)
        after = _read_text(rewritten) if rewritten and rewritten.exists() else ''
        return bool(after and after != before)
    return False


def _repair_startup_bean_wiring_issue(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    return _repair_startup_sql_schema_issue(path, issue, project_root)


def _repair_unexpected_auth_helper_artifact(path: Path, issue: Dict[str, Any] | None = None, project_root: Path | None = None) -> bool:
    helper = str(((issue or {}).get('details') or {}).get('helper') or '').strip().lower()
    changed = False
    if path.exists():
        try:
            path.unlink()
            changed = True
        except Exception:
            pass
    if project_root is None or not helper:
        return changed
    root = Path(project_root)
    token_map = {
        'jwt': ('jwtlogin', 'jwttokenprovider', '/login/jwtLogin.do', '/login/actionJwtLogin.do', '/login/api/jwtLogin.do'),
        'cert': ('certlogin', 'certificate login', '/login/certLogin.do', '/login/actionCertLogin.do'),
        'integration': ('integrationguide', 'integratedauth', 'integratedlogin', 'ssologin', '/login/integrationGuide.do', '/login/integratedLogin.do', '/login/ssoLogin.do', '/login/integratedCallback.do'),
    }
    targets = token_map.get(helper, ())
    if not targets:
        return changed
    for pattern in ('*.jsp', '*.java', '*.xml'):
        for candidate in root.rglob(pattern):
            if not candidate.is_file() or candidate == path:
                continue
            body = _read_text(candidate)
            original = body
            lines = []
            for line in body.splitlines():
                low = line.lower()
                if any(token.lower() in low for token in targets):
                    continue
                lines.append(line)
            body = '\n'.join(lines)
            if body != original:
                candidate.write_text(body + ('\n' if original.endswith('\n') else ''), encoding='utf-8')
                changed = True
    return changed


REPAIR_HANDLERS = {
    "duplicate_boolean_getter": _repair_duplicate_boolean_getters,
    "temporal_input_type": _repair_temporal_inputs,
    "missing_delete_ui": _repair_delete_ui,
    "nested_form": _repair_nested_form,
    "invalid_action_wrapper": _repair_invalid_action_wrapper,
    "broken_c_url": _repair_broken_c_url,
    "malformed_jsp_structure": _repair_malformed_jsp_structure,
    "auth_nav_route_mismatch": _repair_auth_nav_route_mismatch,
    "jsp_missing_route_reference": _repair_jsp_missing_route_reference,
    "jsp_structural_views_artifact": _repair_jsp_structural_views_artifact,
    "route_param_mismatch": _repair_route_param_mismatch,
    "missing_view": _repair_missing_view,
    "calendar_controller_missing": _repair_calendar_controller_missing,
    "calendar_mapping_missing": _repair_calendar_controller,
    "calendar_view_mismatch": _repair_calendar_controller,
    "calendar_ssr_missing": _repair_calendar_ssr_missing,
    "legacy_calendar_jsp": _repair_calendar_ssr_missing,
    "calendar_data_contract_missing": _repair_calendar_data_contract,
    "id_type_mismatch": _repair_controller_signature_alignment,
    "controller_service_signature_mismatch": _repair_controller_signature_alignment,
    "optional_param_guard_mismatch": _repair_optional_param_guard_mismatch,
    "undefined_vo_getter_usage": _repair_undefined_vo_getter_usage,
    "jsp_vo_property_mismatch": _repair_jsp_vo_property_mismatch,
    "jsp_dependency_missing": _repair_jsp_dependency_missing,
    "ambiguous_request_mapping": _repair_ambiguous_request_mapping,
    "duplicate_schema_initializer": _repair_duplicate_schema_initializer,
    "index_entrypoint_miswired": _repair_index_entrypoint_controller,
    "index_entrypoint_crud_leak": _repair_index_entrypoint_controller,
    "schema_variant_conflict": _repair_schema_variant_conflict,
    "schema_conflict": _repair_schema_variant_conflict,
    "duplicate_table_definition": _repair_duplicate_table_definition,
    "mapper_namespace_mismatch": _repair_mapper_namespace_mismatch,
    "mapper_vo_column_mismatch": _repair_mapper_vo_column_mismatch,
    "mapper_table_column_mismatch": _sync_schema_table_from_mapper,
    "schema_generation_metadata_column": _sync_schema_table_from_mapper,
    "schema_column_comment_missing": _ensure_schema_column_comments,
    "search_fields_incomplete": _repair_search_fields_incomplete,
    "missing_delete_ui": _repair_delete_ui,
    "search_ui_missing": _repair_search_fields_incomplete,
    "form_fields_incomplete": _repair_form_fields_incomplete,
    "table_prefix_missing": _repair_table_prefix_missing,
    "startup_sql_schema_issue": _repair_startup_sql_schema_issue,
    "startup_bean_wiring_issue": _repair_startup_bean_wiring_issue,
    "unexpected_auth_helper_artifact": _repair_unexpected_auth_helper_artifact,
}




def _force_repair_common_auth_navigation(project_root: Path, issue: Dict[str, Any] | None = None) -> bool:
    """Final auth-nav safety pass for common JSP layouts.

    The pass appends the required authentication entries when the route/label
    contract is missing. It does not assume fixed domains and it does not remove
    optional auth entries, so it is safe for JSP/React/Vue/Nexacro generators that
    share the same route contract discovery layer.
    """
    root = Path(project_root)
    details = (issue or {}).get('details') or {}
    login_route = str(details.get('login_route') or _discover_primary_login_route(root) or '').strip()
    signup_route = str(details.get('signup_route') or _discover_signup_route(root) or '').strip()
    changed = False

    def c_url(route: str) -> str:
        return f"<c:url value='{route}' />"

    def append_item(body: str, label: str, route: str) -> str:
        item = f'    <li><a href="{c_url(route)}">{label}</a></li>\n'
        lower = body.lower()
        for close_tag in ('</ul>', '</nav>', '</div>', '</header>'):
            idx = lower.rfind(close_tag)
            if idx >= 0:
                return body[:idx] + item + body[idx:]
        return body.rstrip() + '\n' + item

    for rel in ('src/main/webapp/WEB-INF/views/common/header.jsp', 'src/main/webapp/WEB-INF/views/common/leftNav.jsp'):
        path = root / rel
        if not path.exists():
            continue
        body = _read_text(path)
        original = body
        # PATCH: rewrite semantic auth anchors first; append only if the anchor is absent.
        if login_route:
            body = _rewrite_first_nav_link_route(body, ('로그인', 'login'), login_route)
            if not _nav_link_with_label_exists(body, ('로그인', 'login')):
                body = append_item(body, '로그인', login_route)
        if signup_route:
            body = _rewrite_first_nav_link_route(body, ('회원가입', 'signup', 'register', 'join'), signup_route)
            if not _nav_link_with_label_exists(body, ('회원가입', 'signup', 'register', 'join')):
                body = append_item(body, '회원가입', signup_route)
        if body != original:
            path.write_text(body, encoding='utf-8')
            changed = True
    return changed

def auto_repair_generated_project(project_root: Path, validation_report: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(project_root)
    changed: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []
    for issue in validation_report.get("static_issues") or []:
        if not issue.get("repairable"):
            continue
        issue_type = issue.get("type") or issue.get("code") or ""
        handler = REPAIR_HANDLERS.get(issue_type)
        if not handler:
            skipped.append({"path": issue.get("path") or "", "reason": "no_handler"})
            continue
        target = root / _normalize_rel_path(issue.get("path") or "")
        if issue_type not in {"missing_view", "schema_variant_conflict"} and not target.exists():
            skipped.append({"path": issue.get("path") or "", "reason": "missing_target"})
            continue
        if handler(target, issue, root):
            changed.append({"path": issue.get("path") or "", "type": issue_type})
        else:
            skipped.append({"path": issue.get("path") or "", "reason": "no_change"})
    # Final generic safety pass for common authentication navigation.
    # This is intentionally route-discovery based and not tied to member/adminMember.
    auth_nav_issue = next((item for item in (validation_report.get("static_issues") or []) if (item.get("type") or item.get("code")) == "auth_nav_route_mismatch"), None)
    if _force_repair_common_auth_navigation(root, auth_nav_issue):
        changed.append({"path": "src/main/webapp/WEB-INF/views/common", "type": "auth_nav_route_mismatch"})
    return {"changed": changed, "skipped": skipped, "changed_count": len(changed)}


def apply_generated_project_auto_repair(project_root: Path, validation_report: Dict[str, Any]) -> Dict[str, Any]:
    code_map = {
        "ambiguous_boolean_getter": "duplicate_boolean_getter",
        "temporal_input_type_mismatch": "temporal_input_type",
        "missing_delete_ui": "missing_delete_ui",
        "nested_form": "nested_form",
        "invalid_action_wrapper": "invalid_action_wrapper",
        "broken_c_url": "broken_c_url",
        "malformed_jsp_structure": "malformed_jsp_structure",
        "auth_nav_route_mismatch": "auth_nav_route_mismatch",
        "jsp_missing_route_reference": "jsp_missing_route_reference",
        "jsp_structural_views_artifact": "jsp_structural_views_artifact",
        "route_param_mismatch": "route_param_mismatch",
        "calendar_controller_missing": "calendar_controller_missing",
        "calendar_mapping_missing": "calendar_mapping_missing",
        "calendar_view_mismatch": "calendar_view_mismatch",
        "calendar_ssr_missing": "calendar_ssr_missing",
        "legacy_calendar_jsp": "legacy_calendar_jsp",
        "calendar_data_contract_missing": "calendar_data_contract_missing",
        "id_type_mismatch": "id_type_mismatch",
        "controller_vo_type_mismatch": "id_type_mismatch",
        "controller_service_signature_mismatch": "controller_service_signature_mismatch",
        "optional_param_guard_mismatch": "optional_param_guard_mismatch",
        "undefined_vo_getter_usage": "undefined_vo_getter_usage",
        "jsp_vo_property_mismatch": "jsp_vo_property_mismatch",
        "jsp_dependency_missing": "jsp_dependency_missing",
        "ambiguous_request_mapping": "ambiguous_request_mapping",
        "duplicate_schema_initializer": "duplicate_schema_initializer",
        "index_entrypoint_miswired": "index_entrypoint_miswired",
        "index_entrypoint_crud_leak": "index_entrypoint_crud_leak",
        "schema_variant_conflict": "schema_variant_conflict",
        "schema_conflict": "schema_conflict",
        "duplicate_table_definition": "duplicate_table_definition",
        "mapper_namespace_mismatch": "mapper_namespace_mismatch",
        "mapper_vo_column_mismatch": "mapper_vo_column_mismatch",
        "search_fields_incomplete": "search_fields_incomplete",
        "search_ui_missing": "search_fields_incomplete",
        "form_fields_incomplete": "form_fields_incomplete",
        "table_prefix_missing": "table_prefix_missing",
        "missing_view_jsp": "missing_view",
        "startup_sql_schema_issue": "startup_sql_schema_issue",
        "startup_bean_wiring_issue": "startup_bean_wiring_issue",
        "unexpected_auth_helper_artifact": "unexpected_auth_helper_artifact",
    }
    normalized = {"static_issues": []}
    for issue in validation_report.get("issues") or []:
        code = issue.get("type") or issue.get("code") or ""
        normalized["static_issues"].append(
            {
                "type": code_map.get(code, code),
                "path": issue.get("path") or "",
                "repairable": bool(issue.get("repairable", True)),
                "details": issue.get("details") or {},
            }
        )
    return auto_repair_generated_project(project_root, normalized)
