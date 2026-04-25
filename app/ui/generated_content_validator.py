from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Tuple

from app.ui.ui_sanitize_common import allows_auth_sensitive_in_account_form


_GENERATION_METADATA_MARKERS = ('schemaname', 'schema_name', 'db', 'database', 'tablename', 'table_name', 'packagename', 'package_name', 'frontendtype', 'backendtype')
_AUTH_SENSITIVE_MARKERS = ('password', 'loginpassword', 'login_password', 'loginpwd', 'login_pwd', 'passwd', 'pwd', 'userpw', 'user_pw', 'passcode', 'passwordhash', 'password_hash', 'passwordsalt', 'password_salt', 'secretkey', 'secret_key', 'credential', 'credentials', 'pincode', 'pin_code', 'pinno', 'pin_no')
ENTRY_ONLY_CONTROLLER_DOMAINS = {"index", "home", "main", "landing", "root"}


def _ext_of(path: str) -> str:
    return Path(path).suffix.lower()


def _vite_mode(path: str, frontend_key: str = '') -> str:
    norm = path.replace('\\', '/')
    fk = (frontend_key or '').strip().lower()
    if '/frontend/vue/' in f'/{norm}' or fk == 'vue':
        return 'vue'
    if '/frontend/react/' in f'/{norm}' or fk == 'react':
        return 'react'
    return 'generic'





def _is_entry_redirect_only_controller(path: str, body: str) -> bool:
    norm = path.replace('\\', '/').lower()
    if not norm.endswith('controller.java'):
        return False
    stem = Path(path).stem
    stem = stem[:-10] if stem.endswith('Controller') else stem
    stem_key = stem.strip().lower()
    m = re.search(r"@RequestMapping\(\s*[\"']+/([a-zA-Z0-9_\-/]+)[\"']\s*\)", body)
    domain = (m.group(1).strip().split('/')[-1].lower() if m else stem_key)
    if domain not in ENTRY_ONLY_CONTROLLER_DOMAINS and stem_key not in ENTRY_ONLY_CONTROLLER_DOMAINS:
        return False
    returns = [item.strip().lower() for item in re.findall(r"return\s+[\"']([^\"']+)[\"']\s*;", body)]
    return bool(returns) and all(item.startswith('redirect:') or item.startswith('forward:') for item in returns)

def _controller_entity_var(path: str, body: str) -> str:
    stem = Path(path).stem
    for suffix in ("RestController", "Controller"):
        if stem.endswith(suffix) and len(stem) > len(suffix):
            base = stem[:-len(suffix)]
            break
    else:
        base = stem or "item"
    base = base[:1].lower() + base[1:] if base else "item"
    m = re.search(r"@RequestMapping\(\s*[\"']+/([a-zA-Z0-9_\-/]+)[\"']\s*\)", body)
    if m:
        seg = m.group(1).strip().split('/')[-1]
        if seg:
            return seg
    return base


def _calendar_controller_expected_view(path: str, body: str) -> str:
    ev = _controller_entity_var(path, body)
    return f'{ev}/{ev}Calendar'


def _validate_calendar_controller(path: str, body: str) -> Tuple[bool, str]:
    norm = path.replace('\\', '/').lower()
    lower = body.lower()
    if not norm.endswith('controller.java'):
        return True, ''
    has_calendar_mapping = '@getmapping("/calendar.do")' in lower or "@getmapping('/calendar.do')" in lower
    returns_calendar_view = re.search(r"return\s+[\"']+[a-z0-9_]+/[a-z0-9_]+calendar[\"']", lower) is not None
    is_schedule_controller = norm.endswith('/schedulecontroller.java') or '/schedule/' in norm
    if _is_entry_redirect_only_controller(path, body):
        return True, ''
    if not has_calendar_mapping and not returns_calendar_view and not is_schedule_controller:
        return True, ''
    if is_schedule_controller and ('@getmapping("/list.do")' in lower or "@getmapping('/list.do')" in lower):
        return False, 'schedule/calendar controller must not expose /list.do'
    if not has_calendar_mapping:
        return False, 'calendar-feature controller missing /calendar.do mapping'
    expected_view = _calendar_controller_expected_view(path, body)
    expected_view_lower = expected_view.lower()
    if f'return "{expected_view_lower}"' not in lower and f"return '{expected_view_lower}'" not in lower:
        return False, f'calendar-feature controller must return {expected_view} for main view'
    return True, ''




def _validate_boolean_getter_collisions(path: str, body: str) -> Tuple[bool, str]:
    norm = path.replace('\\', '/').lower()
    if not norm.endswith('.java') or not norm.endswith('vo.java') and '/service/vo/' not in norm:
        return True, ''
    for match in re.finditer(r'private\s+(Boolean|boolean)\s+(\w+)\s*;', body):
        prop = match.group(2)
        cap = prop[:1].upper() + prop[1:]
        has_get = re.search(rf'public\s+(?:Boolean|boolean)\s+get{re.escape(cap)}\s*\(', body)
        has_is = re.search(rf'public\s+(?:Boolean|boolean)\s+is{re.escape(cap)}\s*\(', body)
        if has_get and has_is:
            return False, f'ambiguous boolean getter pair detected for {prop}'
    return True, ''

def _validate_jsp_include_leaf_partials(path: str, body: str) -> Tuple[bool, str]:
    norm = path.replace('\\', '/').lower()
    include_re = re.compile(r'<%@\s*include\s+file\s*=\s*"([^"]+)"\s*%>', re.IGNORECASE)
    if norm.endswith('/web-inf/views/common/header.jsp') or norm.endswith('/web-inf/views/common/leftnav.jsp'):
        if include_re.search(body):
            return False, 'common partial jsp must not include other jsp files'
    if norm.endswith('/web-inf/views/_layout.jsp'):
        if include_re.search(body):
            return False, 'deprecated _layout.jsp must not include other jsp files'
    if norm.endswith('.jsp') and '/web-inf/views/' in norm and not (norm.endswith('/web-inf/views/common/header.jsp') or norm.endswith('/web-inf/views/common/leftnav.jsp') or norm.endswith('/web-inf/views/_layout.jsp')):
        lower = body.lower()
        if '/web-inf/views/_layout.jsp' in lower or '/web-inf/views/common/_layout.jsp' in lower:
            return False, 'jsp must not include deprecated _layout.jsp; include common/header.jsp and common/leftNav.jsp directly'
    return True, ''




def _auth_ui_path_tail(path: str) -> str:
    raw = str(path or '').replace('\\', '/')
    lower = raw.lower()
    for marker in ('/web-inf/views/', '/src/pages/', '/src/views/', '/frontend/react/src/', '/frontend/vue/src/'):
        idx = lower.find(marker)
        if idx >= 0:
            return raw[idx:]
    parts = [p for p in raw.split('/') if p]
    return '/'.join(parts[-5:]) if parts else raw


def _auth_ui_scan_tokens(path: str) -> set[str]:
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


def _is_auth_ui_path(path: str) -> bool:
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

def _looks_like_frontend_ui_path(path: str) -> bool:
    norm = path.replace('\\', '/').lower()
    if norm.endswith('.jsp'):
        return '/web-inf/views/' in norm
    if norm.endswith('.jsx') or norm.endswith('.vue'):
        return '/src/pages/' in norm or '/src/views/' in norm or norm.endswith('/app.vue')
    return False


def _strip_non_rendered_markup_for_ui_scan(body: str) -> str:
    if not body:
        return ''
    cleaned = re.sub(r'<%--.*?--%>', ' ', body, flags=re.DOTALL)
    cleaned = re.sub(r'<!--.*?-->', ' ', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'/\*.*?\*/', ' ', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'(?m)//.*$', ' ', cleaned)
    return cleaned


def _validate_auth_sensitive_ui_exposure(path: str, body: str) -> Tuple[bool, str]:
    norm = path.replace('\\', '/').lower()
    if not _looks_like_frontend_ui_path(norm) or allows_auth_sensitive_in_account_form(path, body):
        return True, ''
    low = _strip_non_rendered_markup_for_ui_scan(body).lower()
    if any(marker in low for marker in _AUTH_SENSITIVE_MARKERS):
        return False, 'non-auth UI must not expose auth-sensitive fields such as password/login_password'
    return True, ''


def _validate_generation_metadata_ui_exposure(path: str, body: str) -> Tuple[bool, str]:
    norm = path.replace('\\', '/').lower()
    if not _looks_like_frontend_ui_path(norm) or _is_auth_ui_path(path):
        return True, ''
    low = _strip_non_rendered_markup_for_ui_scan(body).lower()
    for marker in _GENERATION_METADATA_MARKERS:
        marker_pat = re.escape(marker)
        patterns = [
            rf"(?i)(?:name|id|for|path|items|value|data-field|data-name)\s*=\s*[\"']*[^\"']*{marker_pat}[^\"']*[\"']",
            rf'(?i)\$\{{[^}}]*{marker_pat}[^}}]*\}}',
            rf'(?i)#\{{[^}}]*{marker_pat}[^}}]*\}}',
            rf'(?i)<(?:th|td|label|span|div|p|option|li|dt|dd|strong|em|small|button)[^>]*>[^<]*\b{marker_pat}\b[^<]*<',
        ]
        if any(re.search(pat, low) for pat in patterns):
            return False, 'non-auth UI must not expose generation metadata fields such as db/schemaName/tableName/packageName'
    return True, ''



def _validate_schedule_jsp(path: str, body: str) -> Tuple[bool, str]:
    norm = path.replace('\\', '/').lower()
    lower = body.lower()
    if not norm.endswith('.jsp') or '/schedule/' not in norm:
        return True, ''
    if '/web-inf/views/_layout.jsp' in lower or '/web-inf/views/common/_layout.jsp' in lower:
        return False, 'schedule jsp must not include missing _layout.jsp; use common/header.jsp'
    if norm.endswith('schedulecalendar.jsp'):
        if '/web-inf/views/common/header.jsp' in lower:
            return True, ''
        # header include is strongly recommended but not fatal at single-file stage
    return True, ''


def validate_generated_content(path: str, content: str, frontend_key: str = '') -> Tuple[bool, str]:
    ext = _ext_of(path)
    norm = path.replace('\\', '/')
    c = content or ''
    body = c.strip()

    if not body:
        return False, 'empty content'

    if '@function(' in body or '$check' in body or 'korius(' in body:
        return False, 'content looks like non-code script (garbage signature)'

    if ext == '.java':
        name = Path(path).stem
        if body.lstrip().startswith('// path:'):
            body = '\n'.join(body.splitlines()[1:]).strip()
        if not re.search(r'(?m)^\s*package\s+[\w\.]+\s*;', body):
            return False, "missing 'package ...;' in Java file"
        if not re.search(rf'\b(class|interface|enum)\s+{re.escape(name)}\b', body):
            return False, f"missing type declaration for '{name}'"
        ok, reason = _validate_calendar_controller(path, body)
        if not ok:
            return ok, reason
        ok, reason = _validate_boolean_getter_collisions(path, body)
        if not ok:
            return ok, reason
        return True, ''

    ok, reason = _validate_jsp_include_leaf_partials(path, body)
    if not ok:
        return ok, reason

    ok, reason = _validate_auth_sensitive_ui_exposure(path, body)
    if not ok:
        return ok, reason

    ok, reason = _validate_generation_metadata_ui_exposure(path, body)
    if not ok:
        return ok, reason

    if ext == '.json':
        try:
            parsed = json.loads(body)
            if not isinstance(parsed, (dict, list)):
                return False, 'json root must be object or array'
        except Exception as e:
            return False, f'invalid json: {e}'
        if norm.endswith('frontend/vue/package.json') or (_vite_mode(norm, frontend_key) == 'vue' and norm.endswith('package.json')):
            if not isinstance(parsed, dict):
                return False, 'package.json root must be object'
            scripts = parsed.get('scripts') or {}
            deps = parsed.get('dependencies') or {}
            dev_deps = parsed.get('devDependencies') or {}
            if scripts.get('dev') != 'vite' or scripts.get('build') != 'vite build' or scripts.get('preview') != 'vite preview':
                return False, 'Vue package.json missing Vite scripts'
            if 'vue' not in deps or 'vue-router' not in deps:
                return False, 'Vue package.json missing runtime dependencies'
            if 'vite' not in dev_deps or '@vitejs/plugin-vue' not in dev_deps:
                return False, 'Vue package.json missing Vite devDependencies'
        return True, ''

    if norm.endswith('vite.config.js'):
        mode = _vite_mode(norm, frontend_key)
        if 'defineConfig' not in body:
            return False, 'vite.config.js missing defineConfig'
        if re.search(r'(?m)^\s*import\s+.*?from\s+["\']vite-proxy["\']', body):
            return False, "vite.config.js imports unsupported package 'vite-proxy'"
        if mode == 'react':
            if '@vitejs/plugin-react' not in body:
                return False, 'vite.config.js missing React Vite configuration'
            allowed_imports = {'vite', '@vitejs/plugin-react', 'node:path'}
        elif mode == 'vue':
            if '@vitejs/plugin-vue' not in body:
                return False, 'vite.config.js missing Vue Vite configuration'
            allowed_imports = {'vite', '@vitejs/plugin-vue', 'node:path'}
        else:
            if '@vitejs/plugin-react' not in body and '@vitejs/plugin-vue' not in body:
                return False, 'vite.config.js missing supported Vite plugin configuration'
            allowed_imports = {'vite', '@vitejs/plugin-react', '@vitejs/plugin-vue', 'node:path'}
        for m in re.finditer(r'(?m)^\s*import\s+.*?from\s+["\']([^"\']+)["\']', body):
            mod = m.group(1).strip()
            if mod.startswith('.') or mod.startswith('/') or mod.startswith('@/'):
                continue
            if mod not in allowed_imports:
                return False, f"vite.config.js imports unsupported package '{mod}'"
        return True, ''

    if norm.endswith('index.html'):
        mode = _vite_mode(norm, frontend_key)
        if '<!doctype html' not in body.lower() and '<html' not in body.lower():
            return False, 'index.html missing html shell'
        if 'type="module"' not in body and "type='module'" not in body:
            return False, 'index.html missing module script'
        if mode == 'react':
            if '<div id="root"></div>' not in body and "<div id='root'></div>" not in body:
                return False, 'React index.html missing root mount node'
            if '/src/main.jsx' not in body:
                return False, 'React index.html missing /src/main.jsx entry'
        elif mode == 'vue':
            if '<div id="app"></div>' not in body and "<div id='app'></div>" not in body:
                return False, 'Vue index.html missing app mount node'
            if '/src/main.js' not in body:
                return False, 'Vue index.html missing /src/main.js entry'
        return True, ''

    if norm.endswith('src/main.jsx'):
        if 'ReactDOM.createRoot' not in body or ('import App from "./App"' not in body and "import App from './App'" not in body):
            return False, 'src/main.jsx missing React bootstrap'
        return True, ''

    if norm.endswith('src/main.js') and (_vite_mode(norm, frontend_key) == 'vue' or '/frontend/vue/' in f'/{norm}'):
        if 'createApp' not in body or ('import App from "./App.vue"' not in body and "import App from './App.vue'" not in body):
            return False, 'src/main.js missing Vue bootstrap'
        if 'pinia' in body.lower() or 'createpinia' in body.lower():
            return False, 'src/main.js imports unsupported pinia runtime'
        if 'mount("#app")' not in body and "mount('#app')" not in body:
            return False, 'src/main.js missing #app mount'
        return True, ''

    if norm.endswith('src/App.jsx'):
        if 'export default function App' not in body and 'const App' not in body:
            return False, 'src/App.jsx missing App component'
        return True, ''

    if norm.endswith('src/App.vue'):
        if '<template' not in body:
            return False, 'src/App.vue missing template'
        if '<router-view' not in body:
            return False, 'src/App.vue missing router-view'
        if any(token in body for token in ('Home', 'About', 'HelloWorld', 'TheWelcome')):
            return False, 'src/App.vue still contains Vue sample content'
        return True, ''

    if norm.endswith('src/router/index.js') and (_vite_mode(norm, frontend_key) == 'vue' or '/frontend/vue/' in f'/{norm}'):
        if 'createRouter' not in body or 'createWebHistory' not in body or 'export default' not in body:
            return False, 'src/router/index.js missing Vue router bootstrap'
        if '/list' not in body and 'redirect:' not in body:
            return False, 'src/router/index.js missing CRUD list route or redirect'
        return True, ''

    if ext in ('.xml', '.jsp', '.html', '.vue'):
        if '<' not in body or '>' not in body:
            return False, 'markup file missing tags'
        ok, reason = _validate_schedule_jsp(path, body)
        if not ok:
            return ok, reason
        return True, ''

    return True, ''
