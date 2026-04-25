from __future__ import annotations

import re
from pathlib import Path

GENERATION_METADATA_MARKERS = ('db', 'schemaName', 'schema_name', 'database', 'tableName', 'table_name', 'packageName', 'package_name', 'frontendType', 'backendType', 'compile', 'compiled', 'build', 'runtime', 'startup', 'endpoint_smoke')
AUTH_SENSITIVE_MARKERS = ('password', 'loginpassword', 'login_password', 'loginpwd', 'login_pwd', 'passwd', 'pwd', 'userpw', 'user_pw', 'passcode', 'passwordhash', 'password_hash', 'passwordsalt', 'password_salt', 'secretkey', 'secret_key', 'credential', 'credentials', 'pincode', 'pin_code', 'pinno', 'pin_no')
PLACEHOLDER_UI_MARKERS = ('sampledto', 'entityname', 'fieldname', 'table_name', 'schema_name', 'package_name')


_BALANCED_MARKUP_TAGS = (
    'form', 'div', 'section', 'article', 'aside', 'table', 'tr', 'td', 'ul', 'li', 'nav', 'body',
    'c:if', 'c:choose', 'c:when', 'c:otherwise', 'c:forEach', 'c:forTokens', 'c:catch',
)


def _strip_orphan_closing_tags(body: str, tags: tuple[str, ...] = _BALANCED_MARKUP_TAGS) -> str:
    rendered = body or ''
    if not rendered.strip():
        return rendered

    opaque_pattern = re.compile(r'(?is)<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>|<!--.*?-->|<%--.*?--%>')
    opaque_blocks: list[str] = []

    def _stash(match: re.Match) -> str:
        opaque_blocks.append(match.group(0) or '')
        return f'__AUTOPJ_OPAQUE_{len(opaque_blocks) - 1}__'

    working = opaque_pattern.sub(_stash, rendered)
    tag_names = '|'.join(re.escape(tag) for tag in tags)
    token_re = re.compile(rf'(?is)<(?P<closing>/)?(?P<tag>{tag_names})(?P<attrs>\b[^>]*)?>')
    parts: list[str] = []
    stack: list[str] = []
    last = 0
    for match in token_re.finditer(working):
        parts.append(working[last:match.start()])
        token = match.group(0) or ''
        tag = match.group('tag') or ''
        is_closing = bool(match.group('closing'))
        is_self_closing = token.rstrip().endswith('/>')
        if is_closing:
            if tag in stack:
                while stack and stack[-1] != tag:
                    parts.append(f'</{stack.pop()}>')
                if stack and stack[-1] == tag:
                    stack.pop()
                    parts.append(token)
            else:
                pass
        else:
            parts.append(token)
            if not is_self_closing:
                stack.append(tag)
        last = match.end()
    parts.append(working[last:])
    while stack:
        parts.append(f'</{stack.pop()}>')
    balanced = ''.join(parts)
    for idx, block in enumerate(opaque_blocks):
        balanced = balanced.replace(f'__AUTOPJ_OPAQUE_{idx}__', block)
    balanced = re.sub(r'\n{3,}', '\n\n', balanced)
    return balanced


def _auth_ui_path_tail(path: str | Path) -> str:
    raw = str(path or '').replace('\\', '/')
    lower = raw.lower()
    for marker in ('/web-inf/views/', '/src/pages/', '/src/views/', '/frontend/react/src/', '/frontend/vue/src/'):
        idx = lower.find(marker)
        if idx >= 0:
            return raw[idx:]
    parts = [p for p in raw.split('/') if p]
    return '/'.join(parts[-5:]) if parts else raw


def _auth_ui_scan_tokens(path: str | Path) -> set[str]:
    raw = _auth_ui_path_tail(path)
    raw = re.sub(r'([a-z0-9])([A-Z])', r'\1/\2', raw)
    raw = re.sub(r'[^A-Za-z0-9]+', '/', raw).strip('/').lower()
    compact = raw.replace('/', '')
    tokens = {token for token in raw.split('/') if token}
    if 'login' in compact:
        tokens.add('login')
    if 'signup' in compact:
        tokens.add('signup')
    if 'signin' in compact:
        tokens.add('signin')
    if 'register' in compact:
        tokens.add('register')
    if 'join' in compact:
        tokens.add('join')
    if 'password' in compact or 'passwd' in compact:
        tokens.add('password')
    return tokens


def is_auth_ui_file_path(path: str | Path) -> bool:
    norm = _auth_ui_path_tail(path).replace('\\', '/').lower()
    basename = norm.rsplit('/', 1)[-1]
    stem = basename.rsplit('.', 1)[0]
    compact_stem = re.sub(r'[^a-z0-9]+', '', stem)
    collection_suffixes = ('list', 'detail', 'calendar')
    auth_collection_prefixes = ('login', 'signin', 'auth')
    if compact_stem.endswith(collection_suffixes):
        if any(compact_stem == f"{prefix}{suffix}" for prefix in auth_collection_prefixes for suffix in collection_suffixes):
            return True
        return False
    if compact_stem.endswith('form') and compact_stem not in {'signupform', 'registerform', 'joinform', 'loginform', 'signinform'}:
        return False
    auth_exact = {
        'login', 'signin', 'signup', 'register', 'join', 'auth',
        'passwordreset', 'resetpassword', 'changepassword', 'passwordchange',
        'certlogin', 'jwtlogin', 'integratedlogin', 'ssologin',
    }
    if compact_stem in auth_exact or any(compact_stem.endswith(token) for token in auth_exact if len(token) > 4):
        return True
    if '/login/' in norm or '/auth/' in norm:
        return True
    tokens = _auth_ui_scan_tokens(path)
    auth_tokens = {
        'login', 'auth', 'signup', 'signin', 'register', 'join',
        'password', 'passwd', 'reset', 'resetpassword', 'passwordreset',
    }
    if tokens & auth_tokens and not compact_stem.endswith(collection_suffixes):
        return True
    auth_markers = ('/login/', '/auth/', 'sign-up', 'sign-in', 'reset-password', 'resetpassword')
    return any(marker in norm for marker in auth_markers)


_ACCOUNT_DOMAIN_TOKENS = {'user', 'member', 'account', 'admin', 'employee', 'staff', 'customer', 'manager', 'operator'}
_ACCOUNT_FORM_TOKENS = {'form', 'edit', 'create', 'register', 'signup', 'join', 'save'}
_ACCOUNT_IDENTIFIER_MARKERS = ('loginid', 'login_id', 'userid', 'user_id', 'memberid', 'member_id', 'accountid', 'account_id', 'email')


def _ui_path_tokens(path: str | Path) -> set[str]:
    norm = _auth_ui_path_tail(path)
    norm = re.sub(r'([a-z0-9])([A-Z])', r'\1/\2', norm)
    norm = re.sub(r'[^A-Za-z0-9]+', '/', norm).strip('/').lower()
    return {token for token in norm.split('/') if token}


def _is_collection_ui_path(path: str | Path) -> bool:
    norm = _auth_ui_path_tail(path).replace('\\', '/').lower()
    basename = norm.rsplit('/', 1)[-1]
    stem = basename.rsplit('.', 1)[0]
    compact_stem = re.sub(r'[^a-z0-9]+', '', stem)
    return compact_stem.endswith(('list', 'detail', 'calendar', 'search'))


def allows_auth_sensitive_in_account_form(path: str | Path, body: str = '') -> bool:
    if is_auth_ui_file_path(path):
        return True
    if _is_collection_ui_path(path):
        return False
    tokens = _ui_path_tokens(path)
    compact_path = ''.join(sorted(tokens))
    form_like = bool(tokens & _ACCOUNT_FORM_TOKENS)
    if not form_like:
        basename = _auth_ui_path_tail(path).replace('\\', '/').lower().rsplit('/', 1)[-1]
        stem = basename.rsplit('.', 1)[0]
        compact_stem = re.sub(r'[^a-z0-9]+', '', stem)
        form_like = compact_stem.endswith(('form', 'edit', 'create', 'register', 'signup', 'join'))
    if not form_like:
        return False
    body_low = re.sub(r'[^a-z0-9_]+', ' ', str(body or '').lower())
    has_password = any(marker in body_low for marker in ('password', 'login_password', 'loginpassword', 'passwd', 'pwd'))
    has_identifier = any(marker in body_low for marker in _ACCOUNT_IDENTIFIER_MARKERS)
    account_domain = bool(tokens & _ACCOUNT_DOMAIN_TOKENS) or any(token in compact_path for token in ('user', 'member', 'account', 'employee', 'customer', 'admin'))
    return form_like and has_password and has_identifier and account_domain


def sanitize_frontend_ui_text(path: str | Path, body: str, reason: str) -> str:
    original = body or ''
    low_reason = (reason or '').lower()
    markers: list[str] = []
    if 'generation metadata' in low_reason or 'non-auth ui' in low_reason:
        markers.extend(GENERATION_METADATA_MARKERS)
    if ('auth-sensitive' in low_reason or 'password/login_password' in low_reason or 'non-auth ui' in low_reason) and not allows_auth_sensitive_in_account_form(path, original):
        markers.extend(AUTH_SENSITIVE_MARKERS)
    if 'undefined vo properties' in low_reason:
        markers.extend(AUTH_SENSITIVE_MARKERS)
        markers.extend(GENERATION_METADATA_MARKERS)
        markers.extend(PLACEHOLDER_UI_MARKERS)
    markers.extend(PLACEHOLDER_UI_MARKERS)
    markers = [m for i, m in enumerate(markers) if m and m not in markers[:i]]
    if not markers:
        return original
    body = original
    for marker in markers:
        marker_pat = re.escape(marker)
        body = re.sub(rf"""<!--(?:(?!-->).)*\b{marker_pat}\b(?:(?!-->).)*-->""", '', body, flags=re.IGNORECASE | re.DOTALL)
        body = re.sub(rf"""<%--(?:(?!--%>).)*\b{marker_pat}\b(?:(?!--%>).)*--%>""", '', body, flags=re.IGNORECASE | re.DOTALL)
        body = re.sub(rf"""<c:out[^>]*value\s*=\s*['"]\s*\$\{{[^}}]*{marker_pat}[^}}]*\}}\s*['"][^>]*/>""", '', body, flags=re.IGNORECASE)
        body = re.sub(rf"""test\s*=\s*['"]\s*\$\{{[^}}]*{marker_pat}[^}}]*\}}\s*['"]""", 'test="false"', body, flags=re.IGNORECASE)
        body = re.sub(rf'\$\{{[^}}]*{marker_pat}[^}}]*\}}', '', body, flags=re.IGNORECASE)
        body = re.sub(rf'#\{{[^}}]*{marker_pat}[^}}]*\}}', '', body, flags=re.IGNORECASE)
        body = re.sub(rf"""<([A-Za-z0-9:_-]+)[^>]*(?:name|id|for|path|items|value|data-field|data-name)\s*=\s*['"][^'"]*{marker_pat}[^'"]*['"][^>]*>.*?</\1>""", '', body, flags=re.IGNORECASE | re.DOTALL)
        body = re.sub(rf"""<(?:input|select|textarea|option|button|label|div|span|p|td|th)[^>]*(?:name|id|for|path|value|data-field|data-name)\s*=\s*['"][^'"]*{marker_pat}[^'"]*['"][^>]*/?>""", '', body, flags=re.IGNORECASE | re.DOTALL)
        body = re.sub(rf"""<(?:tr|li|dt|dd|section|article|div|p|label)[^>]*>.*?\b{marker_pat}\b.*?</(?:tr|li|dt|dd|section|article|div|p|label)>""", '', body, flags=re.IGNORECASE | re.DOTALL)
        body = re.sub(rf"""<(?:th|td|label|span|div|p|option|li|dt|dd|strong|em|small|button)[^>]*>[^<]*\b{marker_pat}\b[^<]*</(?:th|td|label|span|div|p|option|li|dt|dd|strong|em|small|button)>""", '', body, flags=re.IGNORECASE | re.DOTALL)
        body = re.sub(rf'(?im)^.*\b(?:var|let|const)\s+[A-Za-z0-9_]+\s*=.*\b{marker_pat}\b.*(?:\n|$)', '', body)
        body = re.sub(rf'(?im)^.*\b{marker_pat}\b\s*[:=].*(?:\n|$)', '', body)
        body = re.sub(rf"(?im)^.*[\"']\s*{marker_pat}\s*[\"'].*(?:\n|$)", '', body)
    for marker in markers:
        marker_pat = re.escape(marker)
        body = re.sub(rf'(?im)^.*\b{marker_pat}\b.*(?:\n|$)', '', body)
        body = re.sub(rf'(?im)^.*\$\{{[^}}]*{marker_pat}[^}}]*\}}.*(?:\n|$)', '', body)
    body = re.sub(r'(?is)<script[^>]*>\s*</script>', '', body)
    body = _strip_orphan_closing_tags(body)
    body = re.sub(r'\n{3,}', '\n\n', body)
    return body


def repair_invalid_generated_content(path: str | Path, body: str, reason: str, frontend_key: str = '') -> tuple[str, bool, bool, str]:
    original = body or ''
    cleaned = sanitize_frontend_ui_text(path, original, reason)
    if cleaned == original:
        return original, False, False, reason
    from app.ui.generated_content_validator import validate_generated_content
    ok, err = validate_generated_content(str(path), cleaned, frontend_key=frontend_key)
    return cleaned, True, ok, err
