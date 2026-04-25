from __future__ import annotations
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from app.io.file_writer import apply_file_ops
from app.ui.generated_content_validator import validate_generated_content
from app.ui.java_import_fixer import fix_project_java_imports
from app.ui.template_generator import (
    render_application_properties,
    render_maven_wrapper_properties,
    render_mvnw,
    render_mvnw_cmd,
    render_pom_xml,
)
from execution_core.project_patcher import detect_boot_base_package, patch_boot_application, _find_boot_applications
from app.validation.compile_error_parser import compile_error_paths, summarize_compile_errors
from app.ui.fallback_builder import build_builtin_fallback_content
RegenCallback = Callable[[str, str, str, str], Optional[Dict[str, Any]]]
_BUILD_TEMPLATE_TARGETS = {
    'pom.xml',
    'mvnw',
    'mvnw.cmd',
    '.mvn/wrapper/maven-wrapper.properties',
    'src/main/resources/application.properties',
}
_STARTUP_CLASS_RE = re.compile(r'defined in file \[(?P<path>[^\]]+target[\/]+classes[\/][^\]]+?\.class)\]', re.IGNORECASE)
_UNRESOLVED_RE = re.compile(r'Unresolved compilation problems?', re.IGNORECASE)
_LAYER_MARKERS = ('web', 'service', 'impl', 'domain', 'persistence', 'repository', 'mapper', 'api')
_CLASS_SUFFIXES = ('Controller', 'ServiceImpl', 'Service', 'VO', 'Mapper', 'Repository', 'Entity')
_VIEW_SUFFIXES = ('List', 'Form', 'View', 'Detail', 'Calendar', 'Edit', 'Create')

_BOOT_APP_CLASS = 'EgovBootApplication'
_BOOT_APP_ILLEGAL_SUFFIXES = ('Controller.java', 'ServiceImpl.java', 'Service.java', 'Mapper.java', 'VO.java', 'Mapper.xml', 'List.jsp', 'Detail.jsp', 'Form.jsp', 'Calendar.jsp', 'View.jsp', 'Edit.jsp')

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


def _is_illegal_infra_artifact(rel: str) -> bool:
    norm = _normalize(rel)
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


def _remove_illegal_infra_artifacts(project_root: Path) -> List[str]:
    root = Path(project_root)
    removed: List[str] = []
    for base in ('src/main/java', 'src/main/resources', 'src/main/webapp/WEB-INF/views'):
        probe = root / base
        if not probe.exists():
            continue
        for candidate in probe.rglob('*'):
            if not candidate.is_file():
                continue
            rel = candidate.relative_to(root).as_posix()
            if not _is_illegal_infra_artifact(rel):
                continue
            try:
                candidate.unlink()
                removed.append(rel)
            except Exception:
                pass
    target_root = root / 'target/classes'
    if target_root.exists():
        for name in ('AuthenticInterceptor.class', 'AuthInterceptor.class', 'WebConfig.class', 'WebConfigMapper.class', 'WebConfigService.class', 'WebConfigServiceImpl.class', 'AuthLoginInterceptorMapper.class', 'AuthenticInterceptorMapper.class', 'AuthInterceptorMapper.class', 'AuthInterceptorService.class', 'AuthInterceptorServiceImpl.class'):
            for candidate in target_root.rglob(name):
                try:
                    candidate.unlink()
                except Exception:
                    pass
    return removed

def _is_boot_crud_target(rel: str) -> bool:
    norm = _normalize(rel)
    name = Path(norm).name
    if name == f'{_BOOT_APP_CLASS}.java':
        return False
    return any(name == f'{_BOOT_APP_CLASS}{suffix}' for suffix in _BOOT_APP_ILLEGAL_SUFFIXES)


def _remove_boot_crud_artifacts(project_root: Path) -> List[str]:
    root = Path(project_root)
    removed: List[str] = []
    seen = set()
    patterns = [
        f'src/main/java/**/{_BOOT_APP_CLASS}Service.java',
        f'src/main/java/**/{_BOOT_APP_CLASS}ServiceImpl.java',
        f'src/main/java/**/{_BOOT_APP_CLASS}Mapper.java',
        f'src/main/java/**/{_BOOT_APP_CLASS}VO.java',
        f'src/main/java/**/{_BOOT_APP_CLASS}Controller.java',
        f'src/main/resources/**/{_BOOT_APP_CLASS}Mapper.xml',
        f'src/main/webapp/WEB-INF/views/**/{_BOOT_APP_CLASS}List.jsp',
        f'src/main/webapp/WEB-INF/views/**/{_BOOT_APP_CLASS}Detail.jsp',
        f'src/main/webapp/WEB-INF/views/**/{_BOOT_APP_CLASS}Form.jsp',
        f'src/main/webapp/WEB-INF/views/**/{_BOOT_APP_CLASS}Calendar.jsp',
    ]
    for pattern in patterns:
        for candidate in root.glob(pattern):
            if not candidate.is_file():
                continue
            rel = str(candidate.relative_to(root)).replace('\\', '/')
            if rel in seen:
                continue
            seen.add(rel)
            try:
                candidate.unlink()
                removed.append(rel)
            except Exception:
                pass
    target_root = root / 'target/classes'
    if target_root.exists():
        for candidate in target_root.rglob(f'{_BOOT_APP_CLASS}*.class'):
            if candidate.name == f'{_BOOT_APP_CLASS}.class':
                continue
            try:
                candidate.unlink()
            except Exception:
                pass
    return removed



_JAVA_KEYWORDS = {
    "abstract","assert","boolean","break","byte","case","catch","char","class","const","continue","default","do","double","else","enum","extends","final","finally","float","for","goto","if","implements","import","instanceof","int","interface","long","native","new","package","private","protected","public","return","short","static","strictfp","super","switch","synchronized","this","throw","throws","transient","try","void","volatile","while","true","false","null","record","sealed","permits","var","yield"
}

def _sanitize_java_package_segment(token: str) -> str:
    raw = re.sub(r"[^A-Za-z0-9_]+", "", (token or "").strip())
    if not raw:
        return "app"
    seg = raw[:1].lower() + raw[1:]
    seg = re.sub(r"^[^A-Za-z_]+", "", seg)
    if not seg:
        return "app"
    if seg in _JAVA_KEYWORDS:
        return f"{seg}_"
    return seg

def _replace_pkg_token(body: str, old_pkg: str, new_pkg: str) -> str:
    if not body or old_pkg == new_pkg:
        return body
    body = body.replace(old_pkg + ".", new_pkg + ".")
    body = body.replace(old_pkg + ";", new_pkg + ";")
    body = body.replace(old_pkg + '"', new_pkg + '"')
    body = body.replace(old_pkg + "'", new_pkg + "'")
    body = body.replace(old_pkg.replace('.', '/'), new_pkg.replace('.', '/'))
    return body

def _replace_reserved_pkg_segments(body: str) -> str:
    if not body:
        return body
    for keyword in sorted(_JAVA_KEYWORDS):
        body = body.replace(f'.{keyword}.', f'.{keyword}_.')
        body = body.replace(f'/{keyword}/', f'/{keyword}_/')
    return body

def _relocate_reserved_java_package_segments(root: Path) -> List[str]:
    changes: List[str] = []
    java_root = root / 'src/main/java'
    if not java_root.exists():
        return changes
    mappings: Dict[str, str] = {}
    java_files = sorted(java_root.rglob('*.java'))
    for path in java_files:
        body = _read_text(path)
        m = re.search(r'package\s+([A-Za-z0-9_.]+)\s*;', body)
        if not m:
            continue
        pkg = (m.group(1) or '').strip()
        parts = [p for p in pkg.split('.') if p]
        sanitized = [_sanitize_java_package_segment(part) for part in parts]
        new_pkg = '.'.join(sanitized)
        if new_pkg != pkg:
            mappings[pkg] = new_pkg
    if not mappings:
        return changes
    text_exts = {'.java', '.xml', '.jsp', '.properties', '.yml', '.yaml', '.sql'}
    for file_path in sorted(root.rglob('*')):
        if not file_path.is_file() or file_path.suffix.lower() not in text_exts:
            continue
        body = _read_text(file_path)
        updated = body
        for old_pkg, new_pkg in mappings.items():
            updated = _replace_pkg_token(updated, old_pkg, new_pkg)
        updated = _replace_reserved_pkg_segments(updated)
        if updated != body:
            file_path.write_text(updated, encoding='utf-8')
            try:
                changes.append(file_path.relative_to(root).as_posix())
            except Exception:
                changes.append(str(file_path).replace('\\', '/'))
    for path in java_files:
        if not path.exists():
            continue
        body = _read_text(path)
        m = re.search(r'package\s+([A-Za-z0-9_.]+)\s*;', body)
        if not m:
            continue
        pkg = (m.group(1) or '').strip()
        rel_dir = pkg.replace('.', '/')
        new_path = java_root / rel_dir / path.name
        if new_path == path:
            continue
        new_path.parent.mkdir(parents=True, exist_ok=True)
        if new_path.exists():
            new_path.unlink()
        path.rename(new_path)
        try:
            changes.append(new_path.relative_to(root).as_posix())
        except Exception:
            changes.append(str(new_path).replace('\\', '/'))
        # clean empty parents under java root
        parent = path.parent
        while parent != java_root and parent.exists():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    dedup=[]; seen=set()
    for c in changes:
        if c in seen:
            continue
        seen.add(c)
        dedup.append(c)
    return dedup
def _align_java_public_type_to_filename(path: Path) -> bool:
    if not path.exists() or path.suffix != '.java':
        return False
    body = _read_text(path)
    m = re.search(r'\bpublic\s+(class|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)\b', body)
    if not m:
        return False
    expected = path.stem
    actual = m.group(2)
    if actual == expected:
        return False
    updated = body.replace(f'public {m.group(1)} {actual}', f'public {m.group(1)} {expected}', 1)
    updated = re.sub(rf'\b{re.escape(actual)}\s*\(', f'{expected}(', updated)
    if updated == body:
        return False
    path.write_text(updated, encoding='utf-8')
    return True

def enforce_generated_project_invariants(project_root: Path) -> Dict[str, Any]:
    root = Path(project_root)
    changed: List[Dict[str, Any]] = []
    for rel in _remove_illegal_infra_artifacts(root):
        changed.append({'path': rel, 'reason': 'invalid infra artifact removed'})
    for rel in _remove_boot_crud_artifacts(root):
        changed.append({'path': rel, 'reason': 'invalid boot crud artifact removed'})
    for rel in _relocate_reserved_java_package_segments(root):
        changed.append({'path': rel, 'reason': 'reserved java package segment sanitized'})
    java_root = root / 'src/main/java'
    if java_root.exists():
        for path in sorted(java_root.rglob('*.java')):
            try:
                rel = path.relative_to(root).as_posix()
            except Exception:
                rel = str(path).replace('\\', '/')
            if _is_boot_crud_target(rel) or _is_illegal_infra_artifact(rel):
                continue
            if _align_java_public_type_to_filename(path):
                changed.append({'path': rel, 'reason': 'public type aligned to filename'})
    boot_base = (detect_boot_base_package(root) or '').strip()
    if not boot_base:
        boot_apps = _find_boot_applications(root)
        if boot_apps:
            boot_base = str(boot_apps[0][1] or '').strip()
        if not boot_base and java_root.exists():
            for java_file in sorted(java_root.rglob('*.java')):
                body = _read_text(java_file)
                pkg_m = re.search(r'^\s*package\s+([A-Za-z0-9_.]+)\s*;', body, re.MULTILINE)
                pkg = (pkg_m.group(1).strip() if pkg_m else '')
                if pkg.startswith('egovframework.'):
                    parts = [part for part in pkg.split('.') if part]
                    boot_base = '.'.join(parts[:2]) if len(parts) >= 2 else pkg
                    break
    if boot_base:
        boot_path = patch_boot_application(root, boot_base, _BOOT_APP_CLASS)
        try:
            boot_rel = boot_path.relative_to(root).as_posix()
        except Exception:
            boot_rel = str(boot_path).replace('\\', '/')
        changed.append({'path': boot_rel, 'reason': 'boot application canonicalized'})
    dedup: List[Dict[str, Any]] = []
    seen = set()
    for item in changed:
        key = (str(item.get('path') or ''), str(item.get('reason') or ''))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(item)
    return {'changed': dedup, 'changed_count': len(dedup)}

def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except Exception:
        return path.read_text(encoding='utf-8', errors='ignore')
def _is_entry_controller_target(rel: str) -> bool:
    norm = _normalize(rel).lower()
    name = Path(norm).name
    return name in {'indexcontroller.java', 'homecontroller.java', 'maincontroller.java'} or '/index/web/' in norm or '/home/web/' in norm or '/main/web/' in norm
def _pick_entry_redirect_route(project_root: Path) -> str:
    java_root = Path(project_root) / 'src/main/java'
    preferred: List[str] = []
    if java_root.exists():
        for controller in java_root.rglob('*Controller.java'):
            rel = str(controller.relative_to(project_root)).replace('\\', '/').lower()
            if _is_entry_controller_target(rel):
                continue
            body = _read_text(controller)
            prefix_match = re.search(r"@RequestMapping\(\s*[\"'](/[^\"']*)[\"']\s*\)", body)
            base = (prefix_match.group(1).strip() if prefix_match else '') or '/'
            for route in re.findall(r"@GetMapping\(\s*[\"']([^\"']+)[\"']\s*\)", body):
                route = (route or '').strip()
                if not route:
                    continue
                full = route if route.startswith('/') else '/' + route
                if base and base != '/':
                    full = (base.rstrip('/') + '/' + full.lstrip('/'))
                low = full.lower()
                if '{' in full or '}' in full or any(token in low for token in ('delete', 'remove', 'save', 'update', 'create')):
                    continue
                preferred.append(full)
            for route in re.findall(r"return\s+[\"']redirect:([^\"']+)[\"']", body):
                route = (route or '').strip()
                if route and route not in {'/', '/index.do'}:
                    preferred.append(route if route.startswith('/') else '/' + route)
    ordered: List[str] = []
    for token in ('/calendar.do', '/list.do', '/dashboard', '/main', '/login'):
        for route in preferred:
            if token in route.lower() and route not in ordered:
                ordered.append(route)
    for route in preferred:
        if route not in ordered:
            ordered.append(route)
    for route in ordered:
        if route not in {'/', '/index.do'}:
            return route
    return '/'
def _rewrite_entry_controller(project_root: Path, rel: str) -> bool:
    path = Path(project_root) / _normalize(rel)
    if not path.exists():
        return False
    body = _read_text(path)
    match = re.search(r'package\s+([A-Za-z0-9_.]+)\s*;', body)
    package_name = match.group(1) if match else 'egovframework.app.index.web'
    route = _pick_entry_redirect_route(Path(project_root))
    class_name = path.stem
    desired = f'''package {package_name};
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
@Controller
public class {class_name} {{
    @GetMapping({{"/", "/index.do"}})
    public String index() {{
        return "redirect:{route}";
    }}
}}
'''
    if body.strip() == desired.strip():
        return False
    path.write_text(desired, encoding='utf-8')
    return True
def _compile_error_items_for_target(errors: List[Dict[str, Any]], rel: str) -> List[Dict[str, Any]]:
    norm = _normalize(rel)
    items: List[Dict[str, Any]] = []
    for item in errors or []:
        path = _normalize(str((item or {}).get('path') or ''))
        if path == norm:
            items.append(item)
    return items


def _guess_mapper_param_signature(arg_expr: str, dao_param_block: str, vo_type: str) -> str:
    arg = (arg_expr or '').strip()
    dao_params = (dao_param_block or '').strip()
    if not arg or arg in {'new LinkedHashMap<>()', 'new HashMap<>()'} or 'LinkedHashMap' in arg or 'HashMap' in arg or 'params' in arg:
        return 'Map<String, Object> params'
    if dao_params:
        cleaned = re.sub(r'@Param\([^)]*\)\s*', '', dao_params).strip()
        if ',' not in cleaned and cleaned:
            parts = cleaned.split()
            if len(parts) >= 2:
                ptype = ' '.join(parts[:-1])
                pname = parts[-1]
                if pname in arg or arg == pname:
                    if vo_type and pname == 'vo':
                        return f'{vo_type} vo'
                    return f'@Param("{pname}") {ptype} {pname}'
    if arg == 'vo' and vo_type:
        return f'{vo_type} vo'
    if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', arg):
        return f'@Param("{arg}") String {arg}'
    return 'Map<String, Object> params'




def _method_signature_key(method_name: str, param_sig: str) -> tuple[str, int]:
    cleaned = re.sub(r'@Param\([^)]*\)\s*', '', (param_sig or '')).strip()
    if not cleaned:
        return (method_name, 0)
    parts = [part for part in cleaned.split(',') if part.strip()]
    return (method_name, len(parts))


def _existing_mapper_signature_keys(mapper_body: str) -> set[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    for m in re.finditer(r'\b[A-Za-z_][A-Za-z0-9_<> ,]*\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*;', mapper_body):
        name = m.group(1)
        params = m.group(2)
        if name in {'if','for','while','switch'}:
            continue
        keys.add(_method_signature_key(name, params))
    return keys

def _ensure_dao_mapper_method_alignment(project_root: Path, rel: str) -> List[Dict[str, Any]]:
    norm = _normalize(rel)
    if not norm.endswith('DAO.java'):
        return []
    dao_path = Path(project_root) / norm
    if not dao_path.exists():
        return []
    dao_body = _read_text(dao_path)
    mapper_field_match = re.search(r'private\s+final\s+([A-Za-z_][A-Za-z0-9_]*)\s+([A-Za-z_][A-Za-z0-9_]*)\s*;', dao_body)
    if not mapper_field_match:
        return []
    mapper_type = mapper_field_match.group(1)
    mapper_var = mapper_field_match.group(2)
    mapper_rel = norm.replace('/service/impl/', '/service/mapper/').replace('DAO.java', 'Mapper.java')
    mapper_path = Path(project_root) / mapper_rel
    if not mapper_path.exists():
        return []
    mapper_body = _read_text(mapper_path)
    if f'interface {mapper_type}' not in mapper_body:
        return []
    vo_import_match = re.search(r'import\s+([A-Za-z0-9_.]+\.([A-Za-z_][A-Za-z0-9_]*VO))\s*;', mapper_body)
    vo_type = vo_import_match.group(2) if vo_import_match else ''
    method_calls = re.findall(rf'\b{re.escape(mapper_var)}\.([A-Za-z_][A-Za-z0-9_]*)\((.*?)\)', dao_body, flags=re.DOTALL)
    if not method_calls:
        return []
    existing = _existing_mapper_signature_keys(mapper_body)
    additions: List[str] = []
    for method_name, arg_expr in method_calls:
        if method_name in {'if', 'for', 'while', 'switch'}:
            continue
        wrapper = re.search(
            rf'public\s+([^\{{;]+?)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)\s*throws\s+Exception\s*\{{[^\{{}}]*?\b{re.escape(mapper_var)}\.{re.escape(method_name)}\((.*?)\)\s*;\s*\}}',
            dao_body,
            flags=re.DOTALL,
        )
        return_type = 'int'
        dao_params = ''
        call_arg_expr = arg_expr
        if wrapper:
            return_type = ' '.join(wrapper.group(1).split())
            dao_params = ' '.join((wrapper.group(3) or '').split())
            call_arg_expr = wrapper.group(4)
        param_sig = _guess_mapper_param_signature(call_arg_expr, dao_params, vo_type)
        sig_key = _method_signature_key(method_name, param_sig)
        if sig_key in existing:
            continue
        additions.append(f'    {return_type} {method_name}({param_sig});')
        existing.add(sig_key)
    if not additions:
        return []
    updated = mapper_body
    insert_at = updated.rfind('}')
    if insert_at == -1:
        return []
    block = '\n' + '\n'.join(additions) + '\n'
    updated = updated[:insert_at].rstrip() + block + updated[insert_at:]
    if updated == mapper_body:
        return []
    mapper_path.write_text(updated, encoding='utf-8')
    return [{'path': mapper_rel, 'reason': 'dao/mapper method contract aligned from dao usage'}]


def _has_vo_syntax_failure(errors: List[Dict[str, Any]], rel: str) -> bool:
    norm = _normalize(rel)
    if not norm.endswith('VO.java'):
        return False
    for item in _compile_error_items_for_target(errors, norm):
        message = str((item or {}).get('message') or (item or {}).get('snippet') or '').lower()
        if '<identifier> expected' in message or 'illegal start of type' in message:
            return True
    return False




def _infra_companion_targets(rel: str) -> List[str]:
    norm = _normalize(rel)
    path = Path(norm)
    name = path.name
    parent = path.parent.as_posix()
    if name in {'WebMvcConfig.java', 'WebConfig.java'} and parent.endswith('/config'):
        return [f'{parent}/AuthLoginInterceptor.java']
    if name == 'AuthLoginInterceptor.java' and parent.endswith('/config'):
        return [f'{parent}/WebMvcConfig.java']
    return []

def _expected_contract_bundle_targets(rel: str) -> List[str]:
    norm = _normalize(rel)
    info = _infer_related_context(norm)
    domain = (info.get('domain') or '').strip()
    stem = (info.get('stem') or '').strip()
    if not stem:
        name = Path(norm).name
        stem = name
        for suffix in ('ServiceImpl.java', 'Service.java', 'Mapper.java', 'Mapper.xml', 'Controller.java', 'VO.java'):
            if stem.endswith(suffix):
                stem = stem[:-len(suffix)]
                break
    if not stem:
        return [norm] if norm else []
    if _is_boot_crud_target(norm) or _is_illegal_infra_artifact(norm) or stem == _BOOT_APP_CLASS:
        return []
    candidates: List[str] = []
    candidates.extend(_infra_companion_targets(norm))
    if norm.startswith('src/main/java/'):
        parts = list(Path(norm).parts)
        pkg_parts = list(parts[3:-1])
        base_parts = pkg_parts
        for idx, token in enumerate(pkg_parts):
            if token in _LAYER_MARKERS:
                base_parts = pkg_parts[:idx]
                if not domain and idx > 0:
                    domain = pkg_parts[idx - 1]
                break
        java_base = Path('src/main/java').joinpath(*base_parts) if base_parts else Path('src/main/java')
        candidates.extend([
            str((java_base / 'service' / f'{stem}Service.java').as_posix()),
            str((java_base / 'service' / 'impl' / f'{stem}ServiceImpl.java').as_posix()),
            str((java_base / 'service' / 'impl' / f'{stem}DAO.java').as_posix()),
            str((java_base / 'service' / 'mapper' / f'{stem}Mapper.java').as_posix()),
            str((java_base / 'service' / 'vo' / f'{stem}VO.java').as_posix()),
            str((java_base / 'web' / f'{stem}Controller.java').as_posix()),
        ])
    domain_seg = (domain or (stem[:1].lower() + stem[1:] if stem else '')).strip()
    if domain_seg:
        candidates.extend([
            f'src/main/resources/egovframework/mapper/{domain_seg}/{stem}Mapper.xml',
            f'src/main/webapp/WEB-INF/views/{domain_seg}/{domain_seg}List.jsp',
            f'src/main/webapp/WEB-INF/views/{domain_seg}/{domain_seg}Form.jsp',
            f'src/main/webapp/WEB-INF/views/{domain_seg}/{domain_seg}Detail.jsp',
            f'src/main/webapp/WEB-INF/views/{domain_seg}/{domain_seg}Calendar.jsp',
        ])
    ordered: List[str] = []
    seen = set()
    for item in [norm] + candidates:
        item = _normalize(item)
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _contract_bundle_targets(project_root: Path, rel: str) -> List[str]:
    norm = _normalize(rel)
    path = Path(norm)
    name = path.name
    stem = name
    for suffix in ('ServiceImpl.java', 'Service.java', 'Mapper.java', 'Mapper.xml', 'Controller.java', 'VO.java'):
        if stem.endswith(suffix):
            stem = stem[:-len(suffix)]
            break
    if not stem:
        return [norm]
    if _is_boot_crud_target(norm) or _is_illegal_infra_artifact(norm) or stem == _BOOT_APP_CLASS:
        return []
    results: List[str] = []
    results.extend(_infra_companion_targets(norm))
    root = Path(project_root)
    patterns = [
        f'src/main/java/**/{stem}Service.java',
        f'src/main/java/**/{stem}ServiceImpl.java',
        f'src/main/java/**/{stem}DAO.java',
        f'src/main/java/**/{stem}Mapper.java',
        f'src/main/java/**/{stem}VO.java',
        f'src/main/java/**/{stem}Controller.java',
        f'src/main/resources/**/{stem}Mapper.xml',
    ]
    for pattern in patterns:
        for candidate in root.glob(pattern):
            if candidate.is_file():
                results.append(str(candidate.relative_to(root)).replace('\\', '/'))

    domain_guess = stem[:1].lower() + stem[1:] if stem else ''
    if domain_guess:
        view_root = root / 'src/main/webapp/WEB-INF/views' / domain_guess
        if view_root.exists():
            for view_name in (f'{domain_guess}List.jsp', f'{domain_guess}Form.jsp', f'{domain_guess}Detail.jsp', f'{domain_guess}Calendar.jsp'):
                candidate = view_root / view_name
                if candidate.is_file():
                    results.append(str(candidate.relative_to(root)).replace('\\', '/'))
    for expected in _expected_contract_bundle_targets(norm):
        if expected not in results:
            results.append(expected)
    if norm not in results:
        results.insert(0, norm)
    dedup: List[str] = []
    seen = set()
    for item in results:
        if item not in seen:
            seen.add(item)
            dedup.append(item)
    return dedup

def _guess_boot_base_package(project_root: Path, cfg: Any) -> str:
    detected = (detect_boot_base_package(project_root) or '').strip()
    if detected:
        return detected
    java_root = project_root / 'src/main/java'
    if java_root.exists():
        for java_file in sorted(java_root.rglob('*.java')):
            body = _read_text(java_file)
            pkg_m = re.search(r'^\s*package\s+([A-Za-z0-9_.]+)\s*;', body, re.MULTILINE)
            pkg = (pkg_m.group(1).strip() if pkg_m else '')
            if pkg.startswith('egovframework.'):
                parts = [part for part in pkg.split('.') if part]
                if len(parts) >= 2:
                    return '.'.join(parts[:2])
                return pkg
    project_name = str(getattr(cfg, 'project_name', '') or '').strip().lower() or 'app'
    project_name = re.sub(r'[^a-z0-9_]+', '', project_name) or 'app'
    return f'egovframework.{project_name}'


def _local_contract_repair(project_root: Path, cfg: Any, manifest: Dict[str, Dict[str, Any]], targets: List[str], runtime_report: Dict[str, Any]) -> List[Dict[str, Any]]:
    changed: List[Dict[str, Any]] = []
    changed.extend(enforce_generated_project_invariants(project_root).get('changed') or [])
    errors = ((runtime_report or {}).get('compile') or {}).get('errors') or []
    override_like = any((item.get('code') or '') in {'override_mismatch', 'cannot_find_symbol', 'package_missing'} for item in errors)
    bundle_targets = list(targets)
    for rel in list(targets):
        syntax_broken_vo = _has_vo_syntax_failure(errors, rel)
        if override_like or syntax_broken_vo or any(rel.endswith(suffix) for suffix in ('Controller.java', 'ServiceImpl.java', 'Service.java', 'Mapper.java', 'Mapper.xml', 'VO.java')):
            for extra in _contract_bundle_targets(project_root, rel):
                if extra not in bundle_targets:
                    bundle_targets.append(extra)
    bundle_specs: List[str] = []
    for rel in bundle_targets:
        norm = _normalize(rel)
        abs_path = Path(project_root) / norm
        syntax_broken_vo = _has_vo_syntax_failure(errors, norm)
        manifest_meta = (manifest or {}).get(norm) or {}
        if syntax_broken_vo:
            spec_text = str(manifest_meta.get('spec') or '')
        else:
            meta = _manifest_meta_for_target(project_root, manifest, norm) or {}
            spec_text = str(meta.get('spec') or (_read_text(abs_path) if abs_path.exists() and abs_path.is_file() else ''))
        if spec_text.strip():
            bundle_specs.append(spec_text)
    shared_bundle_spec = '\n'.join(bundle_specs)
    for rel in bundle_targets:
        norm = _normalize(rel)
        abs_path = Path(project_root) / norm
        if Path(norm).name == f'{_BOOT_APP_CLASS}.java':
            boot_base = _guess_boot_base_package(Path(project_root), cfg)
            boot_path = patch_boot_application(Path(project_root), boot_base, _BOOT_APP_CLASS)
            try:
                changed.append({'path': boot_path.relative_to(project_root).as_posix(), 'reason': 'boot application canonicalized after compile failure'})
            except Exception:
                changed.append({'path': norm, 'reason': 'boot application canonicalized after compile failure'})
            continue
        if _is_entry_controller_target(norm):
            if abs_path.exists() and _rewrite_entry_controller(project_root, norm):
                changed.append({'path': norm, 'reason': 'entry controller normalized to redirect-only'})
            continue
        if _is_boot_crud_target(norm):
            continue
        if abs_path.exists() and abs_path.suffix == '.java' and _align_java_public_type_to_filename(abs_path):
            changed.append({'path': norm, 'reason': 'public type aligned to filename'})
        dao_alignment_changes = _ensure_dao_mapper_method_alignment(project_root, norm)
        if dao_alignment_changes:
            changed.extend(dao_alignment_changes)
        if any(norm.endswith(suffix) for suffix in ('ServiceImpl.java', 'DAO.java', 'Service.java', 'Mapper.java', 'Mapper.xml', 'VO.java', 'Controller.java', 'Calendar.jsp', 'Form.jsp', 'List.jsp', 'Detail.jsp', 'View.jsp', 'Edit.jsp')) or (norm.endswith('WebMvcConfig.java') and '/config/' in norm):
            syntax_broken_vo = _has_vo_syntax_failure(errors, norm)
            manifest_meta = (manifest or {}).get(norm) or {}
            if syntax_broken_vo:
                local_spec = str(manifest_meta.get('spec') or '')
                shared_parts = [part for part in bundle_specs if part.strip()]
                spec = '\n'.join(shared_parts) if shared_parts else local_spec
            else:
                meta = _manifest_meta_for_target(project_root, manifest, norm) or {}
                local_spec = str(meta.get('spec') or (_read_text(abs_path) if abs_path.exists() and abs_path.is_file() else ''))
                spec = local_spec if not shared_bundle_spec else (local_spec + '\n' + shared_bundle_spec if local_spec else shared_bundle_spec)
            built = build_builtin_fallback_content(norm, spec, project_name=str(getattr(cfg, 'project_name', '') or ''))
            current = _read_text(abs_path) if abs_path.exists() and abs_path.is_file() else ''
            if built and built.strip() and built.strip() != current.strip():
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_text(built, encoding='utf-8')
                if abs_path.suffix == '.java' and _align_java_public_type_to_filename(abs_path):
                    changed.append({'path': norm, 'reason': 'public type realigned after builtin fallback'})
                changed.append({'path': norm, 'reason': 'builtin contract bundle materialized' if not current.strip() else 'builtin contract bundle refreshed'})
    return changed

def _class_path_to_source(path: str) -> str:
    norm = (path or '').replace('\\', '/').strip()
    marker = '/target/classes/'
    idx = norm.lower().find(marker)
    if idx != -1:
        rel = norm[idx + len(marker):]
    else:
        rel = norm
    rel = rel.lstrip('/').rstrip('/')
    if rel.endswith('.class'):
        rel = rel[:-6] + '.java'
    return _normalize('src/main/java/' + rel)
def _startup_compile_guard_targets(runtime_report: Dict[str, Any]) -> List[str]:
    startup_info = (runtime_report or {}).get('startup') or {}
    if (startup_info.get('status') or '').strip().lower() != 'failed':
        return []
    errors = startup_info.get('errors') or []
    log_text = ' '.join(str(startup_info.get(key) or '') for key in ('raw_output', 'log_tail'))
    if not (_UNRESOLVED_RE.search(log_text) or any((err.get('code') == 'unresolved_compilation') for err in errors)):
        return []
    targets: List[str] = []
    for match in _STARTUP_CLASS_RE.finditer(log_text):
        source = _class_path_to_source(match.group('path'))
        if source:
            targets.append(source)
    return targets
def _class_stem(name: str) -> str:
    stem = name
    for suffix in _CLASS_SUFFIXES:
        if stem.endswith(suffix) and len(stem) > len(suffix):
            return stem[:-len(suffix)]
    for suffix in _VIEW_SUFFIXES:
        if stem.endswith(suffix) and len(stem) > len(suffix):
            return stem[:-len(suffix)]
    return stem
def _infer_related_context(rel: str) -> Dict[str, str]:
    norm = _normalize(rel)
    info = {'domain': '', 'stem': ''}
    parts = Path(norm).parts
    if not parts:
        return info
    if norm.startswith('src/main/java/'):
        pkg_parts = list(parts[3:-1])
        for idx, token in enumerate(pkg_parts):
            if token in _LAYER_MARKERS and idx > 0:
                info['domain'] = pkg_parts[idx - 1]
                break
        info['stem'] = _class_stem(Path(norm).stem)
        return info
    if norm.startswith('src/main/webapp/WEB-INF/views/') and len(parts) >= 6:
        info['domain'] = parts[4]
        info['stem'] = _class_stem(Path(norm).stem)
        return info
    if norm.startswith('src/main/resources/'):
        lower_parts = [p.lower() for p in parts]
        for idx, token in enumerate(lower_parts):
            if token in ('mapper', 'mappers') and idx + 1 < len(parts):
                info['domain'] = parts[idx + 1]
                break
        info['stem'] = _class_stem(Path(norm).stem.replace('Mapper', ''))
    return info
def _expand_related_targets(project_root: Path, targets: List[str]) -> List[str]:
    root = Path(project_root)
    ordered: List[str] = []
    seen = set()
    def _push(path: str) -> None:
        norm = _normalize(path)
        if norm and norm not in seen:
            seen.add(norm)
            ordered.append(norm)
    for rel in targets:
        if _is_boot_crud_target(rel) or _is_illegal_infra_artifact(rel):
            continue
        _push(rel)
        info = _infer_related_context(rel)
        domain = (info.get('domain') or '').strip()
        stem = (info.get('stem') or '').strip()
        candidates: List[Path] = []
        if domain:
            java_root = root / 'src/main/java'
            if java_root.exists():
                candidates.extend(java_root.rglob(f'*/{domain}/**/*.java'))
            resources_root = root / 'src/main/resources'
            if resources_root.exists():
                candidates.extend(resources_root.rglob(f'*/{domain}/**/*.xml'))
            view_root = root / 'src/main/webapp/WEB-INF/views' / domain
            if view_root.exists():
                candidates.extend(view_root.rglob('*.jsp'))
        if stem:
            java_root = root / 'src/main/java'
            if java_root.exists():
                candidates.extend(java_root.rglob(f'{stem}*.java'))
            resources_root = root / 'src/main/resources'
            if resources_root.exists():
                candidates.extend(resources_root.rglob(f'{stem}*.xml'))
        for candidate in candidates:
            if not candidate.exists() or not candidate.is_file():
                continue
            try:
                rel_path = candidate.relative_to(root).as_posix()
            except Exception:
                continue
            if _is_boot_crud_target(rel_path) or _is_illegal_infra_artifact(rel_path):
                continue
            name = candidate.stem
            if stem and stem.lower() not in name.lower() and domain and f'/{domain}/' not in ('/' + rel_path.lower() + '/'):
                continue
            _push(rel_path)
    return ordered
def _normalize(path: str) -> str:
    norm = (path or '').replace('\\', '/').strip()
    while norm.startswith('./'):
        norm = norm[2:]
    while norm.startswith('.\\'):
        norm = norm[2:]
    return norm
def _existing_build_targets(project_root: Path) -> List[str]:
    root = Path(project_root)
    known = [
        'pom.xml',
        'mvnw',
        'mvnw.cmd',
        '.mvn/wrapper/maven-wrapper.properties',
        'src/main/resources/application.properties',
        'build.gradle',
        'build.gradle.kts',
        'gradlew',
        'gradlew.bat',
    ]
    return [rel for rel in known if (root / rel).exists()]
def _bootstrap_targets(runtime_report: Dict[str, Any], project_root: Path) -> List[str]:
    compile_info = (runtime_report or {}).get('compile') or {}
    errors = compile_info.get('errors') or []
    raw_output = ' '.join(str(compile_info.get(key) or '') for key in ('raw_output', 'log_tail')).lower()
    codes = {str(item.get('code') or '').strip() for item in errors}
    targets: List[str] = []
    if {'maven_wrapper_bootstrap', 'maven_wrapper_download'} & codes or 'invoke-webrequest' in raw_output or 'expand-archive' in raw_output or '[mvnw.cmd]' in raw_output:
        targets.extend([rel for rel in ('mvnw.cmd', '.mvn/wrapper/maven-wrapper.properties', 'mvnw') if (project_root / rel).exists()])
    if 'pom_parse_error' in codes or 'non-parseable pom' in raw_output or 'malformed pom' in raw_output:
        if (project_root / 'pom.xml').exists():
            targets.append('pom.xml')
    if 'build_tool_missing' in codes:
        targets.extend(_existing_build_targets(project_root) or ['pom.xml', 'mvnw', 'mvnw.cmd', '.mvn/wrapper/maven-wrapper.properties'])
    dedup: List[str] = []
    seen = set()
    for item in targets:
        norm = _normalize(item)
        if norm and norm not in seen:
            seen.add(norm)
            dedup.append(norm)
    return dedup
def collect_compile_repair_targets(runtime_report: Dict[str, Any], manifest: Dict[str, Dict[str, Any]], project_root: Optional[Path] = None) -> List[str]:
    compile_info = (runtime_report or {}).get('compile') or {}
    errors = compile_info.get('errors') or []
    paths = compile_error_paths(errors)
    bootstrap = _bootstrap_targets(runtime_report, Path(project_root)) if project_root else []
    startup_targets = _startup_compile_guard_targets(runtime_report)
    ordered = list(paths) + [item for item in bootstrap if item not in paths] + [item for item in startup_targets if item not in paths and item not in bootstrap]
    if not ordered and manifest:
        targets: List[str] = []
        summary = ' '.join(summarize_compile_errors(errors, limit=20)).lower()
        for rel, meta in (manifest or {}).items():
            rel_norm = _normalize(rel).lower()
            source_norm = _normalize(str((meta or {}).get('source_path') or '')).lower()
            if rel_norm and rel_norm in summary:
                targets.append(rel)
            elif source_norm and source_norm in summary:
                targets.append(rel)
        ordered = targets + bootstrap + [item for item in startup_targets if item not in targets and item not in bootstrap]
    if project_root and ordered:
        ordered = _expand_related_targets(Path(project_root), ordered)
    dedup: List[str] = []
    seen = set()
    for item in ordered:
        norm = _normalize(item)
        if norm and norm not in seen:
            seen.add(norm)
            dedup.append(norm)
    return dedup
def _template_op_for_target(rel: str, cfg: Any) -> Optional[Dict[str, Any]]:
    rel = _normalize(rel)
    if rel == 'pom.xml':
        return {'path': rel, 'content': render_pom_xml(cfg)}
    if rel == 'mvnw':
        return {'path': rel, 'content': render_mvnw()}
    if rel == 'mvnw.cmd':
        return {'path': rel, 'content': render_mvnw_cmd()}
    if rel == '.mvn/wrapper/maven-wrapper.properties':
        return {'path': rel, 'content': render_maven_wrapper_properties()}
    if rel == 'src/main/resources/application.properties':
        return {'path': rel, 'content': render_application_properties(cfg)}
    return None
def _repair_template_managed_targets(project_root: Path, cfg: Any, targets: List[str]) -> List[Dict[str, Any]]:
    ops: List[Dict[str, Any]] = []
    for rel in targets:
        op = _template_op_for_target(rel, cfg)
        if op is not None:
            ops.append(op)
    if not ops:
        return []
    apply_file_ops(ops, project_root, overwrite=True)
    return [{'path': _normalize(op['path']), 'reason': 'template-managed build file refreshed'} for op in ops]
def _manifest_meta_for_target(project_root: Path, manifest: Dict[str, Dict[str, Any]], rel: str) -> Optional[Dict[str, Any]]:
    rel = _normalize(rel)
    meta = (manifest or {}).get(rel)
    if meta:
        return meta
    abs_path = Path(project_root) / rel
    if not abs_path.exists():
        return None
    try:
        spec = abs_path.read_text(encoding='utf-8')
    except Exception:
        spec = abs_path.read_text(encoding='utf-8', errors='ignore')
    return {
        'source_path': rel,
        'purpose': 'generated',
        'spec': spec,
    }
def regenerate_compile_failure_targets(
    project_root: Path,
    cfg: Any,
    manifest: Dict[str, Dict[str, Any]],
    runtime_report: Dict[str, Any],
    regenerate_callback: Optional[RegenCallback],
    apply_callback: Callable[[Path, Any, Dict[str, Any], bool], Dict[str, Any]],
    use_execution_core: bool,
    frontend_key: str,
    max_attempts: int = 1,
) -> Dict[str, Any]:
    preflight_invariants = enforce_generated_project_invariants(project_root)
    targets = collect_compile_repair_targets(runtime_report, manifest, project_root=project_root)
    if not targets:
        return {'attempted': False, 'targets': [], 'changed': [], 'skipped': [{'path': '', 'reason': 'no_compile_targets'}]}
    changed: List[Dict[str, Any]] = list(preflight_invariants.get('changed') or [])
    skipped: List[Dict[str, Any]] = []
    compile_errors = ((runtime_report or {}).get('compile') or {}).get('errors') or []
    reason_text = '; '.join(summarize_compile_errors(compile_errors, limit=8)) or 'backend compile failed'
    local_changed = _local_contract_repair(project_root, cfg, manifest, targets, runtime_report)
    if local_changed:
        changed.extend(local_changed)
        for path_obj in fix_project_java_imports(project_root):
            try:
                rel = path_obj.relative_to(project_root).as_posix()
            except Exception:
                rel = str(path_obj).replace('\\', '/')
            changed.append({'path': rel, 'reason': 'java imports refreshed after local contract repair'})
    template_targets = [rel for rel in targets if _normalize(rel) in _BUILD_TEMPLATE_TARGETS]
    if template_targets:
        changed.extend(_repair_template_managed_targets(project_root, cfg, template_targets))
    source_targets = [rel for rel in targets if _normalize(rel) not in _BUILD_TEMPLATE_TARGETS and _normalize(rel) not in {item.get('path') for item in changed}]
    if source_targets and regenerate_callback is None:
        skipped.extend({'path': rel, 'reason': 'no_regen_callback'} for rel in source_targets)
        return {'attempted': bool(changed or source_targets), 'targets': targets, 'changed': changed, 'skipped': skipped}
    for rel in source_targets:
        meta = _manifest_meta_for_target(project_root, manifest, rel)
        if not meta:
            skipped.append({'path': rel, 'reason': 'missing_manifest'})
            continue
        success = False
        last_reason = reason_text
        for attempt in range(1, max(1, int(max_attempts)) + 1):
            try:
                regen_op = regenerate_callback(meta.get('source_path') or rel, meta.get('purpose') or 'generated', meta.get('spec') or '', last_reason)
            except Exception as exc:
                last_reason = f'regenerate callback failed: {exc}'
                regen_op = None
            if not regen_op or not isinstance(regen_op, dict) or not (regen_op.get('content') or '').strip():
                if not last_reason.startswith('regenerate callback failed:'):
                    last_reason = 'regenerate callback returned empty content'
                continue
            apply_callback(project_root, cfg, regen_op, use_execution_core)
            changed.extend(enforce_generated_project_invariants(project_root).get('changed') or [])
            abs_path = project_root / rel
            if abs_path.exists() and abs_path.suffix == '.java' and _align_java_public_type_to_filename(abs_path):
                changed.append({'path': rel, 'attempts': attempt, 'reason': 'public type realigned after regeneration'})
            fix_project_java_imports(project_root)
            body = abs_path.read_text(encoding='utf-8', errors='ignore') if abs_path.exists() else ''
            ok, validation_reason = validate_generated_content(rel, body, frontend_key=frontend_key)
            if ok:
                changed.append({'path': rel, 'attempts': attempt, 'reason': reason_text})
                success = True
                break
            last_reason = validation_reason
        if not success:
            skipped.append({'path': rel, 'reason': last_reason})
    return {'attempted': True, 'targets': targets, 'changed': changed, 'skipped': skipped}
