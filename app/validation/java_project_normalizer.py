from __future__ import annotations

from pathlib import Path
import re
from typing import Dict, List, Tuple

from app.ui.java_import_fixer import fix_project_java_imports
from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH

_PUBLIC_TYPE_RE = re.compile(r"\bpublic\s+(class|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_PACKAGE_RE = re.compile(r"^\s*package\s+([A-Za-z0-9_.]+)\s*;\s*$", re.MULTILINE)
_IMPORT_RE = re.compile(r"^\s*import\s+([A-Za-z0-9_.]+)\s*;\s*$", re.MULTILINE)

_AUTH_HELPER_SPECS = {
    "IntegratedAuthService.java": {"logical": "java/service/IntegratedAuthService.java", "unified_auth": True, "cert_login": False, "jwt_login": False},
    "IntegratedAuthServiceImpl.java": {"logical": "java/service/impl/IntegratedAuthServiceImpl.java", "unified_auth": True, "cert_login": False, "jwt_login": False},
    "CertLoginService.java": {"logical": "java/service/CertLoginService.java", "unified_auth": True, "cert_login": True, "jwt_login": False},
    "CertLoginServiceImpl.java": {"logical": "java/service/impl/CertLoginServiceImpl.java", "unified_auth": True, "cert_login": True, "jwt_login": False},
    "CertLoginController.java": {"logical": "java/controller/CertLoginController.java", "unified_auth": True, "cert_login": True, "jwt_login": False},
    "JwtLoginController.java": {"logical": "java/controller/JwtLoginController.java", "unified_auth": True, "cert_login": False, "jwt_login": True},
    "JwtTokenProvider.java": {"logical": "java/config/JwtTokenProvider.java", "unified_auth": True, "cert_login": False, "jwt_login": True},
    "AuthLoginInterceptor.java": {"logical": "java/config/AuthLoginInterceptor.java", "unified_auth": True, "cert_login": False, "jwt_login": False},
    "AuthenticInterceptor.java": {"logical": "java/config/AuthLoginInterceptor.java", "unified_auth": True, "cert_login": False, "jwt_login": False},
    "AuthInterceptor.java": {"logical": "java/config/AuthLoginInterceptor.java", "unified_auth": True, "cert_login": False, "jwt_login": False},
    "WebConfig.java": {"logical": "java/config/WebMvcConfig.java", "unified_auth": True, "cert_login": False, "jwt_login": False},
    "WebMvcConfig.java": {"logical": "java/config/WebMvcConfig.java", "unified_auth": True, "cert_login": False, "jwt_login": False},
}

_AUTH_HELPER_SEGMENTS = {"integratedauth", "certlogin", "jwtlogin", "jwttokenprovider", "authlogininterceptor", "authenticinterceptor", "authinterceptor", "webconfig", "webmvcconfig", "spring", "logindatabaseinitializer"}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return path.read_text(encoding="utf-8", errors="ignore")


def _write_text(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


def _public_type_name(body: str) -> Tuple[str, str]:
    match = _PUBLIC_TYPE_RE.search(body or "")
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def _replace_identifier_everywhere(body: str, old: str, new: str) -> str:
    if not old or not new or old == new:
        return body
    return re.sub(rf"\b{re.escape(old)}\b", new, body)


def _module_base_from_package(package_name: str) -> str:
    pkg = (package_name or "").strip()
    for suffix in ('.service.impl', '.service.mapper', '.service.vo', '.service', '.web', '.config'):
        if pkg.endswith(suffix):
            return pkg[:-len(suffix)]
    return pkg


def _base_package_for_login_owner(path: Path, body: str) -> str:
    pkg_match = _PACKAGE_RE.search(body or "")
    package_name = pkg_match.group(1) if pkg_match else ""
    module_base = _module_base_from_package(package_name)
    parts = [part for part in module_base.split('.') if part]
    while parts and parts[-1].lower() in _AUTH_HELPER_SEGMENTS:
        parts.pop()
    if parts and parts[-1].lower() == 'login':
        parts.pop()
    if parts:
        return '.'.join(parts)

    rel_parts = list(path.parts)
    pkg_parts: List[str] = []
    if 'java' in rel_parts:
        src_idx = rel_parts.index('java')
        pkg_parts = rel_parts[src_idx + 1:-1]
    while pkg_parts and pkg_parts[-1] in {'impl', 'mapper', 'vo', 'service', 'web', 'config'}:
        pkg_parts.pop()
    while pkg_parts and pkg_parts[-1].lower() in _AUTH_HELPER_SEGMENTS:
        pkg_parts.pop()
    if pkg_parts and pkg_parts[-1].lower() == 'login':
        pkg_parts.pop()
    return '.'.join(pkg_parts)


def _normalize_auth_helper_bundle(path: Path, body: str) -> Tuple[str, bool]:
    spec = _AUTH_HELPER_SPECS.get(path.name)
    if not spec:
        return body, False
    base_package = _base_package_for_login_owner(path, body)
    if not base_package:
        return body, False
    schema = schema_for(
        'Login',
        feature_kind=FEATURE_KIND_AUTH,
        unified_auth=bool(spec.get('unified_auth')),
        cert_login=bool(spec.get('cert_login')),
        jwt_login=bool(spec.get('jwt_login')),
    )
    built = builtin_file(str(spec.get('logical') or ''), base_package, schema) or ''
    if not built.strip():
        return body, False
    return built, built != body




def _auth_helper_bundle_needs_rebuild(path: Path, body: str) -> bool:
    spec = _AUTH_HELPER_SPECS.get(path.name)
    if not spec:
        return False
    expected = path.stem
    _kind, actual = _public_type_name(body)
    if actual and actual != expected:
        return True
    lowered = body.lower()
    helper_tokens = ('.certlogin.service.vo', '.integratedauth.service.vo', '.jwtlogin.service.vo')
    if any(token in lowered for token in helper_tokens):
        return True
    if path.name == 'CertLoginService.java' and 'authenticateCertificate(' not in body:
        return True
    if path.name == 'CertLoginServiceImpl.java' and ('implements CertLoginService' not in body or 'IntegratedAuthService' not in body):
        return True
    if path.name == 'IntegratedAuthService.java' and 'resolveIntegratedUser(' not in body:
        return True
    if path.name == 'IntegratedAuthServiceImpl.java' and ('implements IntegratedAuthService' not in body or 'resolveIntegratedUser(' not in body):
        return True
    return False

def _normalize_public_type_name(path: Path, body: str) -> Tuple[str, bool]:
    expected = path.stem
    kind, actual = _public_type_name(body)
    if not kind or not actual or actual == expected:
        return body, False
    updated = _replace_identifier_everywhere(body, actual, expected)
    return updated, updated != body


def _normalize_service_impl_contract(path: Path, body: str) -> Tuple[str, bool]:
    expected = path.stem
    if not expected.endswith("ServiceImpl"):
        return body, False
    service_name = expected[:-4]
    updated = body
    updated = re.sub(r"\bimplements\s+[A-Za-z_][A-Za-z0-9_]*\b", f"implements {service_name}", updated, count=1)
    return updated, updated != body


def _normalize_auth_import_hints(path: Path, body: str) -> Tuple[str, bool]:
    expected = path.stem
    updated = body
    if expected == "CertLoginServiceImpl":
        updated = re.sub(r"\bimplements\s+LoginService\b", "implements CertLoginService", updated)
        updated = re.sub(r"\bpublic\s+class\s+LoginServiceImpl\b", "public class CertLoginServiceImpl", updated)
    if expected == "CertLoginService":
        updated = re.sub(r"\bpublic\s+interface\s+LoginService\b", "public interface CertLoginService", updated)
        updated = re.sub(r"\binterface\s+LoginService\b", "interface CertLoginService", updated)
    if expected == "IntegratedAuthServiceImpl":
        updated = re.sub(r"\bimplements\s+LoginService\b", "implements IntegratedAuthService", updated)
        updated = re.sub(r"\bpublic\s+class\s+LoginServiceImpl\b", "public class IntegratedAuthServiceImpl", updated)
    if expected == "IntegratedAuthService":
        updated = re.sub(r"\bpublic\s+interface\s+LoginService\b", "public interface IntegratedAuthService", updated)
        updated = re.sub(r"\binterface\s+LoginService\b", "interface IntegratedAuthService", updated)
    return updated, updated != body


def _dedupe_same_package_imports(path: Path, body: str) -> Tuple[str, bool]:
    pkg_match = _PACKAGE_RE.search(body or "")
    if not pkg_match:
        return body, False
    package_name = pkg_match.group(1)
    lines = body.splitlines()
    changed = False
    cleaned: List[str] = []
    for line in lines:
        m = _IMPORT_RE.match(line)
        if m:
            imp = m.group(1)
            if imp.startswith(package_name + ".") and imp.rsplit(".", 1)[-1] == path.stem:
                changed = True
                continue
        cleaned.append(line)
    return "\n".join(cleaned) + ("\n" if body.endswith("\n") else ""), changed


def normalize_generated_project(project_root: Path) -> Dict[str, List[str]]:
    root = Path(project_root)
    src = root / "src/main/java"
    if not src.exists():
        return {"changed": [], "normalized_types": [], "normalized_contracts": []}

    changed: List[str] = []
    normalized_types: List[str] = []
    normalized_contracts: List[str] = []

    for path in sorted(src.rglob("*.java")):
        if not path.is_file():
            continue
        body = _read_text(path)
        updated = body
        file_changed = False
        rel = str(path.relative_to(root)).replace("\\", "/")

        if _auth_helper_bundle_needs_rebuild(path, updated):
            updated, ok = _normalize_auth_helper_bundle(path, updated)
        else:
            updated, ok = (updated, False)
        if ok:
            file_changed = True
            if rel not in normalized_contracts:
                normalized_contracts.append(rel)

        updated, ok = _normalize_public_type_name(path, updated)
        if ok:
            file_changed = True
            normalized_types.append(rel)

        updated, ok = _normalize_service_impl_contract(path, updated)
        if ok:
            file_changed = True
            if rel not in normalized_contracts:
                normalized_contracts.append(rel)

        updated, ok = _normalize_auth_import_hints(path, updated)
        if ok:
            file_changed = True
            if rel not in normalized_contracts:
                normalized_contracts.append(rel)

        updated, ok = _dedupe_same_package_imports(path, updated)
        if ok:
            file_changed = True

        if file_changed and updated != body:
            _write_text(path, updated)
            changed.append(rel)

    import_changed = [str(p.relative_to(root)).replace("\\", "/") for p in fix_project_java_imports(root)]
    for rel in import_changed:
        if rel not in changed:
            changed.append(rel)

    return {
        "changed": changed,
        "normalized_types": normalized_types,
        "normalized_contracts": normalized_contracts,
    }
