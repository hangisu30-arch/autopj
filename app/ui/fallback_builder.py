from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.feature_rules import classify_feature_kind, FEATURE_KIND_SCHEDULE
from app.ui.generated_content_validator import validate_generated_content
from app.ui.ui_sanitize_common import repair_invalid_generated_content

_SUFFIXES = (
    "RestController.java",
    "Controller.java",
    "ServiceImpl.java",
    "DAO.java",
    "Service.java",
    "Mapper.java",
    "Mapper.xml",
    "VO.java",
)


_AUTH_HELPER_LOGICAL_PATHS = {
    "IntegratedAuthService.java": "java/service/IntegratedAuthService.java",
    "IntegratedAuthServiceImpl.java": "java/service/impl/IntegratedAuthServiceImpl.java",
    "IntegratedAuthController.java": "java/controller/IntegratedAuthController.java",
    "CertLoginService.java": "java/service/CertLoginService.java",
    "CertLoginServiceImpl.java": "java/service/impl/CertLoginServiceImpl.java",
    "CertLoginController.java": "java/controller/CertLoginController.java",
    "JwtLoginController.java": "java/controller/JwtLoginController.java",
    "JwtTokenProvider.java": "java/config/JwtTokenProvider.java",
    "AuthLoginInterceptor.java": "java/config/AuthLoginInterceptor.java",
    "AuthenticInterceptor.java": "java/config/AuthLoginInterceptor.java",
    "AuthInterceptor.java": "java/config/AuthLoginInterceptor.java",
    "WebConfig.java": "java/config/WebMvcConfig.java",
    "WebMvcConfig.java": "java/config/WebMvcConfig.java",
}

_AUTH_HELPER_SEGMENTS = {"integratedauth", "certlogin", "jwtlogin", "jwttokenprovider", "authlogininterceptor", "authenticinterceptor", "authinterceptor", "webconfig", "webmvcconfig", "spring", "logindatabaseinitializer"}

_AUTH_HELPER_OWNER_ENTITY = {name: "Login" for name in _AUTH_HELPER_LOGICAL_PATHS}



_INFRA_CANONICAL_NAMES = {"AuthLoginInterceptor.java", "WebMvcConfig.java"}
_INFRA_ALIAS_FILENAMES = {"AuthenticInterceptor.java", "AuthInterceptor.java", "WebConfig.java"}
_INFRA_CRUD_STEMS = {"AuthLoginInterceptor", "AuthenticInterceptor", "AuthInterceptor", "WebConfig", "WebMvcConfig"}
_INFRA_ILLEGAL_SUFFIXES = ("Controller.java", "ServiceImpl.java", "Service.java", "Mapper.java", "Mapper.xml", "VO.java", "List.jsp", "Detail.jsp", "Form.jsp", "Calendar.jsp", "View.jsp", "Edit.jsp")


def _is_illegal_infra_artifact(path: str) -> bool:
    name = Path(_normalize(path)).name
    if name in _INFRA_ALIAS_FILENAMES:
        return True
    if name in _INFRA_CANONICAL_NAMES:
        return False
    for stem in _INFRA_CRUD_STEMS:
        if any(name == f"{stem}{suffix}" for suffix in _INFRA_ILLEGAL_SUFFIXES):
            return True
    return False

_BOOT_APP_CLASS = 'EgovBootApplication'
_BOOT_APP_ILLEGAL_SUFFIXES = ('Controller.java', 'ServiceImpl.java', 'Service.java', 'Mapper.java', 'VO.java', 'Mapper.xml', 'List.jsp', 'Detail.jsp', 'Form.jsp', 'Calendar.jsp', 'View.jsp', 'Edit.jsp')


def _is_boot_crud_artifact(path: str) -> bool:
    name = Path(_normalize(path)).name
    if name == f'{_BOOT_APP_CLASS}.java':
        return False
    return any(name == f'{_BOOT_APP_CLASS}{suffix}' for suffix in _BOOT_APP_ILLEGAL_SUFFIXES)


def _normalize(path: str) -> str:
    return (path or "").replace("\\", "/").strip()


def _safe_segment(text: str, default: str = "app") -> str:
    value = re.sub(r"[^A-Za-z0-9_]+", "", text or "").strip("_")
    return value or default


def _extract_entity(path: str) -> str:
    name = Path(path).name
    for suffix in _SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    if name.endswith(".vue"):
        for suffix in ("List.vue", "Detail.vue", "Form.vue"):
            if name.endswith(suffix) and len(name) > len(suffix):
                return name[: -len(suffix)]
    return "Item"


def _base_package_from_path(path: str, project_name: str = "") -> str:
    norm = _normalize(path)
    marker = "src/main/java/"
    if marker in norm:
        tail = norm.split(marker, 1)[1]
        parts = tail.split("/")[:-1]
        if parts:
            while parts and parts[-1] in {"web", "service", "impl", "mapper", "vo", "config"}:
                parts.pop()
            while parts and parts[-1].lower() in _AUTH_HELPER_SEGMENTS:
                parts.pop()
            if parts:
                return ".".join(parts)
    project_segment = _safe_segment(project_name, "example").lower()
    return f"egovframework.{project_segment}"


_FIELD_LINE_RE = re.compile(r"(?:fields?|columns?|컬럼)\s*(?:은|는|:)\s*([^\n\.]+)", re.IGNORECASE)
_FIELD_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TYPED_FIELD_RE = re.compile(
    r"(?:private|protected|public)?\s*(?:static\s+)?(?:final\s+)?(?P<type>[A-Z][A-Za-z0-9_<>.]*)\s+(?P<name>[a-z][A-Za-z0-9_]*)\s*(?:[;,)])"
)
_SQL_COLUMN_RE = re.compile(
    r"(?P<col>[a-z][a-z0-9_]*?)\s+(?P<type>bigint|int|integer|smallint|tinyint|numeric|decimal|varchar|char|text|timestamp|datetime|date|time|boolean|bit)\b",
    re.IGNORECASE,
)
_GENERIC_TYPE_TOKENS = {"Model", "List", "Map", "HashMap", "LinkedHashMap", "ArrayList", "Optional", "Object", "HttpSession", "WebDataBinder"}


_EXPLICIT_REQUIREMENT_BULLET_RE = re.compile(r'^(?:[-*•]|\d+[\.)])\s*[`\"\']?(?P<name>[A-Za-z_][A-Za-z0-9_]*)[`\"\']?(?:\s*[(:].*)?$')


_JAVA_KEYWORDS = {
    'abstract','assert','boolean','break','byte','case','catch','char','class','const','continue','default','do','double','else','enum','extends','final','finally','float','for','goto','if','implements','import','instanceof','int','interface','long','native','new','package','private','protected','public','return','short','static','strictfp','super','switch','synchronized','this','throw','throws','transient','try','void','volatile','while','true','false','null','record','sealed','permits','var','yield'
}


def _is_valid_java_identifier(name: str) -> bool:
    raw = (name or '').strip()
    return bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', raw)) and raw not in _JAVA_KEYWORDS


def _is_valid_column_identifier(name: str) -> bool:
    return bool(re.fullmatch(r'[a-z][a-z0-9_]*', (name or '').strip().lower()))


def _extract_explicit_requirement_fields(spec: str) -> List[Tuple[str, str, str]]:
    body = spec or ''
    fields: List[Tuple[str, str, str]] = []
    seen: set[str] = set()

    def _push(token: str) -> None:
        col = re.sub(r'[^A-Za-z0-9_]+', '_', (token or '').strip()).strip('_').lower()
        if not col or not _is_valid_column_identifier(col):
            return
        prop = _prop_from_col(col)
        if not prop or not _is_valid_java_identifier(prop):
            return
        key = prop.lower()
        if key in seen:
            return
        seen.add(key)
        fields.append((prop, col, _java_type_for(prop, col)))

    for match in _FIELD_LINE_RE.finditer(body):
        chunk = match.group(1)
        for token in re.split(r'[,/\s]+', chunk):
            if token.strip():
                _push(token)

    lines = [line.rstrip() for line in body.splitlines()]
    collecting = False
    for raw in lines:
        line = raw.strip()
        if not line:
            collecting = False
            continue
        if re.search(r'(?:최소\s*)?(?:컬럼|필드|항목)(?:\s*목록)?\s*(?::|은|는|=)?', line, re.IGNORECASE):
            collecting = True
            continue
        if not collecting:
            continue
        bullet = _EXPLICIT_REQUIREMENT_BULLET_RE.match(line)
        if bullet:
            _push(bullet.group('name'))
            continue
        if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', line):
            _push(line)
            continue
        collecting = False
    return fields


def _prop_from_col(col: str) -> str:
    parts = [part for part in (col or '').split('_') if part]
    if not parts:
        return ''
    return parts[0].lower() + ''.join(part[:1].upper() + part[1:] for part in parts[1:])


def _normalize_java_type(jt: str) -> str:
    raw = (jt or '').strip()
    if not raw:
        return 'String'
    simple = raw.split('.')[-1].replace('>', '').replace('<', '').strip()
    mapping = {
        'Long': 'Long',
        'long': 'Long',
        'Integer': 'Integer',
        'int': 'Integer',
        'BigDecimal': 'java.math.BigDecimal',
        'Date': 'String',
        'LocalDate': 'String',
        'LocalDateTime': 'String',
        'Boolean': 'Boolean',
        'boolean': 'Boolean',
        'String': 'String',
    }
    return mapping.get(raw, mapping.get(simple, simple if '.' in raw else 'String'))


def _java_type_for(prop: str, col: str) -> str:
    name = (prop or col or "").lower()
    if name == "id":
        return "String"
    if name.endswith("id") or name.endswith("_id"):
        return "String"
    if any(token in name for token in ("date", "time", "datetime", "_dt")):
        return "String"
    return "String"


def _type_rank(jt: str) -> int:
    norm = (jt or '').strip()
    if norm in {'Long', 'Integer', 'java.math.BigDecimal', 'java.util.Date', 'java.time.LocalDate', 'java.time.LocalDateTime', 'Boolean'}:
        return 3
    if norm == 'String':
        return 1
    return 2


def _infer_typed_fields(spec: str) -> List[Tuple[str, str, str]]:
    typed_map: dict[str, Tuple[str, str, str]] = {}
    for match in _TYPED_FIELD_RE.finditer(spec or ''):
        name = (match.group('name') or '').strip()
        raw_type = (match.group('type') or '').strip()
        if not name or raw_type in _GENERIC_TYPE_TOKENS:
            continue
        jt = _normalize_java_type(raw_type)
        if jt == 'String' and raw_type not in {'String', 'java.lang.String'} and raw_type.split('.')[-1] != 'String':
            continue
        key = name.lower()
        col = re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()
        existing = typed_map.get(key)
        if existing is None or _type_rank(jt) >= _type_rank(existing[2]):
            typed_map[key] = (name, col, jt)
    for match in _SQL_COLUMN_RE.finditer(spec or ''):
        col = (match.group('col') or '').strip().lower()
        if not col:
            continue
        prop = _prop_from_col(col)
        if not prop:
            continue
        sql_type = (match.group('type') or '').lower()
        if sql_type in {'bigint', 'int', 'integer', 'smallint', 'tinyint'}:
            jt = 'String' if col.endswith('_id') or col == 'id' else 'Integer'
        elif sql_type in {'numeric', 'decimal'}:
            jt = 'java.math.BigDecimal'
        elif sql_type in {'timestamp', 'datetime', 'date', 'time'}:
            jt = 'String'
        elif sql_type in {'boolean', 'bit'}:
            jt = 'Boolean'
        else:
            jt = 'String'
        key = prop.lower()
        existing = typed_map.get(key)
        if existing is None or _type_rank(jt) >= _type_rank(existing[2]):
            typed_map[key] = (prop, col, jt)
    return list(typed_map.values())


def _infer_fields(spec: str, entity: str) -> List[Tuple[str, str, str]]:
    text = spec or ""
    fields: List[Tuple[str, str, str]] = []
    seen: set[str] = set()
    typed_by_name = {prop.lower(): (prop, col, jt) for prop, col, jt in _infer_typed_fields(text)}
    explicit_fields = _extract_explicit_requirement_fields(text)

    for prop, col, jt in explicit_fields:
        key = prop.lower()
        if key in seen:
            continue
        typed = typed_by_name.get(key)
        if typed is not None:
            _, _, typed_jt = typed
            fields.append((prop, col, typed_jt))
        else:
            fields.append((prop, col, jt))
        seen.add(key)

    for key, triple in typed_by_name.items():
        if key in seen:
            continue
        prop, col, jt = triple
        if not _is_valid_java_identifier(prop) or not _is_valid_column_identifier(col):
            continue
        fields.append((prop, col, jt))
        seen.add(key)

    if not fields:
        entity_var = entity[:1].lower() + entity[1:] if entity else "item"
        defaults = [
            (f"{entity_var}Id", f"{entity_var}_id", "Long"),
            (f"{entity_var}Name", f"{entity_var}_name", "String"),
            ("email", "email", "String"),
        ]
        for prop, col, jt in defaults:
            if prop.lower() not in seen:
                fields.append((prop, col, jt))
                seen.add(prop.lower())
    return fields

def _logical_path(path: str, entity: str) -> str:
    norm = _normalize(path)
    name = Path(norm).name
    helper_logical = _AUTH_HELPER_LOGICAL_PATHS.get(name)
    if helper_logical:
        return helper_logical
    if norm.startswith("src/main/java/"):
        if name == "MyBatisConfig.java":
            return "java/config/MyBatisConfig.java"
        if name.endswith("RestController.java") or name.endswith("Controller.java"):
            return f"java/controller/{name}"
        if "/service/impl/" in norm and (name.endswith("ServiceImpl.java") or name.endswith("DAO.java")):
            return f"java/service/impl/{name}"
        if "/service/mapper/" in norm and name.endswith("Mapper.java"):
            return f"java/service/mapper/{name}"
        if "/service/vo/" in norm and name.endswith("VO.java"):
            return f"java/service/vo/{name}"
        if "/service/" in norm and name.endswith("Service.java"):
            return f"java/service/{name}"
    if norm.startswith("src/main/resources/") and name.endswith("Mapper.xml"):
        return f"mapper/{name}"
    jsp_marker = "src/main/webapp/WEB-INF/views/"
    if norm.startswith(jsp_marker) and name.endswith(".jsp"):
        tail = norm.split(jsp_marker, 1)[1]
        parts = [part for part in tail.split("/") if part]
        if len(parts) >= 2:
            domain = parts[0]
            return f"jsp/{domain}/{name}"
    if norm.endswith("package.json"):
        return "frontend/package.json"
    return ""




def _infer_feature_kind(path: str, spec: str, entity: str) -> str:
    norm = _normalize(path).lower()
    joined = "\n".join(x for x in [path or "", spec or "", entity or ""] if x)
    canonical_entity = _canonical_userish_entity(entity, spec)
    kind = classify_feature_kind(joined, entity=canonical_entity)
    entity_low = (canonical_entity or '').strip().lower()
    if '/schedule/' in norm or 'calendar.do' in norm or entity_low == 'schedule':
        return FEATURE_KIND_SCHEDULE
    if entity_low in {'signup', 'register', 'registration', 'join'}:
        return 'CRUD'
    if _is_signup_management_spec(spec, entity):
        return 'CRUD'
    if kind == 'AUTH' and entity_low in {'user', 'member', 'account', 'customer'}:
        low = joined.lower()
        explicit_auth = _has_explicit_auth_creation_request(spec)
        if not explicit_auth:
            return 'CRUD'
    return kind


def _entity_from_spec(entity: str, spec: str) -> str:
    if (entity or '').lower() not in {'', 'item'}:
        return entity
    match = re.search(r'(?:table\s*name|table|테이블명|테이블)\s*(?:은|는|:|=)?\s*([A-Za-z_][A-Za-z0-9_]*)', spec or '', re.IGNORECASE)
    if match:
        token = match.group(1).strip()
        if token:
            return token[:1].upper() + token[1:]
    return entity or 'Item'


def _has_explicit_auth_creation_request(spec: str) -> bool:
    joined = (spec or '').lower()
    if not joined.strip():
        return False
    preserve_tokens = (
        '기존 로그인', '기존에 로그인', '로그인은 이미', '로그인 기능은 이미', '로그인은 그대로 유지',
        '기존 로그인은 그대로 유지', 'existing login', 'keep existing login', 'preserve existing login',
        '로그인 재구현 금지', '로그인 기능을 새로 만들지', '로그인을 새로 만들지',
    )
    creation_tokens = (
        '로그인 기능도 구현', '로그인 기능을 구현', '로그인 기능 추가', '로그인 페이지 생성', '로그인 메뉴 추가',
        'implement login', 'create login', 'build login', 'login page', 'login menu', '/login.do', '/login/login.do',
        'authenticate(', '통합인증', 'jwt 로그인', '인증서 로그인', 'certlogin', 'jwtlogin', 'sso',
    )
    if any(token in joined for token in preserve_tokens):
        filtered = joined
        for token in preserve_tokens:
            filtered = filtered.replace(token, ' ')
        joined = filtered
    return any(token in joined for token in creation_tokens)


def _is_signup_management_spec(spec: str, entity: str = '') -> bool:
    joined = "\n".join(part for part in [spec or '', entity or ''] if part).lower()
    signupish = any(token in joined for token in ('signup', 'sign up', 'register', 'registration', '회원가입', '가입화면', '가입 화면')) or (entity or '').strip().lower() in {'signup', 'register', 'registration', 'join'}
    if not signupish:
        return False
    userish = any(token in joined for token in (
        'users', 'user_id', 'login_id', '회원관리', 'user management', 'member management', '중복 로그인 id', 'duplicate login id',
        'email validation', 'phone validation', '이메일 validation', '전화번호 validation',
    ))
    if not userish:
        return False
    explicit_login = _has_explicit_auth_creation_request(spec)
    return not explicit_login


def _canonical_userish_entity(entity: str, spec: str) -> str:
    low = (entity or '').strip().lower()
    joined = "\\n".join(part for part in [spec or '', entity or ''] if part).lower()
    if low in {'signup', 'register', 'registration', 'join'} and _is_signup_management_spec(spec, entity):
        return 'User'
    if 'table: users' in joined or 'table users' in joined or '테이블명: users' in joined or '테이블 이름: users' in joined or "\n- user_id" in joined:
        return 'User'
    if 'table: members' in joined or 'table members' in joined or '테이블명: members' in joined or '테이블 이름: members' in joined or "\n- member_id" in joined:
        return 'Member'
    return entity or 'Item'
def build_builtin_fallback_content(path: str, spec: str, project_name: str = "") -> str:
    norm = _normalize(path)
    if not norm:
        return ""
    name = Path(norm).name
    if _is_boot_crud_artifact(norm):
        return ""
    if _is_illegal_infra_artifact(norm) and name not in _AUTH_HELPER_LOGICAL_PATHS:
        return ""

    owner_entity = _AUTH_HELPER_OWNER_ENTITY.get(name, '')
    entity = owner_entity or _entity_from_spec(_extract_entity(norm), spec)
    fields = _infer_fields(spec, entity)
    feature_kind = _infer_feature_kind(norm, spec, entity)
    joined = "\n".join(part for part in [norm, spec, entity] if part).lower()
    cert_login = name in {"CertLoginService.java", "CertLoginServiceImpl.java", "CertLoginController.java"} or "certlogin" in joined or "certificate login" in joined or "인증서 로그인" in joined
    jwt_login = name in {"JwtLoginController.java", "JwtTokenProvider.java"} or "jwtlogin" in joined or "jwt token" in joined or "jwt 로그인" in joined
    unified_auth = cert_login or jwt_login or name in {"IntegratedAuthService.java", "IntegratedAuthServiceImpl.java", "IntegratedAuthController.java", "AuthLoginInterceptor.java", "AuthenticInterceptor.java", "AuthInterceptor.java", "WebConfig.java", "WebMvcConfig.java"} or "integratedauth" in joined or "통합인증" in joined or "sso" in joined or "authlogininterceptor" in joined or "authenticinterceptor" in joined or "authinterceptor" in joined or name in {"WebConfig.java", "WebMvcConfig.java"}
    schema = schema_for(entity, inferred_fields=fields, feature_kind=feature_kind, unified_auth=unified_auth, cert_login=cert_login, jwt_login=jwt_login)
    base_package = _base_package_from_path(norm, project_name)
    logical = _logical_path(norm, entity)
    if not logical:
        return ""
    built = builtin_file(logical, base_package, schema) or ""
    if not built:
        return ""
    ok, reason = validate_generated_content(norm, built)
    if ok:
        return built
    repaired, changed, repaired_ok, _ = repair_invalid_generated_content(norm, built, reason)
    if changed and repaired_ok:
        return repaired
    return built
