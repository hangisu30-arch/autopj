from __future__ import annotations
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Iterable, Any
import re

from .feature_rules import (
    FEATURE_KIND_AUTH,
    FEATURE_KIND_CRUD,
    FEATURE_KIND_SCHEDULE,
    classify_feature_kind,
    choose_auth_fields,
    is_auth_kind,
    is_read_only_kind,
    is_schedule_kind,
)

@dataclass
class Schema:
    entity: str
    entity_var: str
    table: str
    id_prop: str
    id_column: str
    fields: List[Tuple[str, str, str]]  # (prop, column, java_type)
    routes: Dict[str, str]
    views: Dict[str, str]
    feature_kind: str = FEATURE_KIND_CRUD
    authority: str = "heuristic"
    unified_auth: bool = False
    cert_login: bool = False
    jwt_login: bool = False
    table_comment: str = ""
    db_vendor: str = ""
    field_comments: Dict[str, str] = dc_field(default_factory=dict)
    field_db_types: Dict[str, str] = dc_field(default_factory=dict)
    field_nullable: Dict[str, bool] = dc_field(default_factory=dict)
    field_unique: Dict[str, bool] = dc_field(default_factory=dict)
    field_auto_increment: Dict[str, bool] = dc_field(default_factory=dict)
    field_defaults: Dict[str, str] = dc_field(default_factory=dict)
    field_references: Dict[str, Tuple[str, str]] = dc_field(default_factory=dict)

_AUTH_UNIFIED_HINTS = (
    "통합인증", "sso", "single sign-on", "single sign on", "통합 로그인", "연계 로그인", "federated login",
)
_AUTH_CERT_HINTS = (
    "인증서 로그인", "인증서로그인", "공동인증서", "certificate login", "cert login", "pki", "gpki", "x509",
)
_AUTH_JWT_HINTS = (
    "jwt", "jwt login", "jwt 로그인", "token login", "token auth", "bearer token", "토큰 로그인",
)
_AUTH_NEGATION_HINTS = (
    '생성하지 말', '만들지 말', '추가하지 말', '포함하지 말', '불필요', '필요없', '필요 없', '제외', '금지',
    'do not generate', 'do not create', 'do not add', 'must not generate', 'must not create', 'do not include', 'not needed', 'unnecessary',
)

def _iter_requirementish_text_blobs(source: Any):
    if isinstance(source, dict):
        preferred_keys = (
            'extra_requirements', 'requirements', 'prompt', 'user_prompt', 'instruction', 'instructions',
            'content', 'purpose', 'description', 'summary', 'text', 'message',
        )
        yielded = set()
        for key in preferred_keys:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                yielded.add((key, value))
                yield value
        for key, value in source.items():
            key_low = str(key or '').strip().lower()
            if key_low in {'path', 'target_path', 'file_path', 'filename', 'view_name', 'route', 'url'}:
                continue
            if isinstance(value, str):
                if value.strip() and (key, value) not in yielded:
                    yield value
                continue
            yield from _iter_requirementish_text_blobs(value)
    elif isinstance(source, list):
        for item in source:
            yield from _iter_requirementish_text_blobs(item)
    elif isinstance(source, str):
        if source.strip():
            yield source


def _auth_mode_requested(blobs: str, hints: Tuple[str, ...]) -> bool:
    hay = (blobs or '').lower()
    if not hay.strip():
        return False
    for hint in hints:
        token = str(hint or '').strip().lower()
        if not token or token not in hay:
            continue
        token_idx = hay.find(token)
        window = hay[max(0, token_idx - 40):min(len(hay), token_idx + len(token) + 40)]
        if any(neg in window for neg in _AUTH_NEGATION_HINTS):
            continue
        return True
    return False


def _auth_options_from_sources(sources: Any, feature_kind: str) -> Tuple[bool, bool, bool]:
    if not is_auth_kind(feature_kind):
        return False, False, False
    if isinstance(sources, dict):
        explicit_unified = sources.get('auth_unified_auth')
        explicit_cert = sources.get('auth_cert_login')
        explicit_jwt = sources.get('auth_jwt_login')
        if any(value is not None for value in (explicit_unified, explicit_cert, explicit_jwt)):
            unified_auth = bool(explicit_unified)
            cert_login = bool(explicit_cert)
            jwt_login = bool(explicit_jwt)
            if cert_login or jwt_login:
                unified_auth = unified_auth or cert_login or jwt_login
            return unified_auth, cert_login, jwt_login
    blobs = "\n".join(_iter_requirementish_text_blobs(sources)).lower()
    cert_login = _auth_mode_requested(blobs, _AUTH_CERT_HINTS)
    jwt_login = _auth_mode_requested(blobs, _AUTH_JWT_HINTS)
    unified_auth = _auth_mode_requested(blobs, _AUTH_UNIFIED_HINTS)
    if cert_login or jwt_login:
        unified_auth = unified_auth or cert_login or jwt_login
    return unified_auth, cert_login, jwt_login

def _snake(s: str) -> str:
    s = _strip_logical_tb_prefix(s) or (s or "")
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", (s or "")).strip()
    if not cleaned:
        return "item"
    parts = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", cleaned) or [cleaned]
    return "_".join(p.lower() for p in parts if p)


def _strip_logical_tb_prefix(name: str) -> str:
    raw = re.sub(r"[^A-Za-z0-9_]+", "", str(name or "").strip())
    if not raw:
        return ""
    low = raw.lower()
    if low in {"tb", "tb_"}:
        return ""
    if low.startswith("tb_") and len(raw) > 3:
        raw = raw[3:]
    elif low.startswith("tb") and len(raw) > 2:
        raw = raw[2:]
    raw = re.sub(r"^_+", "", raw)
    return raw or ""

def _ensure_tb_table_name(name: str) -> str:
    low = _snake(name)
    low = re.sub(r'[^A-Za-z0-9_]+', '_', low).strip('_').lower()
    if not low:
        return 'tb_item'
    if low in {'tb', 'tb_'}:
        return 'tb_item'
    if low.startswith('tb_'):
        return low
    return f'tb_{low}'

def _camel_from_snake(s: str) -> str:
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", s or "") if p]
    if not parts:
        return "item"
    head = parts[0].lower()
    tail_parts: List[str] = []
    for token in parts[1:]:
        piece = str(token or "").strip()
        if not piece:
            continue
        if piece.isdigit():
            tail_parts.append("_" + piece)
        else:
            tail_parts.append(piece[:1].upper() + piece[1:])
    return head + "".join(tail_parts)

def _pascal_entity_name(entity: str) -> str:
    entity = _strip_logical_tb_prefix(entity) or (entity or "")
    cleaned = re.sub(r"[^A-Za-z0-9_]+", " ", (entity or "")).strip()
    if not cleaned:
        return "Item"
    snake = _snake(cleaned)
    parts = [part for part in snake.split('_') if part]
    if not parts:
        return "Item"
    return "".join(part[:1].upper() + part[1:] for part in parts)

def _entity_var(entity: str) -> str:
    entity = re.sub(r"[^A-Za-z0-9_]", "", entity or "").strip()
    if not entity:
        return "item"
    if entity.isupper():
        return entity.lower()
    m = re.match(r"^([A-Z]{2,})([A-Z][a-z].*)$", entity)
    if m:
        return m.group(1).lower() + m.group(2)
    return entity[:1].lower() + entity[1:]

def _append_segment_once(base: str, segment: str, sep: str = ".") -> str:
    base = (base or "").strip(sep)
    segment = (segment or "").strip(sep)
    if not segment:
        return base
    if not base:
        return segment
    base_parts = [part for part in base.split(sep) if part]
    seg_parts = [part for part in segment.split(sep) if part]
    if not seg_parts:
        return base
    if base_parts and base_parts[-1] == seg_parts[0]:
        return sep.join(base_parts + seg_parts[1:])
    return sep.join(base_parts + seg_parts)

def _is_generic_entity_var(ev: str) -> bool:
    return (ev or '').lower() in {"ui", "screen", "page", "view", "app", "main", "home", "form"}

def infer_entity_from_plan(plan: Dict) -> str:
    tasks = plan.get("tasks") or []
    for t in tasks:
        p = (t.get("path") or "").replace("\\", "/")
        name = p.split("/")[-1]
        for suf in ("VO.java", "ServiceImpl.java", "Service.java", "RestController.java", "Controller.java", "Mapper.java", "Mapper.xml"):
            if name.endswith(suf) and len(name) > len(suf):
                return name[:-len(suf)]
    return ""

def _iter_text_blobs(source: Any) -> Iterable[str]:
    if isinstance(source, dict):
        for key in ("purpose", "content", "path", "sql", "ddl", "description", "name", "requirements_text", "schema_text"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                yield value
        inputs = source.get("inputs")
        if isinstance(inputs, dict):
            yield from _iter_text_blobs(inputs)
        domains = source.get("domains")
        if isinstance(domains, list):
            for item in domains:
                yield from _iter_text_blobs(item)
        tasks = source.get("tasks")
        if isinstance(tasks, list):
            for item in tasks:
                yield from _iter_text_blobs(item)
        db_ops = source.get("db_ops")
        if isinstance(db_ops, list):
            for item in db_ops:
                yield from _iter_text_blobs(item)
    elif isinstance(source, list):
        for item in source:
            yield from _iter_text_blobs(item)
    elif isinstance(source, str):
        if source.strip():
            yield source

def _split_csv_like(text: str) -> List[str]:
    return [p.strip() for p in re.split(r"[,/\n\r\t]+", text or "") if p.strip()]


def _contains_explicit_column_contract(text: str) -> bool:
    body = text or ''
    if re.search(r'(?:fields?|columns?|column\s*definitions?|컬럼정의|필드정의|컬럼|필드|항목)\s*[:：]', body, re.IGNORECASE):
        return True
    return bool(re.search(r'(?:최소\s*)?(?:컬럼정의|필드정의|컬럼|필드|항목).*(?:아래|다음|사용|포함)', body, re.IGNORECASE))


def _table_identifier_to_entity_token(identifier: str) -> str:
    raw = re.sub(r'[^A-Za-z0-9_]+', '', str(identifier or '').strip())
    if not raw:
        return ''
    low = raw.lower()
    if low in {'tb', 'tb_'}:
        return ''
    if low.startswith('tb_') and len(raw) > 3:
        raw = raw[3:]
    raw = re.sub(r'^_+', '', raw)
    if not raw:
        return ''
    return raw


def _extract_explicit_table_name(text: str) -> str:
    body = text or ''
    patterns = (
        r"(?:table\s*name|table|테이블\s*이름|테이블명|테이블)\s*(?:은|는|:|=)?\s*(?:(?:[-*•]|\d+[\.)])\s*)?[`\'\"]?([A-Za-z_][\w]*)[`\'\"]?",
        r"^[ \t]*(?:table\s*name|table|테이블\s*이름|테이블명|테이블)\s*[:：=][ \t]*(?:(?:[-*•]|\d+[\.)])\s*)?[`\'\"]?([A-Za-z_][\w]*)[`\'\"]?[ \t]*$",
    )
    for pat in patterns:
        for match in re.finditer(pat, body, re.IGNORECASE | re.MULTILINE):
            candidate = (match.group(1) or '').strip().lower()
            if candidate in {'if', 'exists'}:
                continue
            prefix = body[max(0, match.start() - 16):match.start()].lower()
            if 'create' in prefix and 'table' in prefix:
                continue
            return candidate
    lines = [line.strip() for line in body.splitlines() if line and line.strip()]
    for idx, line in enumerate(lines):
        if re.match(r"^(?:table\s*name|table|테이블\s*이름|테이블명|테이블)\s*[:：=]?\s*$", line, re.IGNORECASE):
            if idx + 1 < len(lines):
                nxt = lines[idx + 1].strip()
                bullet = re.match(r"^(?:[-*•]|\d+[\.)])\s*[`\'\"]?([A-Za-z_][\w]*)[`\'\"]?\s*$", nxt)
                if bullet:
                    return (bullet.group(1) or '').strip().lower()
    return ''


def _normalize_explicit_sql_type(segment: str) -> str:
    raw = str(segment or '').strip().strip("`\"'")
    if not raw:
        return ''
    compact = re.sub(r'\s+', ' ', raw).strip()
    low = compact.lower()
    aliases = {
        'string': 'VARCHAR(255)',
        'varchar': 'VARCHAR(255)',
        'text': 'TEXT',
        'clob': 'TEXT',
        'long': 'BIGINT',
        'bigint': 'BIGINT',
        'int': 'INT',
        'integer': 'INT',
        'smallint': 'INT',
        'tinyint': 'INT',
        'datetime': 'DATETIME',
        'timestamp': 'DATETIME',
        'date': 'DATE',
        'boolean': 'BOOLEAN',
        'bool': 'BOOLEAN',
    }
    if low in aliases:
        return aliases[low]
    if re.fullmatch(r'(?:var)?char\s*\(\s*\d+\s*\)', low):
        return re.sub(r'\s+', '', compact).upper()
    if re.fullmatch(r'(?:decimal|numeric)\s*\(\s*\d+\s*,\s*\d+\s*\)', low):
        return re.sub(r'\s+', '', compact).upper()
    if re.fullmatch(r'(?:bigint|int|integer|smallint|tinyint|text|date|datetime|timestamp|boolean|bool)', low):
        return compact.upper().replace('BOOL', 'BOOLEAN')
    return ''


def _extract_explicit_reference(value: str) -> Optional[Tuple[str, str]]:
    raw = str(value or '').strip().strip("`\"'")
    if not raw:
        return None
    patterns = (
        r"(?:foreign\s+key|fk|references?)\s*[:：]?\s*[`\"']?([A-Za-z_][\w]*)[`\"']?\s*(?:\.|\()\s*[`\"']?([A-Za-z_][\w]*)[`\"']?\s*\)?",
        r"^[`\"']?([A-Za-z_][\w]*)[`\"']?\s*(?:\.|\()\s*[`\"']?([A-Za-z_][\w]*)[`\"']?\s*\)?$",
    )
    for pat in patterns:
        m = re.search(pat, raw, re.IGNORECASE)
        if not m:
            continue
        ref_table = str(m.group(1) or '').strip()
        ref_col = str(m.group(2) or '').strip()
        if ref_table and ref_col:
            return ref_table, ref_col
    return None


def _has_shared_auth_table_request(source: Any) -> bool:
    joined = '\n'.join(_iter_text_blobs(source)).lower()
    if not joined.strip():
        return False
    loginish = any(tok in joined for tok in ('로그인', 'login', 'signin', 'sign in', 'auth'))
    signupish = any(tok in joined for tok in ('회원가입', 'signup', 'sign up', 'register', 'registration', 'join'))
    manageish = any(tok in joined for tok in ('회원관리', '사용자관리', 'member management', 'user management', '가입회원관리'))
    sharedish = any(tok in joined for tok in (
        '같은 테이블', '동일 테이블', '하나의 테이블', '단일 테이블', '같은 회원 테이블',
        '회원가입한 계정으로 로그인', '회원가입 후 로그인', '기존 로그인과 연동', '로그인과 연동',
        '같은 컬럼 체계', '동일 컬럼 체계', '하나의 계정 체계', '통합된 계정 구조',
    ))
    return sharedish or (loginish and signupish and manageish)


def _parse_explicit_field_tail(token: str, tail: str) -> Dict[str, Any]:
    if _is_disallowed_schema_contract_token(token, tail):
        return {
            'prop': '',
            'col': '',
            'java_type': 'String',
            'db_type': '',
            'comment': '',
            'default': '',
            'pk': False,
            'nullable': None,
            'unique': False,
            'auto_increment': False,
            'references': None,
        }
    col = _snake(token)
    prop = _camel_from_snake(token)
    meta: Dict[str, Any] = {
        'prop': prop,
        'col': col,
        'java_type': _guess_java_type(prop, col),
        'db_type': '',
        'comment': '',
        'default': '',
        'pk': False,
        'nullable': None,
        'unique': False,
        'auto_increment': False,
        'references': None,
    }
    raw_tail = str(tail or '').strip()
    if not raw_tail:
        return meta
    labeled = re.match(r'^(타입|type|제약|constraint|기본값|default|comment|코멘트|설명)\s*[:：]\s*(.+)$', raw_tail, re.IGNORECASE)
    if labeled:
        label_low = labeled.group(1).strip().lower()
        label_value = labeled.group(2).strip()
        if label_low in {'기본값', 'default'}:
            meta['default'] = label_value
            return meta
        if label_low in {'comment', '코멘트', '설명'}:
            meta['comment'] = label_value
            return meta
        if label_low in {'타입', 'type'}:
            sql_type = _normalize_explicit_sql_type(label_value)
            if sql_type:
                meta['db_type'] = sql_type
                meta['java_type'] = _java_type_from_sql_type(sql_type, col)
            return meta
        if label_low in {'제약', 'constraint'}:
            inner = label_value
        else:
            inner = raw_tail
    else:
        inner = raw_tail
    if (raw_tail.startswith('(') and raw_tail.endswith(')')) or (raw_tail.startswith('（') and raw_tail.endswith('）')):
        inner = raw_tail[1:-1].strip()
    elif ':' in raw_tail:
        inner = raw_tail.split(':', 1)[1].strip()
    elif '|' in raw_tail:
        inner = raw_tail.split('|', 1)[1].strip()
    else:
        paren = None
        trimmed = raw_tail.lstrip()
        if trimmed.startswith('(') or trimmed.startswith('（'):
            paren = re.search(r"[\(（]\s*(.+?)\s*[\)）]", raw_tail)
        if paren:
            inner = paren.group(1).strip()
    segments = [seg.strip() for seg in re.split(r'[,/|]', inner) if seg and seg.strip()]
    for segment in segments:
        raw_segment = segment.strip()
        low = raw_segment.lower()
        normalized_value = raw_segment
        if ':' in raw_segment:
            _, normalized_value = raw_segment.split(':', 1)
            normalized_value = normalized_value.strip()
            low = normalized_value.lower()
        elif '：' in raw_segment:
            _, normalized_value = raw_segment.split('：', 1)
            normalized_value = normalized_value.strip()
            low = normalized_value.lower()
        sql_type = _normalize_explicit_sql_type(normalized_value)
        if sql_type:
            meta['db_type'] = sql_type
            meta['java_type'] = _java_type_from_sql_type(sql_type, col)
            continue
        if any(token in low for token in ('primary key', 'primarykey', '기본키', '주키')) or low in {'pk'}:
            meta['pk'] = True
            meta['nullable'] = False
            continue
        if 'auto increment' in low or 'auto_increment' in low or 'autoincrement' in low or '자동증가' in low:
            meta['auto_increment'] = True
            meta['nullable'] = False
            if not meta['db_type']:
                meta['db_type'] = 'BIGINT'
                meta['java_type'] = _java_type_from_sql_type(meta['db_type'], col)
            continue
        if 'not null' in low or 'required' in low or '필수' in low or 'null 아님' in low:
            meta['nullable'] = False
            continue
        if 'nullable' in low or 'null 허용' in low or '옵션' in low:
            meta['nullable'] = True
            continue
        if 'unique' in low or '중복불가' in low or '유니크' in low:
            meta['unique'] = True
            continue
        if 'default' in raw_segment.lower() or '기본값' in raw_segment:
            default_value = normalized_value.strip()
            if default_value:
                meta['default'] = default_value
            continue
        reference = _extract_explicit_reference(raw_segment) or _extract_explicit_reference(normalized_value)
        if reference:
            meta['references'] = reference
            continue
        if 'comment' in raw_segment.lower() or '설명' in raw_segment or '코멘트' in raw_segment or '주석' in raw_segment:
            if normalized_value:
                meta['comment'] = normalized_value.strip()
            continue
        if not meta['comment']:
            meta['comment'] = normalized_value.strip()
    if not meta['db_type'] and meta['auto_increment']:
        meta['db_type'] = 'BIGINT'
        meta['java_type'] = _java_type_from_sql_type(meta['db_type'], col)
    return meta



def _extract_explicit_table_comment(text: str) -> str:
    body = text or ''
    lines = [line.strip() for line in body.splitlines() if line and line.strip()]
    pattern = re.compile(r'^(?:테이블\s*(?:설명|코멘트)|table\s*description|table\s*comment)(?:\s*\(comment\))?\s*[:：-]?\s*(.*)$', re.IGNORECASE)
    for idx, line in enumerate(lines):
        m = pattern.match(line)
        if not m:
            continue
        value = (m.group(1) or '').strip().strip("`\"'")
        if value and value not in {':', '-'}:
            return value
        if idx + 1 < len(lines):
            nxt = lines[idx + 1].strip()
            bullet = re.match(r"^(?:[-*•]|\d+[\.)])\s*(.+)$", nxt)
            if bullet:
                candidate = bullet.group(1).strip().strip("`\"'")
                if candidate:
                    return candidate
        return ''
    return ''


def _collect_requirement_table_comment(source: Any) -> str:
    for text in _iter_text_blobs(source):
        value = _extract_explicit_table_comment(text)
        if value:
            return value
    return ''


def _merge_entry_meta(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in (updates or {}).items():
        if key in {'prop', 'col'}:
            continue
        if value is None:
            continue
        if key in {'pk', 'unique', 'auto_increment'}:
            if value:
                merged[key] = True
            continue
        if key == 'nullable':
            if value is not None:
                merged[key] = value
            continue
        if key == 'references':
            if value:
                merged[key] = value
            continue
        if str(value).strip():
            merged[key] = value
    return merged


def _looks_like_explicit_field_bullet_tail(token: str, tail: str) -> bool:
    raw_tail = str(tail or '').strip()
    if not raw_tail:
        return True
    trimmed = raw_tail.lstrip()
    if trimmed[:1] in {':', '-', '|', '(', '（'}:
        return True
    low = raw_tail.lower()
    metadata_markers = (
        'type', '타입', 'constraint', '제약', 'comment', '코멘트', '설명', '기본값', 'default',
        'primary key', 'pk', '기본키', 'not null', 'nullable', 'unique', '유니크', '중복불가', 'auto increment', '자동증가',
        'varchar', 'char(', 'text', 'clob', 'bigint', 'int', 'integer', 'datetime', 'timestamp', 'date', 'boolean', 'bool',
    )
    if any(marker in low for marker in metadata_markers):
        return True
    if re.search(r'[:：|,/()]', raw_tail):
        return True
    token_low = str(token or '').strip().lower()
    if token_low in {'id', 'idx', 'no', 'seq', 'pk'} and len(raw_tail.split()) >= 3:
        return False
    if re.search(r'[가-힣]{2,}\s+[가-힣]{2,}', raw_tail):
        return False
    if len(raw_tail.split()) >= 4:
        return False
    return True


def _extract_explicit_requirement_field_entries(text: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _push_meta(meta: Dict[str, Any]) -> None:
        col = str(meta.get('col') or '').strip().lower()
        prop = str(meta.get('prop') or '').strip()
        if _is_disallowed_schema_contract_token(col):
            return
        if not col or not prop or not _is_valid_java_identifier(prop) or not _is_valid_column_identifier(col):
            return
        if col in seen:
            idx = next((i for i, item in enumerate(entries) if str(item.get('col') or '').strip().lower() == col), None)
            if idx is not None:
                entries[idx] = _merge_entry_meta(entries[idx], meta)
            return
        seen.add(col)
        entries.append(meta)

    body = text or ''
    field_line_pat = re.compile(r"(?:(?<=^)|(?<=\n))\s*(?:fields?|columns?|column\s*definitions?|컬럼정의|필드정의|컬럼|필드|항목)(?:\s*(?:목록|리스트))?\s*[:：]\s*([A-Za-z0-9_,\s|`'\"]+)", re.IGNORECASE)
    for match in field_line_pat.finditer(body):
        if _is_css_noise_fragment(match.group(0)):
            continue
        chunk = match.group(1)
        for token in _split_csv_like(chunk.replace("|", ",")):
            cleaned = re.sub(r"^[`\'\"]|[`\'\"]$", "", token.strip())
            if re.fullmatch(r"[`\'\"]?[A-Za-z_][A-Za-z0-9_]*[`\'\"]?", cleaned):
                _push_meta(_parse_explicit_field_tail(cleaned, ""))

    lines = [line.rstrip() for line in body.splitlines()]
    collecting = False
    current_idx: Optional[int] = None
    for raw in lines:
        line = raw.strip()
        if not line:
            if collecting:
                current_idx = None
                continue
            collecting = False
            current_idx = None
        if re.search(r"(?:최소\s*)?(?:컬럼정의|필드정의|컬럼|필드|항목).*(?:아래|다음|사용|포함)", line, re.IGNORECASE) or re.search(r"^(?:[-*•]\s*)?(?:fields?|columns?|column\s*definitions?|컬럼정의|필드정의|컬럼\s*명?|필드|항목)(?:\s*(?:목록|리스트))?\s*[:：]?$", line, re.IGNORECASE):
            collecting = True
            current_idx = None
            continue
        if not collecting:
            continue
        nested = re.match(r"^(?:[-*•])\s*(타입|type|제약|constraint|기본값|default|comment|코멘트|설명)\s*[:：]\s*(.+)$", line, re.IGNORECASE)
        if nested and current_idx is not None:
            token = str(entries[current_idx].get('col') or '')
            meta = _parse_explicit_field_tail(token, f"{nested.group(1)}: {nested.group(2)}")
            entries[current_idx] = _merge_entry_meta(entries[current_idx], meta)
            continue
        field_bullet = re.match(r"^(?:[-*•]|\d+[\.)])\s*[`'\"]?([A-Za-z_][A-Za-z0-9_]*)[`'\"]?\s*(.*)$", line)
        if field_bullet:
            if _is_disallowed_schema_contract_token(field_bullet.group(1), field_bullet.group(2) or ''):
                continue
            token_name = str(field_bullet.group(1) or '').strip().lower()
            if token_name in {'type', 'constraint', 'default', 'comment'}:
                if current_idx is not None:
                    token = str(entries[current_idx].get('col') or '')
                    meta = _parse_explicit_field_tail(token, field_bullet.group(0))
                    entries[current_idx] = _merge_entry_meta(entries[current_idx], meta)
                    continue
                collecting = False
                current_idx = None
                continue
            if not _looks_like_explicit_field_bullet_tail(field_bullet.group(1), field_bullet.group(2) or ''):
                collecting = False
                current_idx = None
                continue
            meta = _parse_explicit_field_tail(field_bullet.group(1), field_bullet.group(2) or '')
            _push_meta(meta)
            current_idx = next((i for i, item in enumerate(entries) if str(item.get('col') or '').strip().lower() == str(meta.get('col') or '').strip().lower()), None)
            continue
        if re.fullmatch(r"[`'\"]?[A-Za-z_][A-Za-z0-9_]*[`'\"]?", line):
            if _is_disallowed_schema_contract_token(line.strip("`\'\"")):
                continue
            meta = _parse_explicit_field_tail(line.strip("`\'\""), "")
            _push_meta(meta)
            current_idx = next((i for i, item in enumerate(entries) if str(item.get('col') or '').strip().lower() == str(meta.get('col') or '').strip().lower()), None)
            continue
        collecting = False
        current_idx = None
    return entries

def _extract_explicit_requirement_field_specs(text: str) -> List[Tuple[str, str, str]]:
    return [
        (str(entry.get('prop') or ''), str(entry.get('col') or ''), str(entry.get('java_type') or 'String'))
        for entry in _extract_explicit_requirement_field_entries(text)
        if entry.get('prop') and entry.get('col')
    ]


def _extract_explicit_requirement_field_comments(text: str) -> Dict[str, str]:
    comments: Dict[str, str] = {}
    for entry in _extract_explicit_requirement_field_entries(text):
        col = str(entry.get('col') or '').strip().lower()
        comment = str(entry.get('comment') or '').strip()
        if col and comment:
            comments[col] = comment
    return comments


def _collect_requirement_field_comments(source: Any) -> Dict[str, str]:
    merged: Dict[str, str] = {}
    for text in _iter_text_blobs(source):
        for col, comment in _extract_explicit_requirement_field_comments(text).items():
            if col and comment and col not in merged:
                merged[col] = comment
    return merged


def _collect_requirement_field_metadata(source: Any) -> Dict[str, Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for text in _iter_text_blobs(source):
        for entry in _extract_explicit_requirement_field_entries(text):
            col = str(entry.get('col') or '').strip().lower()
            if col and col not in merged:
                merged[col] = dict(entry)
    return merged

def _target_contract_tokens(entity: str = '', table: str = '') -> List[str]:
    tokens: List[str] = []
    if table:
        tokens.append((table or '').strip().lower())
    if entity:
        entity_norm = re.sub(r"[^A-Za-z0-9_]", "", entity or "").strip()
        if entity_norm:
            tokens.append(entity_norm.lower())
            entity_table = _snake(entity_norm).lower()
            if entity_table not in tokens:
                tokens.append(entity_table)
    return [token for token in dict.fromkeys(tokens) if token]


def _text_contains_target_token(text: str, tokens: List[str]) -> bool:
    if not tokens:
        return False
    low = (text or '').lower()
    for token in tokens:
        if not token:
            continue
        if re.search(rf'\b{re.escape(token)}\b', low):
            return True
    return False


def _extract_explicit_contract_for_target(text: str, entity: str = '', table: str = '') -> Tuple[str, List[Tuple[str, str, str]], List[Dict[str, Any]]]:
    body = text or ''
    tokens = _target_contract_tokens(entity, table)
    if not body.strip():
        return '', [], []

    paragraphs = [part.strip() for part in re.split(r'\n\s*\n', body) if part and part.strip()]
    sections = paragraphs
    best_score = -10**9
    best_table = ''
    best_specs: List[Tuple[str, str, str]] = []
    best_entries: List[Dict[str, Any]] = []

    for paragraph in sections:
        has_contract = _contains_explicit_column_contract(paragraph)
        if not has_contract and not _extract_explicit_table_name(paragraph):
            continue
        entries = _extract_explicit_requirement_field_entries(paragraph) if has_contract else []
        specs = [(str(e.get('prop') or ''), str(e.get('col') or ''), str(e.get('java_type') or 'String')) for e in entries if e.get('prop') and e.get('col') and not _is_disallowed_schema_contract_token(str(e.get('col') or ''))]
        para_table = _extract_explicit_table_name(paragraph)
        score = 0
        if para_table:
            if para_table.lower() in tokens:
                score += 6
            elif tokens:
                score -= 3
        if _text_contains_target_token(paragraph, tokens):
            score += 3
        if has_contract:
            score += 4
        if specs:
            score += len(specs)
        if tokens and not _text_contains_target_token(paragraph, tokens) and para_table and para_table.lower() not in tokens:
            score -= 6
        if specs and score > best_score:
            best_score = score
            best_table = para_table
            best_specs = specs
            best_entries = entries

    entries = _extract_explicit_requirement_field_entries(body)
    specs = [(str(e.get('prop') or ''), str(e.get('col') or ''), str(e.get('java_type') or 'String')) for e in entries if e.get('prop') and e.get('col') and not _is_disallowed_schema_contract_token(str(e.get('col') or ''))]
    body_table = _extract_explicit_table_name(body) if specs else ''
    if specs and body_table and (not best_table or body_table != best_table):
        return body_table, specs, entries
    if specs and (
        not best_specs
        or (body_table and best_table and body_table == best_table and len(specs) > len(best_specs))
        or (not best_table and len(specs) > len(best_specs))
    ):
        return body_table, specs, entries
    if best_specs and best_score >= 4:
        return best_table, best_specs, best_entries
    return body_table, specs, entries


def _singularize_token(token: str) -> str:
    value = re.sub(r'[^A-Za-z0-9_]+', '_', (token or '').strip()).strip('_').lower()
    if value.endswith('ies'):
        return value[:-3] + 'y'
    if value.endswith('ses') and len(value) > 3:
        return value[:-2]
    if value.endswith('s') and not value.endswith('ss'):
        return value[:-1]
    return value


def _entity_name_from_table_name(table_name: str) -> str:
    normalized_table = re.sub(r'^(?:tb|tbl|t)_', '', str(table_name or '').strip(), flags=re.IGNORECASE)
    parts = [part for part in re.split(r'[^A-Za-z0-9]+', normalized_table or '') if part]
    if not parts:
        return 'Item'
    normalized: List[str] = []
    for idx, part in enumerate(parts):
        token = _singularize_token(part) if idx == len(parts) - 1 else re.sub(r'[^A-Za-z0-9_]+', '', part).lower()
        token = token or re.sub(r'[^A-Za-z0-9_]+', '', part).lower()
        if token:
            normalized.append(token[:1].upper() + token[1:])
    return ''.join(normalized) or 'Item'


def _should_collapse_explicit_auth_entity(entity_name: str, table_name: str, paragraph: str) -> bool:
    entity_low = str(entity_name or '').strip().lower()
    table_low = str(table_name or '').strip().lower()
    if any(token in entity_low or token in table_low for token in ('login', 'auth', 'signin', 'sign_in', 'logout', 'session', 'jwt', 'cert', 'integrated', 'sso')):
        return True
    blob = str(paragraph or '').lower()
    explicit_phrases = (
        '로그인 테이블', '로그인 기능', '인증 테이블', '인증 기능',
        'sign in table', 'login table', 'authentication table', 'auth table',
    )
    return any(phrase in blob for phrase in explicit_phrases)


def _dedupe_field_specs(specs: List[Tuple[str, str, str]]) -> List[Tuple[str, str, str]]:
    out: List[Tuple[str, str, str]] = []
    seen: set[str] = set()
    for prop, col, jt in specs or []:
        key = (col or prop or '').strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append((prop, col, jt))
    return out


def extract_explicit_requirement_schemas(requirements_text: str) -> Dict[str, Schema]:
    body = str(requirements_text or '').strip()
    if not body:
        return {}
    paragraphs = [part.strip() for part in re.split(r'\n\s*\n', body) if part and part.strip()]
    db_rule_sections = [part.strip() for part in re.split(r'(?=^\s*DB\s*규칙\s*:)', body, flags=re.IGNORECASE | re.MULTILINE) if part and part.strip()]
    sections = db_rule_sections if len(db_rule_sections) > 1 else paragraphs
    out: Dict[str, Schema] = {}
    for paragraph in sections:
        table_name = _extract_explicit_table_name(paragraph)
        entries = _extract_explicit_requirement_field_entries(paragraph)
        specs = [(str(e.get('prop') or ''), str(e.get('col') or ''), str(e.get('java_type') or 'String')) for e in entries if e.get('prop') and e.get('col') and not _is_disallowed_schema_contract_token(str(e.get('col') or ''))]
        if not table_name or not specs:
            continue
        entity_name = _entity_name_from_table_name(table_name)
        entity_name = _canonical_userish_entity(entity_name, table_name, paragraph)
        field_columns = {col.lower() for _prop, col, _jt in specs}
        looks_like_auth_contract = ({'login_id', 'password'}.issubset(field_columns) or {'login_id', 'login_password'}.issubset(field_columns) or {'user_id', 'password'}.issubset(field_columns))
        signup_management = _is_signup_management_request(paragraph, entity_name, table_name)
        explicit_auth_request = _has_explicit_auth_creation_request(paragraph)
        shared_auth_table = _has_shared_auth_table_request(paragraph)
        feature_kind = _feature_kind_hint_from_entity_or_table(entity_name, table_name, classify_feature_kind(paragraph, entity=entity_name))
        if looks_like_auth_contract and explicit_auth_request and not signup_management and not shared_auth_table:
            feature_kind = FEATURE_KIND_AUTH
            entity_name = 'Login'
        elif shared_auth_table and looks_like_auth_contract:
            feature_kind = FEATURE_KIND_CRUD
        unified_auth, cert_login, jwt_login = _auth_options_from_sources(paragraph, feature_kind)
        if is_auth_kind(feature_kind):
            if not signup_management and (explicit_auth_request or _should_collapse_explicit_auth_entity(entity_name, table_name, paragraph)):
                entity_name = 'Login'
                feature_kind = FEATURE_KIND_AUTH
            else:
                feature_kind = FEATURE_KIND_CRUD
        field_meta = {str(entry.get('col') or '').strip().lower(): entry for entry in entries if str(entry.get('col') or '').strip()}
        schema = schema_for(
            entity_name,
            inferred_fields=_dedupe_field_specs(specs),
            table=table_name,
            feature_kind=feature_kind,
            strict_fields=True,
            unified_auth=unified_auth,
            cert_login=cert_login,
            jwt_login=jwt_login,
            field_comments={col: str(meta.get('comment') or '').strip() for col, meta in field_meta.items() if str(meta.get('comment') or '').strip()},
            field_db_types={col: str(meta.get('db_type') or '').strip() for col, meta in field_meta.items() if str(meta.get('db_type') or '').strip()},
            field_nullable={col: meta.get('nullable') for col, meta in field_meta.items() if meta.get('nullable') is not None},
            field_unique={col: bool(meta.get('unique')) for col, meta in field_meta.items() if meta.get('unique')},
            field_auto_increment={col: bool(meta.get('auto_increment')) for col, meta in field_meta.items() if meta.get('auto_increment')},
            field_defaults={col: str(meta.get('default') or '').strip() for col, meta in field_meta.items() if str(meta.get('default') or '').strip()},
            table_comment=_extract_explicit_table_comment(paragraph),
            db_vendor=_database_vendor_from_source(paragraph),
        )
        schema.authority = 'explicit'
        existing = out.get(entity_name)
        if existing is None or len(getattr(schema, 'fields', []) or []) > len(getattr(existing, 'fields', []) or []):
            out[entity_name] = schema
    return out



def _mapper_table_names_from_text(text: str) -> List[str]:
    body = text or ""
    names: List[str] = []
    seen: set[str] = set()
    patterns = (
        r'insert\s+into\s+[`"]?([A-Za-z_][\w]*)[`"]?',
        r'update\s+[`"]?([A-Za-z_][\w]*)[`"]?',
        r'delete\s+from\s+[`"]?([A-Za-z_][\w]*)[`"]?',
        r'from\s+[`"]?([A-Za-z_][\w]*)[`"]?',
    )
    for pattern in patterns:
        for match in re.finditer(pattern, body, re.IGNORECASE):
            name = (match.group(1) or '').strip().lower()
            if not name or name in seen:
                continue
            seen.add(name)
            names.append(name)
    return names


def _authoritative_mapper_contract(sources: Any, table: str = '', entity: str = '') -> Tuple[str, List[Tuple[str, str, str]]]:
    desired_names: List[str] = []
    if table:
        desired_names.append((table or '').strip().lower())
    entity_table = _snake(entity) if entity else ''
    if entity_table and entity_table not in desired_names:
        desired_names.append(entity_table)

    preferred_texts: List[str] = []
    fallback_texts: List[str] = []
    iterable = sources if isinstance(sources, list) else ([sources] if isinstance(sources, dict) else [])
    entity_low = (entity or '').strip().lower()

    for item in iterable:
        if not isinstance(item, dict):
            continue
        content = item.get('content') or item.get('sql') or item.get('ddl') or ''
        if not isinstance(content, str) or not content.strip():
            continue
        path = str(item.get('path') or '').replace('\\', '/').lower()
        is_mapper = path.endswith('mapper.xml') or '<mapper' in content.lower()
        if not is_mapper:
            continue
        if entity_low and entity_low not in {'', 'item', 'entity', 'domain', 'record', 'data'} and entity_low in Path(path).stem.lower():
            preferred_texts.append(content)
        else:
            fallback_texts.append(content)

    for text in preferred_texts + fallback_texts:
        specs = _extract_field_specs(text)
        table_names = _mapper_table_names_from_text(text)
        chosen = ''
        for name in table_names:
            if name in desired_names:
                chosen = name
                break
        if not chosen and len(set(table_names)) == 1:
            chosen = table_names[0]
        if specs and (chosen or (desired_names and not table_names)):
            return chosen or (desired_names[0] if desired_names else ''), _normalize_fields(specs)
        if chosen:
            return chosen, []
    return '', []


def _normalized_name(prop: str = '', column: str = '') -> str:
    return re.sub(r'[^a-z0-9]+', '_', (prop or column or '').lower())


def _is_yn_field(prop: str = '', column: str = '') -> bool:
    normalized = _normalized_name(prop, column)
    return normalized.endswith('_yn') or normalized.endswith('yn') or normalized in {'yn', 'use_yn', 'all_day_yn'}


def _is_date_only_name(prop: str = '', column: str = '') -> bool:
    normalized = _normalized_name(prop, column)
    if not normalized:
        return False
    if any(token in normalized for token in ('datetime', 'date_time', 'timestamp', 'time_stamp')):
        return False
    if normalized.endswith('_dt') or normalized.endswith('dt'):
        return False
    if normalized.endswith('_time') or normalized == 'time' or (normalized.endswith('time') and 'update_time' not in normalized):
        return False
    return normalized.endswith('_date') or normalized == 'date' or normalized.endswith('date')


def _is_datetime_name(prop: str = '', column: str = '') -> bool:
    normalized = _normalized_name(prop, column)
    if not normalized:
        return False
    if any(token in normalized for token in ('datetime', 'date_time', 'timestamp', 'time_stamp')):
        return True
    if normalized.endswith('_dt') or normalized.endswith('dt'):
        return True
    if normalized.endswith('_time') or normalized == 'time' or (normalized.endswith('time') and 'update_time' not in normalized):
        return True
    if normalized.endswith('at') and any(token in normalized for token in ('created', 'updated', 'deleted', 'start', 'end', 'reg', 'mod')):
        return True
    return False


def _is_date_java_type(java_type: str) -> bool:
    return (java_type or '').strip() in {'Date', 'java.util.Date', 'java.time.LocalDate', 'LocalDate', 'java.time.LocalDateTime', 'LocalDateTime'}


def _date_pattern_for_field(prop: str, column: str = '') -> str:
    return 'yyyy-MM-dd' if _is_date_only_name(prop, column) else "yyyy-MM-dd'T'HH:mm:ss"


def _is_datetime_field(prop: str, column: str, java_type: str = '') -> bool:
    jt = (java_type or '').strip()
    return jt in {'java.time.LocalDateTime', 'LocalDateTime'} or (_is_date_java_type(jt) and not _is_date_only_name(prop, column)) or _is_datetime_name(prop, column)

def _java_type_from_sql_type(sql_type: str, field_name: str) -> str:
    s = (sql_type or "").lower()
    f = (field_name or "").lower()
    if _is_yn_field(f, f):
        return "String"
    if _is_id_like(f, f):
        return "String"
    if any(token in s for token in ("date", "timestamp", "datetime", "time")):
        return "String"
    if "bigint" in s:
        return "String" if _is_id_like(f, f) else "Long"
    if any(token in s for token in ("int", "integer", "smallint", "tinyint")):
        return "String" if _is_id_like(f, f) else "Integer"
    if any(token in s for token in ("decimal", "numeric", "double", "float")):
        return "java.math.BigDecimal"
    if any(token in s for token in ("bool", "bit")):
        return "String" if _is_yn_field(f, f) else "Boolean"
    if f.endswith("at") and f[:-2].endswith("created"):
        return "String"
    return "String"

def _guess_java_type(prop: str, column: str) -> str:
    name = (prop or column or "").lower()
    normalized = re.sub(r'[^a-z0-9]+', '_', name)
    if _is_yn_field(prop, column):
        return "String"
    if name == "id":
        return "String"
    if name.endswith("id") or name.endswith("_id"):
        return "String"
    if any(token in normalized for token in ("created_at", "updated_at", "deleted_at", "reg_date", "createdat", "updatedat", "deletedat", "regdate")):
        return "String"
    if _is_datetime_name(prop, column):
        return "String"
    if _is_date_only_name(prop, column):
        return "String"
    return "String"

def _is_id_like(prop: str = '', column: str = '') -> bool:
    normalized = _normalized_name(prop, column)
    if not normalized:
        return False
    return normalized == 'id' or normalized.endswith('_id') or normalized.endswith('id')

def _is_temporal_field(prop: str = '', column: str = '', java_type: str = '') -> bool:
    return _is_datetime_name(prop, column) or _is_date_only_name(prop, column) or _is_date_java_type(java_type)

def _date_format_pattern(prop: str, column: str = '') -> str:
    return '%Y-%m-%d' if _is_date_only_name(prop, column) else '%Y-%m-%dT%H:%i'

def _temporal_parse_pattern(prop: str, column: str = '') -> str:
    return '%Y-%m-%d' if _is_date_only_name(prop, column) else '%Y-%m-%dT%H:%i'

def _temporal_select_expr(prop: str, column: str) -> str:
    return f"DATE_FORMAT({column}, '{_date_format_pattern(prop, column)}') AS {column}"

def _temporal_write_value_expr(prop: str, column: str) -> str:
    pattern = _temporal_parse_pattern(prop, column)
    return f"STR_TO_DATE(NULLIF(REPLACE(#{{{prop}}}, 'T', ' '), ''), '{pattern}')"

def _authoritative_analysis_field_specs(source: Any, entity: str) -> List[Tuple[str, str, str]]:
    target = (entity or '').strip().lower()
    if not target:
        return []

    def _from_domain(domain: Dict[str, Any]) -> List[Tuple[str, str, str]]:
        name = (domain.get('name') or domain.get('entity_name') or '').strip().lower()
        table = (domain.get('source_table') or '').strip().lower()
        entity_name = (domain.get('entity_name') or '').strip().lower()
        if target not in {name, table, entity_name}:
            return []
        specs: List[Tuple[str, str, str]] = []
        for field in domain.get('fields') or []:
            prop = field.get('name') or _camel_from_snake(field.get('column') or '')
            col = field.get('column') or _snake(prop)
            jt = _normalize_java_field_type(field.get('java_type') or field.get('javaType') or '', prop, col)
            if prop and col:
                specs.append((prop, col, jt))
        return specs

    if isinstance(source, dict):
        domains = source.get('domains')
        if isinstance(domains, list):
            for domain in domains:
                specs = _from_domain(domain if isinstance(domain, dict) else {})
                if specs:
                    return specs
        for value in source.values():
            specs = _authoritative_analysis_field_specs(value, entity)
            if specs:
                return specs
    elif isinstance(source, list):
        for item in source:
            specs = _authoritative_analysis_field_specs(item, entity)
            if specs:
                return specs
    return []


def _is_css_noise_fragment(text: str) -> bool:
    low = (text or '').lower()
    return any(marker in low for marker in (
        'grid-template', 'minmax(', 'repeat(', 'display:', 'padding:', 'margin:',
        'border:', 'font-', 'color:', 'background:', '.autopj-', '.fc-', '#calendar'
    ))


_JAVA_KEYWORDS = {
    'abstract','assert','boolean','break','byte','case','catch','char','class','const','continue','default','do','double','else','enum','extends','final','finally','float','for','goto','if','implements','import','instanceof','int','interface','long','native','new','package','private','protected','public','return','short','static','strictfp','super','switch','synchronized','this','throw','throws','transient','try','void','volatile','while','true','false','null','record','sealed','permits','var','yield'
}


_DB_RESERVED_KEYWORDS = {
    'mysql': {
        'accessible','add','all','alter','analyze','and','as','asc','before','between','by','case','check','column','constraint','create','database','databases','default','delete','desc','distinct','drop','else','exists','from','group','having','in','index','insert','into','join','key','keys','like','limit','not','null','on','or','order','primary','references','schema','schemas','select','set','table','to','union','unique','update','user','using','values','where','with'
    },
    'postgresql': {
        'all','analyse','analyze','and','any','array','as','asc','asymmetric','authorization','between','binary','both','case','cast','check','collate','column','constraint','create','current_catalog','current_date','current_role','current_time','current_timestamp','current_user','default','deferrable','desc','distinct','do','else','end','except','false','fetch','for','foreign','from','grant','group','having','in','initially','intersect','into','leading','limit','localtime','localtimestamp','not','null','offset','on','only','or','order','placing','primary','references','returning','select','session_user','some','symmetric','table','then','to','trailing','true','union','unique','user','using','variadic','when','where','window','with'
    },
    'oracle': {
        'access','add','all','alter','and','any','as','asc','audit','between','by','char','check','cluster','column','comment','compress','connect','create','current','date','decimal','default','delete','desc','distinct','drop','else','exclusive','exists','file','float','for','from','grant','group','having','identified','immediate','in','increment','index','initial','insert','integer','intersect','into','is','level','like','lock','long','maxextents','minus','mlslabel','mode','modify','noaudit','nocompress','not','nowait','null','number','of','offline','on','online','option','or','order','pctfree','prior','privileges','public','raw','rename','resource','revoke','row','rowid','rownum','rows','select','session','set','share','size','smallint','start','successful','synonym','sysdate','table','then','to','trigger','uid','union','unique','update','user','validate','values','varchar','varchar2','view','whenever','where','with'
    },
}

_COMMON_DANGEROUS_DB_IDENTIFIERS = {
    'schema', 'user', 'order', 'group', 'key', 'desc', 'table', 'column', 'index',
    'select', 'where', 'from', 'to', 'by', 'primary', 'default', 'values', 'comment',
}

_DB_IDENTIFIER_REPLACEMENTS = {
    'table': {
        'schema': 'schema_info',
        'user': 'user_account',
        'order': 'order_info',
        'group': 'group_info',
        'key': 'key_info',
        'desc': 'description_info',
        'table': 'table_info',
        'column': 'column_info',
        'index': 'index_info',
        'select': 'select_info',
        'where': 'where_info',
        'comment': 'comment_info',
    },
    'column': {
        'schema': 'schema_name',
        'user': 'user_id',
        'order': 'sort_order',
        'group': 'group_name',
        'key': 'item_key',
        'desc': 'description',
        'table': 'table_name',
        'column': 'column_name',
        'index': 'index_no',
        'select': 'select_value',
        'where': 'where_value',
        'comment': 'comment_text',
        'default': 'default_value',
        'values': 'value_text',
        'from': 'from_value',
        'to': 'to_value',
        'by': 'by_value',
        'primary': 'primary_value',
    },
}


def _normalize_db_vendor(db_vendor: str | None) -> str:
    token = str(db_vendor or '').strip().lower()
    aliases = {
        'postgres': 'postgresql',
        'postgresql': 'postgresql',
        'postgre': 'postgresql',
        'pg': 'postgresql',
        'oracle': 'oracle',
        'oci': 'oracle',
        'mysql': 'mysql',
        'mariadb': 'mysql',
    }
    return aliases.get(token, '')


def _db_reserved_keywords(db_vendor: str | None = None) -> set[str]:
    vendor = _normalize_db_vendor(db_vendor)
    if vendor and vendor in _DB_RESERVED_KEYWORDS:
        return set(_DB_RESERVED_KEYWORDS[vendor]) | set(_COMMON_DANGEROUS_DB_IDENTIFIERS)
    out: set[str] = set(_COMMON_DANGEROUS_DB_IDENTIFIERS)
    for words in _DB_RESERVED_KEYWORDS.values():
        out.update(words)
    return out


def _is_reserved_db_identifier(token: str, db_vendor: str | None = None) -> bool:
    normalized = _snake(token)
    return bool(normalized) and normalized.lower() in _db_reserved_keywords(db_vendor)


def _sanitize_db_identifier(token: str, kind: str = 'column', db_vendor: str | None = None, used: set[str] | None = None) -> str:
    identifier_kind = 'table' if str(kind or '').strip().lower() == 'table' else 'column'
    reserved = _db_reserved_keywords(db_vendor)
    normalized = _snake(token)
    if not normalized:
        normalized = 'table_info' if identifier_kind == 'table' else 'item_value'
    normalized = re.sub(r'[^A-Za-z0-9_]+', '_', normalized).strip('_').lower()
    if not normalized:
        normalized = 'table_info' if identifier_kind == 'table' else 'item_value'
    if re.match(r'^\d', normalized):
        normalized = ('t_' if identifier_kind == 'table' else 'c_') + normalized
    replacement_map = _DB_IDENTIFIER_REPLACEMENTS.get(identifier_kind, {})
    candidate = replacement_map.get(normalized, normalized)
    candidate = re.sub(r'[^A-Za-z0-9_]+', '_', candidate).strip('_').lower()
    if not candidate:
        candidate = 'table_info' if identifier_kind == 'table' else 'item_value'
    if re.match(r'^\d', candidate):
        candidate = ('t_' if identifier_kind == 'table' else 'c_') + candidate
    suffix = '_info' if identifier_kind == 'table' else '_value'
    while candidate in reserved or candidate in _COMMON_DANGEROUS_DB_IDENTIFIERS:
        if candidate in replacement_map:
            candidate = replacement_map[candidate]
        elif not candidate.endswith(suffix):
            candidate = f'{candidate}{suffix}'
        else:
            candidate = f'{candidate}_1'
    if identifier_kind == 'table':
        candidate = _ensure_tb_table_name(candidate)
    seen = {str(item or '').strip().lower() for item in (used or set()) if str(item or '').strip()}
    base = candidate
    counter = 2
    while candidate.lower() in seen:
        candidate = f'{base}_{counter}'
        counter += 1
    return candidate


def _database_vendor_from_source(source: Any) -> str:
    if isinstance(source, dict):
        for key in ('database_type', 'db_type', 'database_key', 'db_vendor', 'database', 'db'):
            value = source.get(key)
            if isinstance(value, str):
                vendor = _normalize_db_vendor(value)
                if vendor:
                    return vendor
            elif isinstance(value, dict):
                vendor = _database_vendor_from_source(value)
                if vendor:
                    return vendor
        for value in source.values():
            vendor = _database_vendor_from_source(value)
            if vendor:
                return vendor
    elif isinstance(source, list):
        for item in source:
            vendor = _database_vendor_from_source(item)
            if vendor:
                return vendor
    return ''


def _sanitize_java_package_segment(token: str) -> str:
    raw = re.sub(r'[^A-Za-z0-9_]+', '', (token or '').strip())
    if not raw:
        return 'app'
    seg = raw[:1].lower() + raw[1:]
    seg = re.sub(r'^[^A-Za-z_]+', '', seg)
    if not seg:
        return 'app'
    if seg in _JAVA_KEYWORDS:
        return f'{seg}_'
    return seg


def _is_valid_java_identifier(token: str) -> bool:
    raw = (token or '').strip()
    return bool(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', raw)) and raw not in _JAVA_KEYWORDS


_SCHEMA_GENERATION_METADATA_MARKERS = {
    'db', 'database', 'dbname', 'schema', 'schemaname', 'schema_name',
    'table', 'tablename', 'table_name', 'package', 'packagename', 'package_name',
    'frontend', 'frontendtype', 'backend', 'backendtype', 'entity', 'entityname',
    'project', 'projectname', 'path', 'filepath', 'filename', 'resource', 'resources', 'compile', 'compiled', 'build', 'runtime', 'startup', 'endpoint_smoke',
}

_FILE_ARTIFACT_EXTENSIONS = {'sql', 'jsp', 'java', 'xml', 'yml', 'yaml', 'json', 'js', 'ts', 'tsx', 'jsx', 'css', 'html'}


def _is_generation_metadata_identifier(token: str) -> bool:
    raw = re.sub(r'[^A-Za-z0-9_]+', '_', str(token or '').strip()).strip('_').lower()
    return bool(raw) and raw in _SCHEMA_GENERATION_METADATA_MARKERS


def _looks_like_file_artifact_fragment(token: str, tail: str = '') -> bool:
    combined = f"{str(token or '').strip()}{str(tail or '').strip()}".strip().strip("`\"'")
    if not combined:
        return False
    low = combined.lower()
    if re.search(r'\.(?:' + '|'.join(sorted(_FILE_ARTIFACT_EXTENSIONS)) + r')\b', low):
        return True
    if ('/' in low or '\\' in low) and not re.search(r'\s/\s|\s\\\s', low):
        return True
    return False


def _is_disallowed_schema_contract_token(token: str, tail: str = '') -> bool:
    return _is_generation_metadata_identifier(token) or _looks_like_file_artifact_fragment(token, tail)


def _is_valid_column_identifier(token: str) -> bool:
    token = (token or '').strip()
    if not _is_valid_java_identifier(token):
        return False
    low = token.lower()
    if re.fullmatch(r'\d+fr(?:_\d+fr)*', low):
        return False
    if low in {'grid', 'column', 'columns', 'repeat', 'minmax', 'autofit', 'autofill'}:
        return False
    if _is_generation_metadata_identifier(low):
        return False
    return True


def _iter_create_table_blocks(text: str) -> List[Tuple[str, str]]:
    body = text or ""
    out: List[Tuple[str, str]] = []
    start_pat = re.compile(r"create\s+table\s+(?:if\s+not\s+exists\s+)?[`\"]?([A-Za-z_][\w]*)[`\"]?\s*\(", re.IGNORECASE)
    pos = 0
    while True:
        match = start_pat.search(body, pos)
        if not match:
            break
        table = (match.group(1) or "").strip().lower()
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


def _extract_field_specs(text: str) -> List[Tuple[str, str, str]]:
    specs: List[Tuple[str, str, str]] = []

    for _table_name, cols_part in _iter_create_table_blocks(text or ""):
        for raw in re.split(r",\s*(?![^()]*\))", cols_part):
            line = raw.strip()
            if not line:
                continue
            if re.match(r"^(primary|foreign|unique|constraint|key)\b", line, re.IGNORECASE):
                continue
            m = re.match(r'[`"]?([A-Za-z_][\w]*)[`"]?\s+([A-Za-z]+(?:\s*\([^)]*\))?)', line)
            if not m:
                continue
            col = m.group(1)
            sql_type = m.group(2)
            prop = _camel_from_snake(col)
            if not _is_valid_java_identifier(prop) or not _is_valid_column_identifier(col):
                continue
            specs.append((prop, col, _java_type_from_sql_type(sql_type, prop)))

    table_line_pat = re.compile(r"(?:table|테이블)\s*[:：]\s*([A-Za-z_][\w]*)\s*\(([^)]*)\)", re.IGNORECASE)
    for match in table_line_pat.finditer(text or ""):
        if _is_css_noise_fragment(match.group(0)):
            continue
        for token in _split_csv_like(match.group(2)):
            col = _snake(token)
            prop = _camel_from_snake(token)
            if not _is_valid_java_identifier(prop) or not _is_valid_column_identifier(col):
                continue
            specs.append((prop, col, _guess_java_type(prop, col)))

    field_line_pat = re.compile(r"(?:(?<=^)|(?<=\n))\s*(?:fields?|columns?|column\s*definitions?|컬럼정의|필드정의|컬럼|필드|항목)(?:\s*(?:목록|리스트))?\s*[:：]\s*([A-Za-z0-9_,\s|`'\"]+)", re.IGNORECASE)
    for match in field_line_pat.finditer(text or ""):
        if _is_css_noise_fragment(match.group(0)):
            continue
        for token in _split_csv_like(match.group(1)):
            col = _snake(token)
            prop = _camel_from_snake(token)
            if not _is_valid_java_identifier(prop) or not _is_valid_column_identifier(col):
                continue
            specs.append((prop, col, _guess_java_type(prop, col)))

    result_tag_pat = re.compile(r'<(?:id|result)\s+[^>]*property=[\"\']([A-Za-z_][\w]*)[\"\'][^>]*column=[\"\']([A-Za-z_][\w]*)[\"\'][^>]*/?>', re.IGNORECASE)
    for prop, col in result_tag_pat.findall(text or ""):
        if not _is_valid_java_identifier(prop) or not _is_valid_column_identifier(col):
            continue
        specs.append((prop, col, _guess_java_type(prop, col)))

    insert_pat = re.compile(r'insert\s+into\s+[`"]?([A-Za-z_][\w]*)[`"]?\s*\((.*?)\)\s*values\s*\((.*?)\)', re.IGNORECASE | re.DOTALL)
    for m in insert_pat.finditer(text or ""):
        cols = [c.strip(' `"') for c in re.split(r",\s*", m.group(2)) if c.strip()]
        vals = [v.strip() for v in re.split(r",\s*", m.group(3)) if v.strip()]
        for col, val in zip(cols, vals):
            ph = re.search(r"#\{\s*([A-Za-z_][\w]*)\s*\}", val)
            prop = ph.group(1) if ph else _camel_from_snake(col)
            if not _is_valid_java_identifier(prop) or not _is_valid_column_identifier(col):
                continue
            specs.append((prop, col, _guess_java_type(prop, col)))

    update_pat = re.compile(r'update\s+[`"]?([A-Za-z_][\w]*)[`"]?\s+set\s+(.*?)\s+where\s+', re.IGNORECASE | re.DOTALL)
    for m in update_pat.finditer(text or ""):
        set_part = m.group(2)
        for raw in re.split(r",\s*", set_part):
            mm = re.search(r'[`"]?([A-Za-z_][\w]*)[`"]?\s*=\s*#\{\s*([A-Za-z_][\w]*)\s*\}', raw)
            if mm:
                col = mm.group(1)
                prop = mm.group(2)
                if not _is_valid_java_identifier(prop) or not _is_valid_column_identifier(col):
                    continue
                specs.append((prop, col, _guess_java_type(prop, col)))

    select_pat = re.compile(r'select\s+(.*?)\s+from\s+[`"]?([A-Za-z_][\w]*)[`"]?', re.IGNORECASE | re.DOTALL)
    for m in select_pat.finditer(text or ""):
        cols_part = m.group(1)
        if '*' in cols_part:
            continue
        for raw in re.split(r",\s*", cols_part):
            token = raw.strip()
            token = re.sub(r"\s+as\s+[A-Za-z_][\w]*$", "", token, flags=re.IGNORECASE)
            token = token.split('.')[-1].strip(' `"')
            if not re.match(r"^[A-Za-z_][\w]*$", token):
                continue
            prop = _camel_from_snake(token)
            if not _is_valid_java_identifier(prop) or not _is_valid_column_identifier(token):
                continue
            specs.append((prop, token, _guess_java_type(prop, token)))

    return specs


def _table_field_specs_from_text(text: str) -> Dict[str, List[Tuple[str, str, str]]]:
    body = text or ""
    table_specs: Dict[str, List[Tuple[str, str, str]]] = {}
    for table, cols_part in _iter_create_table_blocks(body):
        specs: List[Tuple[str, str, str]] = []
        for raw in re.split(r",\s*(?![^()]*\))", cols_part):
            line = raw.strip()
            if not line:
                continue
            if re.match(r"^(primary|foreign|unique|constraint|key|index)\b", line, re.IGNORECASE):
                continue
            m = re.match(r'[`"]?([A-Za-z_][\w]*)[`"]?\s+([A-Za-z]+(?:\s*\([^)]*\))?)', line)
            if not m:
                continue
            col = m.group(1)
            sql_type = m.group(2)
            prop = _camel_from_snake(col)
            if not _is_valid_java_identifier(prop) or not _is_valid_column_identifier(col):
                continue
            specs.append((prop, col, _java_type_from_sql_type(sql_type, prop)))
        if specs:
            table_specs[table] = _normalize_fields(specs)
    return table_specs


def _authoritative_table_field_specs(sources: Any, table: str, entity: str = '') -> List[Tuple[str, str, str]]:
    desired_names: List[str] = []
    if table:
        desired_names.append((table or '').strip().lower())
    entity_table = _snake(entity) if entity else ''
    if entity_table and entity_table not in desired_names:
        desired_names.append(entity_table)

    prioritized_texts: List[str] = []
    fallback_texts: List[str] = []

    iterable = sources if isinstance(sources, list) else ([sources] if isinstance(sources, dict) else [])
    for item in iterable:
        if not isinstance(item, dict):
            continue
        content = item.get('content') or item.get('sql') or item.get('ddl') or ''
        if not isinstance(content, str) or not content.strip():
            continue
        path = str(item.get('path') or '').replace('\\', '/').lower()
        purpose = str(item.get('purpose') or '').lower()
        if path.endswith('schema.sql') or path.endswith('.sql') or 'create table' in content.lower() or 'schema' in purpose:
            prioritized_texts.append(content)
        else:
            fallback_texts.append(content)

    for text in prioritized_texts + fallback_texts + list(_iter_text_blobs(sources)):
        table_map = _table_field_specs_from_text(text)
        for name in desired_names:
            specs = table_map.get(name)
            if specs:
                return _normalize_fields(specs)
    return []


def _extract_java_vo_field_specs(text: str) -> List[Tuple[str, str, str]]:
    body = text or ""
    if not re.search(r"\bclass\s+[A-Z][A-Za-z0-9_]*VO\b", body):
        return []
    specs: List[Tuple[str, str, str]] = []
    field_pat = re.compile(r"\bprivate\s+([A-Za-z_][\w\.<>]*)\s+([a-zA-Z_][A-Za-z0-9_]*)\s*;")
    for java_type, prop in field_pat.findall(body):
        if prop == "serialVersionUID":
            continue
        col = _snake(prop)
        if not _is_valid_java_identifier(prop) or not _is_valid_column_identifier(col):
            continue
        specs.append((prop, col, _normalize_java_field_type(java_type.strip() or "String", prop, col)))
    return specs


def _authoritative_vo_field_specs(file_ops: List[Dict[str, Any]], entity: str) -> List[Tuple[str, str, str]]:
    entity_name = re.sub(r"[^A-Za-z0-9_]", "", entity or "").strip()
    if not entity_name:
        return []
    preferred_names = {f"{entity_name}VO.java", f"{entity_name.lower()}VO.java"}
    for item in file_ops or []:
        path = (item.get("path") or "").replace("\\", "/")
        name = Path(path).name
        content = item.get("content") or ""
        if name in preferred_names or re.search(rf"\bclass\s+{re.escape(entity_name)}VO\b", content):
            specs = _extract_java_vo_field_specs(content)
            if specs:
                return _normalize_fields(specs)
    return []


def _should_force_crud_from_file_ops(file_ops: List[Dict[str, Any]], entity: str, fields: List[Tuple[str, str, str]]) -> bool:
    entity_low = (entity or "").strip().lower()
    if entity_low in {"login", "auth", "signin", "logout", "session", "account"}:
        return False
    text = "\n".join(_iter_text_blobs(file_ops)).lower()
    has_crud = any(tok in text for tok in (
        "/list.do", "/detail.do", "/form.do", "/save.do", "/delete.do",
        "list.jsp", "detail.jsp", "form.jsp",
        "savemember", "deletemember", "memberlist", "memberdetail", "memberform",
        "insertmember", "updatemember", "deletemember",
    ))
    if not has_crud:
        return False
    field_names = {prop.lower() for prop, _, _ in fields or []}
    has_password = any("password" in name or name in {"pwd", "passwd", "userpw"} for name in field_names)
    has_login = any(name in {"loginid", "userid", "user_id"} for name in field_names)
    return not has_password and not has_login




def _should_force_crud_for_generic_user_entity(source: Any, entity: str, table: str = '') -> bool:
    entity_low = (entity or '').strip().lower()
    table_low = (table or '').strip().lower()
    if any(token in entity_low or token in table_low for token in ('login', 'auth', 'signin', 'sign_in', 'logout', 'session', 'jwt', 'cert', 'integrated', 'sso')):
        return False
    userish = entity_low in {'user', 'member', 'account', 'customer'} or table_low in {'users', 'members', 'accounts', 'customers'}
    if not userish:
        return False
    joined = '\n'.join(_iter_text_blobs(source)).lower()
    explicit_auth_cues = (
        '로그인 기능', '로그인 페이지', '인증 기능', '통합인증', '인증서 로그인', 'jwt 로그인',
        'sign in', 'authentication', 'authenticate(', '/login.do', 'processlogin', 'certlogin', 'jwtlogin', 'sso', 'token login',
    )
    if any(token in joined for token in explicit_auth_cues):
        return False
    crud_cues = (
        'crud', '/list.do', '/detail.do', '/form.do', '/save.do', '/delete.do',
        'list.jsp', 'detail.jsp', 'form.jsp', 'controller.java', 'serviceimpl.java', 'mapper.xml',
        '관리', '목록', '등록', '수정', '삭제', '조회',
    )
    if any(token in joined for token in crud_cues):
        return True
    return True

def _normalize_java_field_type(java_type: str, prop: str = '', col: str = '') -> str:
    raw = (java_type or '').strip()
    if not raw:
        return _guess_java_type(prop, col)
    if _is_temporal_field(prop, col, raw):
        return 'String'
    if _is_id_like(prop, col):
        return 'String'
    lower = raw.lower()
    if any(token in lower for token in ('varchar', 'char', 'text', 'clob', 'bigint', 'smallint', 'tinyint', 'integer', 'decimal', 'numeric', 'datetime', 'timestamp', 'date', 'time', 'bool', 'boolean', 'bit')):
        return _java_type_from_sql_type(raw, col or prop)
    mapping = {
        'string': 'String',
        'java.lang.string': 'String',
        'long': 'Long',
        'java.lang.long': 'Long',
        'integer': 'Integer',
        'int': 'Integer',
        'java.lang.integer': 'Integer',
        'date': 'String',
        'java.util.date': 'String',
        'localdate': 'String',
        'java.time.localdate': 'String',
        'localdatetime': 'String',
        'java.time.localdatetime': 'String',
        'bigdecimal': 'java.math.BigDecimal',
        'java.math.bigdecimal': 'java.math.BigDecimal',
        'boolean': 'Boolean',
        'java.lang.boolean': 'Boolean',
    }
    mapped = mapping.get(lower)
    if mapped:
        return mapped
    if raw[:1].islower():
        return _guess_java_type(prop, col)
    return raw


def _normalize_fields(fields: List[Tuple[str, str, str]], db_vendor: str | None = None) -> List[Tuple[str, str, str]]:
    out: List[Tuple[str, str, str]] = []
    seen_props: set[str] = set()
    used_cols: set[str] = set()
    base_index_by_col: Dict[str, int] = {}

    for prop, col, jt in fields:
        raw_prop = re.sub(r"[^A-Za-z0-9_]", "", prop or "")
        raw_col = re.sub(r"[^A-Za-z0-9_]", "", col or "")

        base_col = _sanitize_db_identifier(raw_col or raw_prop or 'item_value', kind='column', db_vendor=db_vendor)
        if not _is_valid_column_identifier(base_col):
            continue

        prop_candidate = raw_prop
        if not prop_candidate or _snake(prop_candidate) == _snake(raw_col) or _is_reserved_db_identifier(raw_col, db_vendor):
            prop_candidate = _camel_from_snake(base_col)
        prop_candidate = re.sub(r"[^A-Za-z0-9_]", "", prop_candidate or "")
        if not prop_candidate or not _is_valid_java_identifier(prop_candidate):
            prop_candidate = _camel_from_snake(base_col)

        normalized_jt = _normalize_java_field_type(jt, prop_candidate, base_col)
        base_key = base_col.lower()

        if base_key in base_index_by_col:
            idx = base_index_by_col[base_key]
            out[idx] = _prefer_stronger_field_type(out[idx], (prop_candidate, base_col, normalized_jt))
            continue

        final_col = _sanitize_db_identifier(base_col, kind='column', db_vendor=db_vendor, used=used_cols)
        used_cols.add(final_col.lower())

        final_prop = prop_candidate
        if final_prop.lower() in seen_props:
            fallback_prop = _camel_from_snake(final_col)
            if not fallback_prop or not _is_valid_java_identifier(fallback_prop) or fallback_prop.lower() in seen_props:
                continue
            final_prop = fallback_prop

        seen_props.add(final_prop.lower())
        out.append((final_prop, final_col, normalized_jt))
        base_index_by_col[base_key] = len(out) - 1

    return out

def _preferred_id_names_for_table(table: str = '') -> Tuple[List[str], List[str]]:
    table_norm = _snake(table or '')
    table_names: List[str] = []
    if table_norm:
        table_names.append(table_norm)
        if table_norm.endswith('ies'):
            table_names.append(table_norm[:-3] + 'y')
        elif table_norm.endswith('s') and len(table_norm) > 1:
            table_names.append(table_norm[:-1])
    preferred_cols: List[str] = []
    preferred_props: List[str] = []
    for name in table_names:
        candidate_col = f'{name}_id'
        candidate_prop = _camel_from_snake(candidate_col)
        if candidate_col not in preferred_cols:
            preferred_cols.append(candidate_col)
        if candidate_prop.lower() not in [prop.lower() for prop in preferred_props]:
            preferred_props.append(candidate_prop)
    return preferred_props, preferred_cols


def _drop_shadow_generic_id(fields: List[Tuple[str, str, str]], table: str = '') -> List[Tuple[str, str, str]]:
    preferred_props, preferred_cols = _preferred_id_names_for_table(table)
    pref_prop_set = {prop.lower() for prop in preferred_props}
    pref_col_set = {col.lower() for col in preferred_cols}
    has_specific_id = any((prop or '').lower() in pref_prop_set or (col or '').lower() in pref_col_set for prop, col, _ in fields)
    if not has_specific_id:
        return fields
    filtered: List[Tuple[str, str, str]] = []
    for prop, col, jt in fields:
        if (prop or '').lower() == 'id' or (col or '').lower() == 'id':
            continue
        filtered.append((prop, col, jt))
    return filtered or fields


def _pick_id_field(fields: List[Tuple[str, str, str]], table: str = '') -> Tuple[str, str]:
    preferred_props, preferred_cols = _preferred_id_names_for_table(table)
    pref_prop_set = {prop.lower() for prop in preferred_props}
    pref_col_set = {col.lower() for col in preferred_cols}
    for prop, col, _ in fields:
        low_prop = prop.lower()
        low_col = col.lower()
        if low_prop in pref_prop_set or low_col in pref_col_set:
            return prop, col
    for prop, col, _ in fields:
        low_prop = prop.lower()
        low_col = col.lower()
        if low_prop == "id" or low_col == "id":
            return prop, col
    for prop, col, _ in fields:
        if prop.lower().endswith("id") or col.lower().endswith("_id"):
            return prop, col
    return fields[0][0], fields[0][1]


def _type_specificity_rank(java_type: str) -> int:
    jt = (java_type or '').strip()
    if jt in {'Long', 'long', 'Integer', 'int', 'java.math.BigDecimal', 'Boolean', 'boolean'}:
        return 3
    if jt in {'java.util.Date', 'Date', 'java.time.LocalDate', 'LocalDate', 'java.time.LocalDateTime', 'LocalDateTime'}:
        return 3
    if jt == 'String':
        return 1
    return 2


def _prefer_stronger_field_type(existing: Tuple[str, str, str], default: Tuple[str, str, str]) -> Tuple[str, str, str]:
    e_prop, e_col, e_jt = existing
    d_prop, d_col, d_jt = default
    if _type_specificity_rank(d_jt) > _type_specificity_rank(e_jt):
        return (e_prop or d_prop, e_col or d_col, d_jt)
    return existing


def _schedule_schema_defaults(entity_name: str, table_name: str, fields: List[Tuple[str, str, str]]) -> List[Tuple[str, str, str]]:
    normalized = _normalize_fields(list(fields or []))
    existing_cols = {col.lower() for _, col, _ in normalized}
    existing_props = {prop.lower() for prop, _, _ in normalized}
    name_low = (entity_name or table_name or '').lower()
    is_schedule_table = 'schedule' in name_low or (table_name or '').strip().lower() == 'schedule'
    has_temporal = any(
        col.lower() in {"start_datetime", "end_datetime", "start_date", "end_date", "reservation_date"}
        or prop.lower() in {"startdatetime", "enddatetime", "startdate", "enddate", "reservationdate"}
        for prop, col, _ in normalized
    )
    # Respect richer authoritative schemas only when they already satisfy the schedule minimum contract.
    if 'reservation' in name_low:
        required_cols = {'reservation_id', 'room_id', 'start_datetime', 'end_datetime', 'status_cd', 'reg_dt', 'upd_dt'}
    elif is_schedule_table:
        required_cols = {
            'schedule_id', 'title', 'content', 'start_datetime', 'end_datetime', 'all_day_yn',
            'status_cd', 'priority_cd', 'location', 'writer_id', 'use_yn', 'reg_dt', 'upd_dt'
        }
    else:
        required_cols = set()
    if has_temporal and required_cols and required_cols.issubset(existing_cols):
        return normalized
    defaults: List[Tuple[str, str, str]]
    if 'reservation' in name_low:
        defaults = [
            ("reservationId", "reservation_id", "String"),
            ("roomId", "room_id", "String"),
            ("reserverName", "reserver_name", "String"),
            ("purpose", "purpose", "String"),
            ("startDatetime", "start_datetime", "String"),
            ("endDatetime", "end_datetime", "String"),
            ("statusCd", "status_cd", "String"),
            ("remark", "remark", "String"),
            ("regDt", "reg_dt", "String"),
            ("updDt", "upd_dt", "String"),
        ]
    elif is_schedule_table:
        defaults = [
            ("scheduleId", "schedule_id", "String"),
            ("title", "title", "String"),
            ("content", "content", "String"),
            ("startDatetime", "start_datetime", "String"),
            ("endDatetime", "end_datetime", "String"),
            ("allDayYn", "all_day_yn", "String"),
            ("statusCd", "status_cd", "String"),
            ("priorityCd", "priority_cd", "String"),
            ("location", "location", "String"),
            ("writerId", "writer_id", "String"),
            ("useYn", "use_yn", "String"),
            ("regDt", "reg_dt", "String"),
            ("updDt", "upd_dt", "String"),
        ]
    else:
        defaults = [
            ("id", "id", "String"),
            ("title", "title", "String"),
            ("startDatetime", "start_datetime", "String"),
            ("endDatetime", "end_datetime", "String"),
            ("statusCd", "status_cd", "String"),
            ("remark", "remark", "String"),
            ("regDt", "reg_dt", "String"),
            ("updDt", "upd_dt", "String"),
        ]
    merged: List[Tuple[str, str, str]] = []
    seen_cols: set[str] = set()
    seen_props: set[str] = set()
    for prop, col, jt in defaults:
        prop_low = prop.lower()
        col_low = col.lower()
        default_item = (prop, col, jt)
        if prop_low in existing_props or col_low in existing_cols:
            match = next((item for item in normalized if item[0].lower() == prop_low or item[1].lower() == col_low), None)
            if match and match[0].lower() not in seen_props and match[1].lower() not in seen_cols:
                merged_item = _prefer_stronger_field_type(match, default_item)
                merged.append(merged_item)
                seen_props.add(merged_item[0].lower())
                seen_cols.add(merged_item[1].lower())
            continue
        if col_low not in seen_cols and prop_low not in seen_props:
            merged.append(default_item)
            seen_props.add(prop_low)
            seen_cols.add(col_low)
    for item in normalized:
        prop_low = item[0].lower()
        col_low = item[1].lower()
        if prop_low in seen_props or col_low in seen_cols:
            continue
        merged.append(item)
        seen_props.add(prop_low)
        seen_cols.add(col_low)
    return _normalize_fields(merged)

def _auth_schema_defaults(fields: List[Tuple[str, str, str]], id_prop: str, id_col: str) -> Tuple[List[Tuple[str, str, str]], Tuple[str, str, str], Tuple[str, str, str]]:
    auth_id, auth_pw, normalized = choose_auth_fields(fields, id_prop, id_col)
    return _normalize_fields(normalized), auth_id, auth_pw

def _routes_and_views(entity_var: str, feature_kind: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    route_base = f"/{entity_var}"
    if is_auth_kind(feature_kind):
        route_base = "/login"
        return (
            {
                "login": f"{route_base}/login.do",
                "process": f"{route_base}/actionLogin.do",
                "logout": f"{route_base}/actionLogout.do",
                "main": f"{route_base}/actionMain.do",
                "integrationGuide": f"{route_base}/integrationGuide.do",
                "integratedLogin": f"{route_base}/integratedLogin.do",
                "integrationCallback": f"{route_base}/integratedCallback.do",
                "certLogin": f"{route_base}/certLogin.do",
                "certProcess": f"{route_base}/actionCertLogin.do",
                "jwtLogin": f"{route_base}/jwtLogin.do",
                "jwtProcess": f"{route_base}/actionJwtLogin.do",
            },
            {
                "login": "login/login",
                "main": "login/main",
            },
        )
    if is_schedule_kind(feature_kind):
        return (
            {
                "calendar": f"{route_base}/calendar.do",
                "detail": f"{route_base}/view.do",
                "form": f"{route_base}/edit.do",
                "save": f"{route_base}/save.do",
                "delete": f"{route_base}/remove.do",
            },
            {
                "calendar": f"{entity_var}/{entity_var}Calendar",
                "detail": f"{entity_var}/{entity_var}Detail",
                "form": f"{entity_var}/{entity_var}Form",
            },
        )
    if is_read_only_kind(feature_kind):
        return (
            {
                "list": f"{route_base}/list.do",
                "detail": f"{route_base}/detail.do",
            },
            {
                "list": f"{entity_var}/{entity_var}List",
                "detail": f"{entity_var}/{entity_var}Detail",
            },
        )
    return (
        {
            "list": f"{route_base}/list.do",
            "detail": f"{route_base}/detail.do",
            "form": f"{route_base}/form.do",
            "save": f"{route_base}/save.do",
            "delete": f"{route_base}/delete.do",
        },
        {
            "list": f"{entity_var}/{entity_var}List",
            "detail": f"{entity_var}/{entity_var}Detail",
            "form": f"{entity_var}/{entity_var}Form",
        },
    )

def _is_generic_entity_name(name: str) -> bool:
    return (name or '').strip().lower() in {'', 'item', 'entity', 'domain', 'record', 'data'}

def _feature_kind_hint_from_entity_or_table(entity: str = '', table: str = '', current: str = FEATURE_KIND_CRUD) -> str:
    joined = f"{entity or ''} {table or ''}".lower()
    if re.search(r'\b(login|auth|signin|session|account|user_auth|login_user)\b', joined):
        return FEATURE_KIND_AUTH
    if re.search(r'\b(schedule|calendar|reservation|booking)\b', joined):
        return FEATURE_KIND_SCHEDULE
    return current


def _has_explicit_auth_creation_request(source: Any) -> bool:
    joined = '\\n'.join(_iter_text_blobs(source)).lower()
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
        'authenticate(', '통합인증', '인증서 로그인', 'jwt 로그인', 'certlogin', 'jwtlogin', 'sso',
    )
    if any(token in joined for token in preserve_tokens):
        filtered = joined
        for token in preserve_tokens:
            filtered = filtered.replace(token, ' ')
        joined = filtered
    return any(token in joined for token in creation_tokens)


def _is_signup_management_request(source: Any, entity: str = '', table: str = '') -> bool:
    joined = '\\n'.join(_iter_text_blobs(source)).lower()
    entity_low = (entity or '').strip().lower()
    table_low = (table or '').strip().lower()
    signupish = any(token in joined for token in (
        'signup', 'sign up', 'register', 'registration', 'join member', '회원가입', '가입화면', '가입 화면',
    )) or entity_low in {'signup', 'register', 'registration', 'join'}
    if not signupish:
        return False
    userish = any(token in joined for token in (
        'member management', 'user management', '회원관리', '사용자관리', '중복 로그인 id', '중복 login id',
        'duplicate login id', 'email validation', 'phone validation', '이메일 validation', '전화번호 validation',
    )) or table_low in {'users', 'members'}
    if not userish:
        return False
    explicit_login = _has_explicit_auth_creation_request(source)
    return _has_shared_auth_table_request(source) or not explicit_login


def _canonical_userish_entity(entity: str = '', table: str = '', source: Any = None) -> str:
    entity_low = (entity or '').strip().lower()
    table_low = (table or '').strip().lower()
    joined = '\n'.join(_iter_text_blobs(source)).lower() if source is not None else ''
    normalized_table = table_low[3:] if table_low.startswith('tb_') else table_low
    auth_like = ((('login_id' in joined and 'password' in joined) or ('로그인 id' in joined and '비밀번호' in joined))
        and entity_low not in {'signup', 'register', 'registration', 'join'}
        and not _has_shared_auth_table_request(source)
        and not any(token in joined for token in ('기존 로그인 기능은 그대로 유지', '로그인 기능은 새로 만들지 말고', '회원가입/회원관리만 추가')))
    if auth_like and normalized_table in {'users', 'user', 'members', 'member'}:
        return 'Login'
    if _has_shared_auth_table_request(source) and normalized_table in {'users', 'user'}:
        return 'User'
    if _has_shared_auth_table_request(source) and normalized_table in {'members', 'member'}:
        return 'Member'
    if normalized_table == 'users' or entity_low in {'user', 'users'}:
        return 'User'
    if normalized_table == 'members' or entity_low in {'member', 'members'}:
        return 'Member'
    if entity_low in {'signup', 'register', 'registration', 'join'} and (normalized_table in {'users', 'members'} or any(token in joined for token in ('회원관리', 'user management', 'member management', '중복 로그인 id', 'duplicate login id'))):
        return 'User' if normalized_table != 'members' else 'Member'
    return entity or 'Item'


def _entity_name_from_sources(entity: str, sources: Any) -> str:
    if not _is_generic_entity_name(entity):
        return entity
    for text_blob in _iter_text_blobs(sources):
        explicit_table = _extract_explicit_table_name(text_blob)
        if explicit_table:
            token = _table_identifier_to_entity_token(explicit_table)
            if token:
                return token[:1].upper() + token[1:]
    mapper_table, _mapper_specs = _authoritative_mapper_contract(sources, entity=entity)
    if mapper_table:
        token = _table_identifier_to_entity_token(mapper_table)
        if token:
            return token[:1].upper() + token[1:]
    if isinstance(sources, dict):
        domains = sources.get('domains')
        if isinstance(domains, list):
            for domain in domains:
                if isinstance(domain, dict):
                    name = (domain.get('name') or domain.get('entity_name') or domain.get('source_table') or '').strip()
                    token = _strip_logical_tb_prefix(name) or re.sub(r"[^A-Za-z0-9_]", "", name)
                    if token:
                        return token[:1].upper() + token[1:]
    return entity or 'Item'

def _table_from_sources(entity: str, sources: Any) -> str:
    entity_table = _snake(entity)
    create_table_names: List[str] = []
    labeled_names: List[str] = []
    mapper_names: List[str] = []
    for text in _iter_text_blobs(sources):
        create_table_names.extend(
            m.group(1).lower()
            for m in re.finditer(r'create\s+table\s+(?:if\s+not\s+exists\s+)?[`"]?([A-Za-z_][\w]*)[`"]?', text, re.IGNORECASE)
        )
        labeled_names.extend(
            m.group(1).lower()
            for m in re.finditer(r"(?:table\s*name|table|테이블명|테이블)\s*(?:은|는|:|=)?\s*([A-Za-z_][\w]*)", text, re.IGNORECASE)
        )
        mapper_names.extend(_mapper_table_names_from_text(text))

    for name in labeled_names + mapper_names + create_table_names:
        if name == entity_table:
            return name

    unique_mapper_names = [name for name in dict.fromkeys(mapper_names) if name]
    if len(set(unique_mapper_names)) == 1:
        return unique_mapper_names[0]

    # Guard against cross-entity leakage. When multiple CREATE TABLE blocks exist but none
    # explicitly match the current entity, keep the default entity-derived table name instead
    # of blindly reusing the first table name from another entity.
    if len(set(create_table_names)) > 1:
        return entity_table
    if len(set(labeled_names)) > 1:
        return entity_table

    if labeled_names and labeled_names[0] == entity_table:
        return labeled_names[0]
    if create_table_names and create_table_names[0] == entity_table:
        return create_table_names[0]
    if labeled_names:
        return labeled_names[0]
    if unique_mapper_names:
        return unique_mapper_names[0]
    return entity_table
def schema_for(entity: str, inferred_fields: Optional[List[Tuple[str, str, str]]] = None, table: Optional[str] = None, feature_kind: str = FEATURE_KIND_CRUD, strict_fields: bool = False, unified_auth: Optional[bool] = None, cert_login: bool = False, jwt_login: bool = False, field_comments: Optional[Dict[str, str]] = None, field_db_types: Optional[Dict[str, str]] = None, field_nullable: Optional[Dict[str, bool]] = None, field_unique: Optional[Dict[str, bool]] = None, field_auto_increment: Optional[Dict[str, bool]] = None, field_defaults: Optional[Dict[str, str]] = None, field_references: Optional[Dict[str, Any]] = None, table_comment: str = '', db_vendor: Optional[str] = None) -> Schema:
    entity_name = _pascal_entity_name(entity or "Item")
    ev = _entity_var(entity_name)
    resolved_table = _sanitize_db_identifier(table or _snake(entity_name), kind='table', db_vendor=db_vendor)
    fields = _normalize_fields(list(inferred_fields or []), db_vendor=db_vendor)
    if not fields:
        if is_auth_kind(feature_kind):
            fields = [
                ("loginId", "login_id", "String"),
                ("password", "password", "String"),
            ]
        elif is_schedule_kind(feature_kind):
            fields = _schedule_schema_defaults(entity_name, resolved_table, [])
        else:
            fields = [
                ("id", "id", "String"),
                ("name", "name", "String"),
                ("description", "description", "String"),
                ("createdAt", "created_at", "String"),
            ]
    elif is_schedule_kind(feature_kind) and not strict_fields:
        fields = _schedule_schema_defaults(entity_name, resolved_table, fields)
    fields = _normalize_fields(fields, db_vendor=db_vendor)
    fields = [item for item in fields if item and len(item) >= 2 and not _is_disallowed_schema_contract_token(str(item[1] or ''))]
    fields = _drop_shadow_generic_id(fields, resolved_table)
    id_prop, id_column = _pick_id_field(fields, resolved_table)
    if is_auth_kind(feature_kind):
        fields, auth_id, _auth_pw = _auth_schema_defaults(fields, id_prop, id_column)
        if not strict_fields:
            id_prop, id_column = auth_id[0], auth_id[1]
    routes, views = _routes_and_views(ev, feature_kind)
    resolved_unified_auth = is_auth_kind(feature_kind) if unified_auth is None else bool(unified_auth)
    resolved_cert_login = bool(cert_login) if is_auth_kind(feature_kind) else False
    resolved_jwt_login = bool(jwt_login) if is_auth_kind(feature_kind) else False
    field_columns = [str(col or '').strip().lower() for _prop, col, _jt in fields if str(col or '').strip()]

    def _normalize_field_map(source: Optional[Dict[str, Any]], *, bool_mode: bool = False) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for key, value in (source or {}).items():
            col = _sanitize_db_identifier(_snake(key), kind='column', db_vendor=db_vendor)
            if not col:
                continue
            if bool_mode:
                if value is None:
                    continue
                normalized[col.lower()] = bool(value)
            else:
                if value is None or not str(value).strip():
                    continue
                normalized[col.lower()] = str(value).strip()
        return {col: normalized[col] for col in field_columns if col in normalized}

    normalized_comments = _normalize_field_map(field_comments)
    if is_auth_kind(feature_kind):
        auth_comment_defaults = {
            'login_id': '로그인ID',
            'password': '비밀번호',
            'user_name': '사용자명',
            'use_yn': '사용여부',
            'status_cd': '상태코드',
            'reg_dt': '등록일시',
            'upd_dt': '수정일시',
            'created_at': '생성일시',
            'updated_at': '수정일시',
        }
        for col in field_columns:
            if col not in normalized_comments and auth_comment_defaults.get(col):
                normalized_comments[col] = auth_comment_defaults[col]
    normalized_db_types = _normalize_field_map(field_db_types)
    normalized_nullable = _normalize_field_map(field_nullable, bool_mode=True)
    normalized_unique = _normalize_field_map(field_unique, bool_mode=True)
    normalized_auto_increment = _normalize_field_map(field_auto_increment, bool_mode=True)
    normalized_defaults: Dict[str, str] = {}
    for col, value in _normalize_field_map(field_defaults).items():
        normalized_default = _normalize_sql_default(value)
        if normalized_default:
            normalized_defaults[col] = normalized_default

    normalized_references: Dict[str, Tuple[str, str]] = {}
    for key, value in (field_references or {}).items():
        col = _sanitize_db_identifier(_snake(key), kind='column', db_vendor=db_vendor)
        if not col or col.lower() not in field_columns or not value:
            continue
        ref_table = ''
        ref_col = ''
        if isinstance(value, dict):
            ref_table = str(value.get('table') or value.get('ref_table') or '').strip()
            ref_col = str(value.get('column') or value.get('ref_column') or '').strip()
        elif isinstance(value, (tuple, list)) and len(value) >= 2:
            ref_table = str(value[0] or '').strip()
            ref_col = str(value[1] or '').strip()
        if not ref_table or not ref_col:
            continue
        ref_table = _sanitize_db_identifier(ref_table, kind='table', db_vendor=db_vendor)
        ref_col = _sanitize_db_identifier(ref_col, kind='column', db_vendor=db_vendor)
        if ref_table and ref_col:
            normalized_references[col.lower()] = (ref_table, ref_col)

    return Schema(
        entity=entity_name,
        entity_var=ev,
        table=resolved_table,
        id_prop=id_prop,
        id_column=id_column,
        fields=fields,
        routes=routes,
        views=views,
        feature_kind=feature_kind,
        unified_auth=resolved_unified_auth,
        cert_login=resolved_cert_login,
        jwt_login=resolved_jwt_login,
        table_comment=str(table_comment or '').strip(),
        db_vendor=str(db_vendor or '').strip().lower(),
        field_comments=normalized_comments,
        field_db_types=normalized_db_types,
        field_nullable=normalized_nullable,
        field_unique=normalized_unique,
        field_auto_increment=normalized_auto_increment,
        field_defaults=normalized_defaults,
        field_references=normalized_references,
    )

def infer_schema_from_plan(plan: Dict) -> Schema:
    entity = _entity_name_from_sources(infer_entity_from_plan(plan) or "Item", plan)
    explicit_contract = False
    authority = 'heuristic'
    explicit_table_name = ''
    table_name = _table_from_sources(entity, plan)
    field_specs: List[Tuple[str, str, str]] = []
    explicit_entries: List[Dict[str, Any]] = []
    mapper_table_name, mapper_specs = _authoritative_mapper_contract(plan.get('tasks') or plan, table_name, entity)
    if mapper_table_name and (_is_generic_entity_name(entity) or table_name in {'', 'item', 'id'}):
        entity = mapper_table_name[:1].upper() + mapper_table_name[1:]
        table_name = mapper_table_name

    feature_kind = classify_feature_kind(plan)
    db_vendor = _database_vendor_from_source(plan)
    unified_auth, cert_login, jwt_login = _auth_options_from_sources(plan, feature_kind)

    for text in _iter_text_blobs(plan):
        targeted_table_name, extracted, extracted_entries = _extract_explicit_contract_for_target(text, entity=entity, table=table_name)
        if extracted:
            explicit_table_name = explicit_table_name or targeted_table_name
            field_specs = extracted
            explicit_entries = extracted_entries
            explicit_contract = True
            authority = 'explicit'
            break

    if not field_specs and mapper_specs:
        field_specs = mapper_specs
        explicit_contract = True
        authority = 'mapper'
    if not field_specs:
        field_specs = _authoritative_table_field_specs(plan.get('tasks') or plan, table_name, entity)
        explicit_contract = bool(field_specs)
        if field_specs:
            authority = 'ddl'
    if not field_specs:
        field_specs = _authoritative_analysis_field_specs(plan, entity)
        explicit_contract = bool(field_specs)
        if field_specs:
            authority = 'analysis'
    if not field_specs:
        for text in _iter_text_blobs(plan):
            field_specs.extend(_extract_field_specs(text))
        if field_specs:
            authority = 'heuristic'
    feature_kind = classify_feature_kind(plan, entity=entity)
    if explicit_table_name:
        table_name = explicit_table_name
    elif mapper_table_name:
        table_name = mapper_table_name
    entity = _canonical_userish_entity(entity, table_name, plan)
    feature_kind = _feature_kind_hint_from_entity_or_table(entity, table_name, feature_kind)
    if is_auth_kind(feature_kind) and (((entity or '').strip().lower() in {'signup', 'register', 'registration', 'join'}) or _should_force_crud_for_generic_user_entity(plan, entity, table_name) or _is_signup_management_request(plan, entity, table_name)):
        feature_kind = FEATURE_KIND_CRUD
    explicit_meta = {str(entry.get('col') or '').strip().lower(): entry for entry in (explicit_entries or []) if str(entry.get('col') or '').strip()}
    schema = schema_for(entity, field_specs, table_name, feature_kind=feature_kind, strict_fields=explicit_contract, unified_auth=unified_auth, cert_login=cert_login, jwt_login=jwt_login, field_comments={**_collect_requirement_field_comments(plan), **{col: str(meta.get('comment') or '').strip() for col, meta in explicit_meta.items() if str(meta.get('comment') or '').strip()}}, field_db_types={col: str(meta.get('db_type') or '').strip() for col, meta in explicit_meta.items() if str(meta.get('db_type') or '').strip()}, field_nullable={col: meta.get('nullable') for col, meta in explicit_meta.items() if meta.get('nullable') is not None}, field_unique={col: bool(meta.get('unique')) for col, meta in explicit_meta.items() if meta.get('unique')}, field_auto_increment={col: bool(meta.get('auto_increment')) for col, meta in explicit_meta.items() if meta.get('auto_increment')}, field_defaults={col: str(meta.get('default') or '').strip() for col, meta in explicit_meta.items() if str(meta.get('default') or '').strip()}, field_references={col: meta.get('references') for col, meta in explicit_meta.items() if meta.get('references')}, table_comment=_collect_requirement_table_comment(plan), db_vendor=db_vendor)
    schema.authority = authority
    return schema

def infer_schema_from_file_ops(file_ops: List[Dict[str, Any]], entity: Optional[str] = None) -> Schema:
    plan = {"tasks": file_ops or []}
    inferred_entity = _entity_name_from_sources(entity or infer_entity_from_plan(plan) or "Item", file_ops)
    table_name = _table_from_sources(inferred_entity, file_ops)
    explicit_contract = False
    authority = 'heuristic'
    explicit_table_name = ''
    field_specs: List[Tuple[str, str, str]] = []
    explicit_entries: List[Dict[str, Any]] = []
    mapper_table_name, mapper_specs = _authoritative_mapper_contract(file_ops, table_name, inferred_entity)
    feature_kind = classify_feature_kind(file_ops, entity=inferred_entity)
    db_vendor = _database_vendor_from_source(file_ops)
    feature_kind = _feature_kind_hint_from_entity_or_table(inferred_entity, table_name, feature_kind)
    if is_auth_kind(feature_kind) and _should_force_crud_for_generic_user_entity(file_ops, inferred_entity, table_name):
        feature_kind = FEATURE_KIND_CRUD
    unified_auth, cert_login, jwt_login = _auth_options_from_sources(file_ops, feature_kind)
    if mapper_table_name and (_is_generic_entity_name(inferred_entity) or table_name in {'id', 'item', ''}):
        inferred_entity = mapper_table_name[:1].upper() + mapper_table_name[1:]
        table_name = mapper_table_name

    for text in _iter_text_blobs(file_ops):
        targeted_table_name, extracted, extracted_entries = _extract_explicit_contract_for_target(text, entity=inferred_entity, table=table_name)
        if extracted:
            explicit_table_name = explicit_table_name or targeted_table_name
            field_specs = extracted
            explicit_entries = extracted_entries
            explicit_contract = True
            authority = 'explicit'
            break

    if not field_specs and mapper_specs:
        field_specs = mapper_specs
        explicit_contract = True
        authority = 'mapper'
    if not field_specs:
        field_specs = _authoritative_table_field_specs(file_ops, table_name, inferred_entity)
        explicit_contract = bool(field_specs)
        if field_specs:
            authority = 'ddl'
    if not field_specs:
        field_specs = _authoritative_analysis_field_specs(file_ops, inferred_entity)
        explicit_contract = bool(field_specs)
        if field_specs:
            authority = 'analysis'
    if not field_specs:
        for text in _iter_text_blobs(file_ops):
            field_specs.extend(_extract_field_specs(text))
        if field_specs:
            authority = 'heuristic'
    authoritative_vo = _authoritative_vo_field_specs(file_ops, inferred_entity)
    if authoritative_vo and not field_specs:
        field_specs = authoritative_vo
        authority = 'vo'
    if authoritative_vo and _should_force_crud_from_file_ops(file_ops, inferred_entity, authoritative_vo):
        feature_kind = FEATURE_KIND_CRUD
    if explicit_table_name:
        table_name = explicit_table_name
    elif mapper_table_name:
        table_name = mapper_table_name
    inferred_entity = _canonical_userish_entity(inferred_entity, table_name, file_ops)
    feature_kind = _feature_kind_hint_from_entity_or_table(inferred_entity, table_name, feature_kind)
    if is_auth_kind(feature_kind) and (((inferred_entity or '').strip().lower() in {'signup', 'register', 'registration', 'join'}) or _should_force_crud_for_generic_user_entity(file_ops, inferred_entity, table_name) or _is_signup_management_request(file_ops, inferred_entity, table_name)):
        feature_kind = FEATURE_KIND_CRUD
    unified_auth, cert_login, jwt_login = _auth_options_from_sources(file_ops, feature_kind)
    explicit_meta = {str(entry.get('col') or '').strip().lower(): entry for entry in (explicit_entries or []) if str(entry.get('col') or '').strip()}
    schema = schema_for(inferred_entity, field_specs, table_name, feature_kind=feature_kind, strict_fields=explicit_contract, unified_auth=unified_auth, cert_login=cert_login, jwt_login=jwt_login, field_comments={**_collect_requirement_field_comments(file_ops), **{col: str(meta.get('comment') or '').strip() for col, meta in explicit_meta.items() if str(meta.get('comment') or '').strip()}}, field_db_types={col: str(meta.get('db_type') or '').strip() for col, meta in explicit_meta.items() if str(meta.get('db_type') or '').strip()}, field_nullable={col: meta.get('nullable') for col, meta in explicit_meta.items() if meta.get('nullable') is not None}, field_unique={col: bool(meta.get('unique')) for col, meta in explicit_meta.items() if meta.get('unique')}, field_auto_increment={col: bool(meta.get('auto_increment')) for col, meta in explicit_meta.items() if meta.get('auto_increment')}, field_defaults={col: str(meta.get('default') or '').strip() for col, meta in explicit_meta.items() if str(meta.get('default') or '').strip()}, field_references={col: meta.get('references') for col, meta in explicit_meta.items() if meta.get('references')}, table_comment=_collect_requirement_table_comment(file_ops), db_vendor=db_vendor)
    schema.authority = authority
    return schema

def _java_imports(schema: Schema) -> List[str]:
    imports: List[str] = []
    java_types = {jt for _, _, jt in schema.fields}
    if any(jt in {"java.util.Date", "Date", "java.time.LocalDateTime", "LocalDateTime", "java.time.LocalDate", "LocalDate"} for jt in java_types):
        imports.append("import java.util.Date;")
    if "java.math.BigDecimal" in java_types:
        imports.append("import java.math.BigDecimal;")
    return imports

def _java_default_literal(java_type: str) -> str:
    if java_type in ("Long", "long", "Integer", "int"):
        return "0"
    return "null"

def _java_param_type(java_type: str) -> str:
    return java_type if java_type else "String"

def _mybatis_param_type(java_type: str) -> str:
    mapping = {
        "String": "string",
        "Long": "long",
        "long": "long",
        "Integer": "int",
        "int": "int",
        "Boolean": "boolean",
        "boolean": "boolean",
    }
    return mapping.get(java_type, java_type)


def _optional_param_has_value_expr(var_name: str, java_type: str) -> str:
    jt = (java_type or "String").strip()
    simple = jt.split('.')[-1]
    if simple == "String":
        return f"{var_name} != null && !{var_name}.isBlank()"
    if simple == "Long":
        return f"{var_name} != null && {var_name}.longValue() != 0L"
    if simple == "Integer":
        return f"{var_name} != null && {var_name}.intValue() != 0"
    if simple == "long":
        return f"{var_name} != 0L"
    if simple == "int":
        return f"{var_name} != 0"
    return f"{var_name} != null"


def _optional_param_missing_expr(var_name: str, java_type: str) -> str:
    jt = (java_type or "String").strip()
    simple = jt.split('.')[-1]
    if simple == "String":
        return f"{var_name} == null || {var_name}.isBlank()"
    if simple == "Long":
        return f"{var_name} == null || {var_name}.longValue() == 0L"
    if simple == "Integer":
        return f"{var_name} == null || {var_name}.intValue() == 0"
    if simple == "long":
        return f"{var_name} == 0L"
    if simple == "int":
        return f"{var_name} == 0"
    return f"{var_name} == null"

def _find_field_type(schema: Schema, prop: str) -> str:
    for p, _, jt in schema.fields:
        if p == prop:
            return jt
    return "String"

def _ddl_default_sql_type(prop: str, col: str, jt: str, schema: Schema) -> str:
    if col == schema.id_column:
        return 'VARCHAR(64)'
    if _is_temporal_field(prop, col, jt):
        return 'DATE' if _is_date_only_name(prop, col) else 'DATETIME'
    if jt in ("Long", "Integer", "int", "long"):
        return 'BIGINT'
    if jt == "java.math.BigDecimal":
        return 'DECIMAL(18,2)'
    if jt in ("Boolean", "boolean"):
        return 'BOOLEAN'
    if _is_yn_field(prop, col):
        return 'VARCHAR(1)'
    if col.lower() in {'content', 'remark', 'description', 'memo'}:
        return 'TEXT'
    return 'VARCHAR(255)'


def _strip_default_prefix(value: str) -> str:
    raw = str(value or '').strip()
    if not raw:
        return ''
    while True:
        match = re.match(r'^DEFAULT\s+(.*)$', raw, re.IGNORECASE)
        if not match:
            break
        next_raw = str(match.group(1) or '').strip()
        if not next_raw or next_raw == raw:
            break
        raw = next_raw
    return raw



def _normalize_sql_default(value: str) -> str:
    raw = _strip_default_prefix(value)
    if not raw:
        return ''
    upper_raw = raw.upper()
    if upper_raw in {'CURRENT_TIMESTAMP', 'CURRENT_DATE', 'CURRENT_TIME', 'NULL'}:
        return upper_raw
    if re.fullmatch(r'CURRENT_TIMESTAMP\s*\(\s*\)', raw, re.IGNORECASE):
        return 'CURRENT_TIMESTAMP'
    if re.fullmatch(r'-?\d+(?:\.\d+)?', raw):
        return raw
    if (raw.startswith("'") and raw.endswith("'")) or (raw.startswith('"') and raw.endswith('"')):
        return raw.replace('"', "'")
    return "'" + raw.replace("'", "''") + "'"


def ddl(schema: Schema) -> str:
    cols = []
    comments = getattr(schema, 'field_comments', {}) or {}
    explicit_db_types = getattr(schema, 'field_db_types', {}) or {}
    explicit_nullable = getattr(schema, 'field_nullable', {}) or {}
    explicit_unique = getattr(schema, 'field_unique', {}) or {}
    explicit_auto_increment = getattr(schema, 'field_auto_increment', {}) or {}
    explicit_defaults = getattr(schema, 'field_defaults', {}) or {}
    vendor = str(getattr(schema, 'db_vendor', '') or '').lower()
    table_comment = str(getattr(schema, 'table_comment', '') or '').strip()
    post_statements: List[str] = []
    fk_clauses: List[str] = []
    explicit_references = getattr(schema, 'field_references', {}) or {}
    mysql_like = vendor in {'', 'mysql', 'mariadb'}
    postgres_like = vendor in {'postgres', 'postgresql'}
    oracle_like = vendor == 'oracle'
    for prop, col, jt in schema.fields:
        col_key = str(col or '').lower()
        comment = str(comments.get(col_key, '') or '').strip() or str(col or '').strip()
        sql_type = str(explicit_db_types.get(col_key) or '').strip() or _ddl_default_sql_type(prop, col, jt, schema)
        nullable = explicit_nullable.get(col_key, None)
        unique = bool(explicit_unique.get(col_key, False))
        auto_increment = bool(explicit_auto_increment.get(col_key, False))
        default_expr = _normalize_sql_default(explicit_defaults.get(col_key, ''))
        tokens = [f"{col} {sql_type}"]
        if auto_increment and 'AUTO_INCREMENT' not in sql_type.upper() and mysql_like:
            tokens.append('AUTO_INCREMENT')
        is_primary = (col == schema.id_column)
        if not is_primary and unique:
            tokens.append('UNIQUE')
        if is_primary:
            if nullable is not True and 'NOT NULL' not in sql_type.upper():
                tokens.append('NOT NULL')
            if 'PRIMARY KEY' not in sql_type.upper():
                tokens.append('PRIMARY KEY')
        elif nullable is False and 'NOT NULL' not in sql_type.upper():
            tokens.append('NOT NULL')
        elif auto_increment and 'NOT NULL' not in sql_type.upper():
            tokens.append('NOT NULL')
        if default_expr and 'DEFAULT ' not in sql_type.upper():
            tokens.append(f'DEFAULT {default_expr}')
        if mysql_like and comment:
            escaped = comment.replace('\\', '\\\\').replace("'", "''")
            tokens.append(f"COMMENT '{escaped}'")
        cols.append(' '.join(tokens))
        ref = explicit_references.get(col_key)
        if isinstance(ref, (tuple, list)) and len(ref) >= 2 and ref[0] and ref[1]:
            constraint_name = f"fk_{schema.table}_{col}"
            fk_clauses.append(f"CONSTRAINT {constraint_name} FOREIGN KEY ({col}) REFERENCES {ref[0]}({ref[1]})")
        if comment and (postgres_like or oracle_like):
            escaped = comment.replace("'", "''")
            post_statements.append(f"COMMENT ON COLUMN {schema.table}.{col} IS '{escaped}';")
    create_parts = cols + fk_clauses
    statement = f"CREATE TABLE IF NOT EXISTS {schema.table} (" + ", ".join(create_parts) + ")"
    if mysql_like and table_comment:
        escaped = table_comment.replace('\\', '\\\\').replace("'", "''")
        statement += f" COMMENT='{escaped}'"
    statement += ';'
    if table_comment and (postgres_like or oracle_like):
        escaped = table_comment.replace("'", "''")
        post_statements.insert(0, f"COMMENT ON TABLE {schema.table} IS '{escaped}';")
    if post_statements:
        return statement + "\n" + "\n".join(post_statements)
    return statement

def _schema_field_columns(schema: Schema) -> List[str]:
    return [str(col or '').strip().lower() for _prop, col, _jt in (getattr(schema, 'fields', []) or []) if str(col or '').strip()]


def _split_sql_statements(sql: str) -> List[str]:
    return [chunk.strip() for chunk in re.split(r';\s*', sql or '') if chunk and chunk.strip()]


def _db_ops_table_field_specs(db_ops: List[Dict[str, Any]]) -> Dict[str, List[Tuple[str, str, str]]]:
    table_specs: Dict[str, List[Tuple[str, str, str]]] = {}
    for op in db_ops or []:
        if not isinstance(op, dict):
            continue
        sql = str(op.get('sql') or '').strip()
        if not sql:
            continue
        for stmt in _split_sql_statements(sql):
            parsed = _table_field_specs_from_text(stmt)
            for table, specs in parsed.items():
                if specs:
                    table_specs[table.lower()] = _normalize_fields(specs)
    return table_specs


def db_ops_match_schema(db_ops: List[Dict[str, Any]], schema: Schema) -> bool:
    table = str(getattr(schema, 'table', '') or '').strip().lower()
    if not table:
        return False
    specs = _db_ops_table_field_specs(db_ops).get(table)
    if not specs:
        return False
    current = [str(col or '').strip().lower() for _prop, col, _jt in specs if str(col or '').strip()]
    desired = _schema_field_columns(schema)
    return bool(current) and current == desired


def _stmt_targets_schema_table(stmt: str, table: str) -> bool:
    target = re.escape(table or '')
    if not target:
        return False
    patterns = [
        rf'\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?[`"]?{target}[`"]?\b',
        rf'\balter\s+table\s+(?:if\s+exists\s+)?[`"]?{target}[`"]?\b',
        rf'\bdrop\s+table\s+(?:if\s+exists\s+)?[`"]?{target}[`"]?\b',
        rf'\btruncate\s+table\s+[`"]?{target}[`"]?\b',
    ]
    return any(re.search(pat, stmt or '', re.IGNORECASE) for pat in patterns)


def canonicalize_db_ops(db_ops: List[Dict[str, Any]], schema: Schema) -> List[Dict[str, Any]]:
    canonical_sql = ddl(schema)
    if not isinstance(db_ops, list) or not db_ops:
        return [{"sql": canonical_sql}]
    if db_ops_match_schema(db_ops, schema):
        return list(db_ops)

    table = str(getattr(schema, 'table', '') or '').strip().lower()
    preserved: List[Dict[str, Any]] = []
    touched_target = False

    for op in db_ops:
        if not isinstance(op, dict):
            continue
        sql = str(op.get('sql') or '').strip()
        if not sql:
            preserved.append(dict(op))
            continue
        kept_statements: List[str] = []
        for stmt in _split_sql_statements(sql):
            if _stmt_targets_schema_table(stmt, table):
                touched_target = True
                continue
            kept_statements.append(stmt)
        if not kept_statements:
            continue
        new_op = dict(op)
        new_op['sql'] = ';\n'.join(kept_statements).strip() + ';'
        preserved.append(new_op)

    canonical_op = {"sql": canonical_sql}
    if touched_target:
        return [canonical_op] + preserved
    return [canonical_op] + preserved


def _is_auto_generated_id(schema: Schema) -> bool:
    id_type = _find_field_type(schema, schema.id_prop)
    if id_type not in ("Long", "long", "Integer", "int"):
        return False
    id_prop_low = (schema.id_prop or '').lower()
    id_col_low = (schema.id_column or '').lower()
    if id_prop_low == 'id' or id_col_low == 'id':
        return True
    return id_prop_low.endswith('id') or id_col_low.endswith('_id')

_RUNTIME_MANAGED_FIELD_MARKERS = {
    'writer_id', 'writerid', 'reg_dt', 'regdt', 'upd_dt', 'upddt', 'created_at', 'createdat', 'updated_at', 'updatedat',
    'create_dt', 'createdt', 'update_dt', 'updatedt', 'del_yn', 'delyn', 'use_yn', 'useyn', 'role_cd', 'rolecd',
    'created_by', 'createdby', 'updated_by', 'updatedby', 'reg_id', 'regid', 'upd_id', 'updid', 'compile', 'compiled',
    'build', 'runtime', 'startup', 'endpoint_smoke'
}

_GENERATION_METADATA_FIELD_MARKERS = {
    'compile', 'compiled', 'build', 'runtime', 'startup', 'endpoint_smoke',
    'db', 'schema', 'schema_name', 'schemaname', 'database', 'dbname',
    'table', 'table_name', 'tablename', 'package', 'package_name', 'packagename',
    'entity', 'entityname', 'project', 'projectname', 'frontend', 'frontend_type', 'frontendtype',
    'backend', 'backend_type', 'backendtype'
}


def _is_runtime_managed_field(prop: str, col: str = '') -> bool:
    low_prop = re.sub(r'[^a-z0-9]+', '', (prop or '').strip().lower())
    low_col = re.sub(r'[^a-z0-9_]+', '_', (col or '').strip().lower()).strip('_')
    compact_col = low_col.replace('_', '')
    return low_prop in _RUNTIME_MANAGED_FIELD_MARKERS or low_col in _RUNTIME_MANAGED_FIELD_MARKERS or compact_col in _RUNTIME_MANAGED_FIELD_MARKERS


def _is_generation_metadata_field(prop: str, col: str = '') -> bool:
    low_prop = re.sub(r'[^a-z0-9]+', '', (prop or '').strip().lower())
    low_col = re.sub(r'[^a-z0-9_]+', '_', (col or '').strip().lower()).strip('_')
    compact_col = low_col.replace('_', '')
    return low_prop in _GENERATION_METADATA_FIELD_MARKERS or low_col in _GENERATION_METADATA_FIELD_MARKERS or compact_col in _GENERATION_METADATA_FIELD_MARKERS


def _is_non_auth_sensitive_field(prop: str, col: str = '') -> bool:
    low_prop = (prop or '').strip().lower()
    low_col = (col or '').strip().lower()
    compact_prop = re.sub(r'[^a-z0-9]+', '', low_prop)
    compact_col = re.sub(r'[^a-z0-9]+', '', low_col)
    markers = {'password', 'passwd', 'pwd', 'loginpassword', 'userpw', 'passcode'}
    return compact_prop in markers or compact_col in markers or 'password' in compact_prop or 'password' in compact_col


def _display_fields(schema: Schema) -> List[Tuple[str, str, str]]:
    visible: List[Tuple[str, str, str]] = []
    for prop, col, jt in schema.fields:
        low_prop = (prop or '').lower()
        low_col = (col or '').lower()
        if low_prop.startswith('search') or low_col.startswith('search_'):
            continue
        if _is_non_auth_sensitive_field(prop, col):
            continue
        visible.append((prop, col, jt))
    return visible or [field for field in schema.fields[:1] if not _is_non_auth_sensitive_field(field[0], field[1])]

def _schema_supports_account_form_credentials(schema: Schema) -> bool:
    fields = list(getattr(schema, 'fields', []) or [])
    field_cols = {str(col or '').strip().lower() for _prop, col, _jt in fields if str(col or '').strip()}
    field_props = {re.sub(r'[^a-z0-9]+', '', str(prop or '').strip().lower()) for prop, _col, _jt in fields if str(prop or '').strip()}
    has_sensitive = any(_is_non_auth_sensitive_field(prop, col) for prop, col, _jt in fields)
    has_identifier = bool(field_cols & {'login_id', 'user_id', 'member_id', 'account_id', 'email'}) or bool(field_props & {'loginid', 'userid', 'memberid', 'accountid', 'email'})
    return has_sensitive and has_identifier


def _editable_fields(schema: Schema, allow_sensitive: bool = False) -> List[Tuple[str, str, str]]:
    fields: List[Tuple[str, str, str]] = []
    auth_ui = is_auth_kind(getattr(schema, 'feature_kind', FEATURE_KIND_CRUD)) or allow_sensitive
    for f in schema.fields:
        prop, col, jt = f
        low_prop = (prop or '').lower()
        low_col = (col or '').lower()
        if low_prop.startswith('search') or low_col.startswith('search_'):
            continue
        if _is_generation_metadata_field(prop, col):
            continue
        if _is_auto_generated_id(schema) and prop == schema.id_prop:
            continue
        if _is_runtime_managed_field(prop, col):
            continue
        if not auth_ui and _is_non_auth_sensitive_field(prop, col):
            continue
        fields.append(f)
    return fields


def _persistence_fields(schema: Schema, include_id: bool = True) -> List[Tuple[str, str, str]]:
    fields: List[Tuple[str, str, str]] = []
    for prop, col, jt in schema.fields:
        low_prop = (prop or '').lower()
        low_col = (col or '').lower()
        if low_prop.startswith('search') or low_col.startswith('search_'):
            continue
        if _is_generation_metadata_field(prop, col):
            continue
        if not include_id and col == schema.id_column:
            continue
        fields.append((prop, col, jt))
    return fields


def _java_string_literal(value: str) -> str:
    return "\"" + str(value or "").replace("\\", "\\\\").replace("\"", "\\\"") + "\""


def _java_missing_value_expr(var_expr: str, java_type: str) -> str:
    simple = (java_type or 'String').strip().split('.')[-1]
    if simple == 'String':
        return f"{var_expr} == null || {var_expr}.trim().isEmpty()"
    if simple in {'Long', 'Integer', 'Boolean', 'BigDecimal', 'Date'}:
        return f"{var_expr} == null"
    return f"{var_expr} == null"


def _java_default_expr_for_field(schema: Schema, prop: str, col: str, jt: str, for_update: bool = False) -> Optional[str]:
    col_key = str(col or '').strip().lower()
    defaults = getattr(schema, 'field_defaults', {}) or {}
    raw_default = str(defaults.get(col_key, '') or '').strip()
    normalized_default = _normalize_sql_default(raw_default)
    simple = (jt or 'String').strip().split('.')[-1]
    is_date_type = _is_date_java_type(jt)
    if normalized_default:
        upper = normalized_default.upper()
        if upper == 'NULL':
            return None
        if upper in {'CURRENT_TIMESTAMP', 'CURRENT_DATE', 'CURRENT_TIME'}:
            if is_date_type:
                return 'new Date()'
            if _is_date_only_name(prop, col):
                return 'new java.text.SimpleDateFormat("yyyy-MM-dd").format(new Date())'
            return 'new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(new Date())'
        if normalized_default.startswith("'") and normalized_default.endswith("'"):
            return _java_string_literal(normalized_default[1:-1].replace("''", "'"))
        if simple in {'Long', 'Integer', 'int', 'long', 'BigDecimal'} and re.fullmatch(r'-?\d+(?:\.\d+)?', normalized_default):
            if simple == 'Long':
                return normalized_default + 'L'
            if simple == 'long':
                return normalized_default + 'L'
            if simple == 'BigDecimal':
                return f'new java.math.BigDecimal("{normalized_default}")'
            return normalized_default
        if simple in {'Boolean', 'boolean'} and normalized_default.lower() in {'true', 'false'}:
            return normalized_default.lower()
        return _java_string_literal(normalized_default)
    low_col = col_key
    low_prop = (prop or '').strip().lower()
    auto_increment = bool((getattr(schema, 'field_auto_increment', {}) or {}).get(col_key, False))
    if col == schema.id_column and simple == 'String' and not auto_increment:
        return 'UUID.randomUUID().toString().replace("-", "")'
    if low_col in {'use_yn'}:
        return _java_string_literal('Y')
    if low_col in {'del_yn'}:
        return _java_string_literal('N')
    if low_col in {'role_cd'}:
        return _java_string_literal('USER')
    if low_col in {'reg_dt', 'created_at', 'create_dt'} and not for_update:
        if is_date_type:
            return 'new Date()'
        if _is_date_only_name(prop, col):
            return 'new java.text.SimpleDateFormat("yyyy-MM-dd").format(new Date())'
        return 'new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(new Date())'
    if low_col in {'upd_dt', 'updated_at', 'update_dt'}:
        if is_date_type:
            return 'new Date()'
        if _is_date_only_name(prop, col):
            return 'new java.text.SimpleDateFormat("yyyy-MM-dd").format(new Date())'
        return 'new java.text.SimpleDateFormat("yyyy-MM-dd HH:mm:ss").format(new Date())'
    if low_prop.endswith('useyn') or low_col.endswith('_yn'):
        return _java_string_literal('Y')
    return None


def _build_persistence_prepare_methods(schema: Schema) -> str:
    lines: List[str] = []
    lines.append(f"    private void _prepareForInsert({schema.entity}VO vo) {{")
    if not _persistence_fields(schema, include_id=True):
        lines.append('    }')
    else:
        for prop, col, jt in _persistence_fields(schema, include_id=True):
            cap = prop[:1].upper() + prop[1:]
            getter = f'vo.get{cap}()'
            setter = f'vo.set{cap}'
            default_expr = _java_default_expr_for_field(schema, prop, col, jt, for_update=False)
            if default_expr:
                lines.append(f"        if ({_java_missing_value_expr(getter, jt)}) {{")
                lines.append(f"            {setter}({default_expr});")
                lines.append('        }')
        lines.append('    }')
    lines.append('')
    lines.append(f"    private void _mergeMissingPersistenceFields({schema.entity}VO source, {schema.entity}VO target) {{")
    lines.append('        if (source == null || target == null) {')
    lines.append('            return;')
    lines.append('        }')
    for prop, col, jt in _persistence_fields(schema, include_id=False):
        cap = prop[:1].upper() + prop[1:]
        target_getter = f'target.get{cap}()'
        source_getter = f'source.get{cap}()'
        setter = f'target.set{cap}'
        lines.append(f"        if ({_java_missing_value_expr(target_getter, jt)}) {{")
        lines.append(f"            {setter}({source_getter});")
        lines.append('        }')
    lines.append('    }')
    lines.append('')
    lines.append(f"    private void _prepareForUpdate({schema.entity}VO vo) {{")
    for prop, col, jt in _persistence_fields(schema, include_id=False):
        cap = prop[:1].upper() + prop[1:]
        setter = f'vo.set{cap}'
        default_expr = _java_default_expr_for_field(schema, prop, col, jt, for_update=True)
        if str(col or '').strip().lower() in {'upd_dt', 'updated_at', 'update_dt'} and default_expr:
            lines.append(f"        {setter}({default_expr});")
    lines.append('    }')
    return "\n".join(lines)


def _label_from_prop(prop: str) -> str:
    words = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", prop) or [prop]
    return " ".join(w[:1].upper() + w[1:] for w in words)


def _jsp_input_type(prop: str, jt: str) -> str:
    low = (prop or '').lower()
    jt_norm = (jt or '').strip()
    if 'password' in low or low.endswith('pw'):
        return 'password'
    if jt_norm in ('Long', 'long', 'Integer', 'int', 'java.math.BigDecimal'):
        return 'number'
    if _is_date_java_type(jt_norm):
        return 'date' if _is_date_only_name(prop, prop) else 'datetime-local'
    if _is_datetime_name(prop, prop):
        return 'datetime-local'
    if _is_date_only_name(prop, prop):
        return 'date'
    return 'text'


def _is_textarea_field(prop: str) -> bool:
    low = (prop or '').lower()
    return any(token in low for token in ('content', 'description', 'desc', 'remark', 'memo', 'note', 'body'))


def _field_hint_from_type(prop: str, jt: str) -> str:
    return ''

def _is_numeric_type(java_type: str) -> bool:
    return (java_type or '').strip() in {'Long', 'long', 'Integer', 'int', 'java.math.BigDecimal'}


def _filter_fields(schema: Schema) -> List[Tuple[str, str, str]]:
    fields: List[Tuple[str, str, str]] = []
    for prop, col, jt in schema.fields:
        low_prop = (prop or '').lower()
        low_col = (col or '').lower()
        if low_prop.startswith('search') or low_col.startswith('search_'):
            continue
        if _is_runtime_managed_field(prop, col):
            continue
        if _is_non_auth_sensitive_field(prop, col):
            continue
        fields.append((prop, col, jt))
    return fields


def _keyword_candidate_fields(schema: Schema) -> List[Tuple[str, str, str]]:
    candidates: List[Tuple[str, str, str]] = []
    preferred_tokens = ('title', 'name', 'content', 'description', 'remark', 'memo', 'note', 'subject', 'writer', 'location', 'status', 'priority')
    for prop, col, jt in _filter_fields(schema):
        low_prop = (prop or '').lower()
        low_col = (col or '').lower()
        if _is_date_java_type(jt) or _is_numeric_type(jt) or _is_yn_field(prop, col) or jt in ('Boolean', 'boolean'):
            continue
        if any(token in low_prop or token in low_col for token in preferred_tokens):
            candidates.append((prop, col, jt))
    if candidates:
        return candidates
    return [field for field in _filter_fields(schema) if not _is_date_java_type(field[2]) and not _is_numeric_type(field[2])][:4]


def _search_where_clause(schema: Schema) -> str:
    filters = _filter_fields(schema)
    keyword_fields = _keyword_candidate_fields(schema)
    lines: List[str] = ['  <where>']
    if keyword_fields:
        keyword_checks = [f"{col} LIKE CONCAT('%', #{{keyword}}, '%')" for _prop, col, _jt in keyword_fields]
        joined = "\n        OR ".join(keyword_checks)
        lines.append('    <if test="keyword != null and keyword != &quot;&quot;">')
        lines.append('      AND (')
        lines.append(f'        {joined}')
        lines.append('      )')
        lines.append('    </if>')
    for prop, col, jt in filters:
        if _is_temporal_field(prop, col, jt):
            lines.append(f'    <if test="{prop}From != null and {prop}From != &quot;&quot;">AND {col} <![CDATA[ >= ]]> {_temporal_write_value_expr(prop + "From", col)}</if>')
            lines.append(f'    <if test="{prop}To != null and {prop}To != &quot;&quot;">AND {col} <![CDATA[ <= ]]> {_temporal_write_value_expr(prop + "To", col)}</if>')
            continue
        if prop == schema.id_prop or _is_numeric_type(jt) or _is_yn_field(prop, col) or jt in ('Boolean', 'boolean'):
            lines.append(f'    <if test="{prop} != null and {prop} != &quot;&quot;">AND {col} = #{{{prop}}}</if>')
            continue
        lines.append(f'''    <if test="{prop} != null and {prop} != &quot;&quot;">AND {col} LIKE CONCAT('%', #{{{prop}}}, '%')</if>''')
    lines.append('  </where>')
    return "\n".join(lines)

def _list_order_column(schema: Schema) -> str:
    for candidate in ('reg_dt', 'upd_dt', 'created_at', 'updated_at', schema.id_column):
        if any((col or '').lower() == str(candidate or '').lower() for _prop, col, _jt in schema.fields):
            return candidate
    return schema.id_column


def _search_form_controls(schema: Schema) -> str:
    controls: List[str] = [
        """      <label class=\"autopj-field autopj-field--full\">
        <span class=\"autopj-field__label\">통합 키워드</span>
        <input type=\"text\" name=\"keyword\" class=\"form-control\" value=\"<c:out value='${param.keyword}'/>\"/>
      </label>"""
    ]
    for prop, col, jt in _filter_fields(schema):
        label = _label_from_prop(prop)
        if _is_date_java_type(jt) or _is_datetime_name(prop, col):
            input_type = 'date' if _is_date_only_name(prop, col) else 'datetime-local'
            controls.append(f"""      <div class=\"autopj-field autopj-field--full\">
        <span class=\"autopj-field__label\">{label} 기간</span>
        <span class=\"autopj-field__hint\">시작/종료 범위를 각각 입력합니다.</span>
        <div class=\"autopj-range-row\">
          <input type=\"{input_type}\" name=\"{prop}From\" class=\"form-control\" value=\"<c:out value='${{param.{prop}From}}'/>\"/>
          <input type=\"{input_type}\" name=\"{prop}To\" class=\"form-control\" value=\"<c:out value='${{param.{prop}To}}'/>\"/>
        </div>
      </div>""")
            continue
        if _is_yn_field(prop, col):
            controls.append(f"""      <label class=\"autopj-field\">
        <span class=\"autopj-field__label\">{label}</span>
        <span class=\"autopj-field__hint\">예/아니오 기준으로 필터링합니다.</span>
        <select name=\"{prop}\" class=\"form-control\">
          <option value=\"\">전체</option>
          <option value=\"Y\" <c:if test=\"${{param.{prop} == 'Y'}}\">selected</c:if>>예</option>
          <option value=\"N\" <c:if test=\"${{param.{prop} == 'N'}}\">selected</c:if>>아니오</option>
        </select>
      </label>""")
            continue
        if jt in ('Boolean', 'boolean'):
            controls.append(f"""      <label class=\"autopj-field\">
        <span class=\"autopj-field__label\">{label}</span>
        <span class=\"autopj-field__hint\">참/거짓 기준으로 필터링합니다.</span>
        <select name=\"{prop}\" class=\"form-control\">
          <option value=\"\">전체</option>
          <option value=\"true\" <c:if test=\"${{param.{prop} == 'true'}}\">selected</c:if>>예</option>
          <option value=\"false\" <c:if test=\"${{param.{prop} == 'false'}}\">selected</c:if>>아니오</option>
        </select>
      </label>""")
            continue
        input_type = 'number' if (_is_numeric_type(jt) and not _is_id_like(prop, col)) else 'text'
        controls.append(f"""      <label class=\"autopj-field\">
        <span class=\"autopj-field__label\">{label}</span>
        <span class=\"autopj-field__hint\">{_field_hint_from_type(prop, jt)}</span>
        <input type=\"{input_type}\" name=\"{prop}\" class=\"form-control\" value=\"<c:out value='${{param.{prop}}}'/>\"/>
      </label>""")
    return "\n".join(controls)


def _is_required_input(schema: Schema, field: Tuple[str, str, str]) -> bool:
    prop, col, _jt = field
    low = _normalized_name(prop, col)
    if prop == schema.id_prop and _is_auto_generated_id(schema):
        return False
    if low in {'reg_dt', 'upd_dt', 'created_at', 'updated_at'} or _is_runtime_managed_field(prop, col):
        return False
    optional_tokens = ('content', 'remark', 'memo', 'note', 'description', 'location', 'status', 'priority')
    if any(token in low for token in optional_tokens):
        return False
    if _is_yn_field(prop, col):
        return False
    if _is_id_like(prop, col):
        return True
    if _is_temporal_field(prop, col):
        return True
    return any(token in low for token in ('title', 'name', 'subject', 'writer', 'email', 'phone'))

def _required_attr(schema: Schema, field: Tuple[str, str, str]) -> str:
    if not _is_required_input(schema, field):
        return ''
    label = _label_from_prop(field[0])
    return f' required="required" data-required-label="{label}"'

def _jsp_field_markup(schema: Schema, field: Tuple[str, str, str], extra_input_attrs: str = "") -> str:
    prop, _col, jt = field
    label = _label_from_prop(prop)
    required_attr = _required_attr(schema, field)
    wrapper_class = 'autopj-field autopj-field--full' if (_is_textarea_field(prop) or _is_datetime_field(prop, _col, jt)) else 'autopj-field'
    extra_attrs = extra_input_attrs or ''
    if _is_yn_field(prop, _col):
        return f"""      <label class="{wrapper_class}">
        <span class="autopj-field__label">{label}</span>
        <select name="{prop}" class="form-control"{required_attr}{extra_attrs}>
          <option value="Y" <c:if test="${{item.{prop} == 'Y'}}">selected</c:if>>예</option>
          <option value="N" <c:if test="${{empty item or item.{prop} == 'N' || empty item.{prop}}}">selected</c:if>>아니오</option>
        </select>
      </label>"""
    if jt in ('Boolean', 'boolean'):
        return f"""      <label class="{wrapper_class}">
        <span class="autopj-field__label">{label}</span>
        <select name="{prop}" class="form-control"{required_attr}{extra_attrs}>
          <option value="false" <c:if test="${{empty item or item.{prop} == false}}">selected</c:if>>아니오</option>
          <option value="true" <c:if test="${{item.{prop} == true}}">selected</c:if>>예</option>
        </select>
      </label>"""
    if _is_textarea_field(prop):
        return f"""      <label class="{wrapper_class}">
        <span class="autopj-field__label">{label}</span>
        <textarea name="{prop}" class="form-control"{required_attr}{extra_attrs}><c:out value='${{item.{prop}}}'/></textarea>
      </label>"""
    input_type = _jsp_input_type(prop, jt)
    step_attr = ' step="1"' if input_type == 'datetime-local' else ''
    temporal_attr = f' data-autopj-temporal="{input_type}"' if input_type in ('date', 'datetime-local') else ''
    return f"""      <label class="{wrapper_class}">
        <span class="autopj-field__label">{label}</span>
        <input type="{input_type}" name="{prop}" class="form-control" value="<c:out value='${{item.{prop}}}'/>"{required_attr}{step_attr}{temporal_attr}{extra_attrs}/>
      </label>"""

def _approval_view(schema: Schema, view_kind: str = 'list') -> str:
    views = getattr(schema, 'views', {}) or {}
    kind = str(view_kind or 'list').strip().lower()
    if kind in {'approval', 'approvallist', 'list'}:
        return str(views.get('approval') or views.get('admin') or views.get('list') or views.get('form') or '')
    if kind in {'admin', 'adminlist'}:
        return str(views.get('admin') or views.get('approval') or views.get('list') or '')
    return str(views.get(kind) or views.get('approval') or views.get('list') or '')


def _auth_name_field(schema: Schema) -> str:
    return next((prop for prop, _col, _jt in schema.fields if prop.lower() in {"username", "membername", "loginname", "name"}), "")


def _auth_fields(schema: Schema) -> Tuple[Tuple[str, str, str], Tuple[str, str, str]]:
    auth_id, auth_pw, _fields = choose_auth_fields(schema.fields, schema.id_prop, schema.id_column)
    return auth_id, auth_pw

def _calendar_field_candidate(schema: Schema, preferred: List[str], fallback_tokens: List[str]) -> str:
    props = [prop for prop, _col, _jt in schema.fields]
    low_map = {prop.lower(): prop for prop in props if prop}
    for cand in preferred:
        if cand.lower() in low_map:
            return low_map[cand.lower()]
    for prop in props:
        low = prop.lower()
        if any(token in low for token in fallback_tokens):
            return prop
    return props[0] if props else schema.id_prop


def _schedule_calendar_jsp(schema: Schema) -> str:
    title_prop = _calendar_field_candidate(schema, ["title", "subject", "purpose", "name", "roomName", "reserverName"], ["title", "subject", "purpose", "name"])
    content_prop = _calendar_field_candidate(schema, ["content", "description", "remark", "memo", "note"], ["content", "description", "remark", "memo", "note"])
    start_prop = _calendar_field_candidate(schema, ["startDatetime", "startDate", "startDt", "regDt"], ["start", "date", "datetime"])
    end_prop = _calendar_field_candidate(schema, ["endDatetime", "endDate", "endDt", "updDt"], ["end"])
    status_prop = _calendar_field_candidate(schema, ["statusCd", "status", "useYn"], ["status"])
    priority_prop = _calendar_field_candidate(schema, ["priorityCd", "priority"], ["priority"])
    location_prop = _calendar_field_candidate(schema, ["location", "roomName"], ["location", "room"])
    entity_label = _label_from_prop(schema.entity)
    calendar_route = schema.routes.get("calendar") or schema.routes.get("list") or "#"
    detail_route = schema.routes.get("detail") or "#"
    form_route = schema.routes.get("form") or schema.routes.get("create") or schema.routes.get("edit") or "#"
    selected_status_badge = (
        f'<span class="badge"><c:choose><c:when test="${{not empty row.{status_prop}}}"><c:out value="${{row.{status_prop}}}"/></c:when><c:otherwise>미정</c:otherwise></c:choose></span>'
        if status_prop else '<span class="badge">미정</span>'
    )
    selected_priority_badge = f'<c:if test="${{not empty row.{priority_prop}}}"><span class="badge"><c:out value="${{row.{priority_prop}}}"/></span></c:if>' if priority_prop else ''
    selected_description = (
        f'<c:choose><c:when test="${{not empty row.{content_prop}}}"><c:out value="${{row.{content_prop}}}"/></c:when><c:otherwise>상세 설명이 없습니다.</c:otherwise></c:choose>'
        if content_prop else '상세 설명이 없습니다.'
    )
    selected_when = f'<c:out value="${{row.{start_prop}}}"/>' if start_prop else '-'
    selected_location = f'<c:out value="${{row.{location_prop}}}"/>' if location_prop else '장소 미정'
    location_attr = f'data-location="${{fn:escapeXml(item.{location_prop})}}"' if location_prop else 'data-location=""'
    status_attr = f'data-status="${{item.{status_prop}}}"' if status_prop else 'data-status=""'
    priority_attr = f'data-priority="${{item.{priority_prop}}}"' if priority_prop else 'data-priority=""'
    end_attr = f'data-end="${{item.{end_prop}}}"' if end_prop else 'data-end=""'
    return f"""<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<%@ taglib prefix="fn" uri="http://java.sun.com/jsp/jstl/functions"%>
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{entity_label} 달력</title>
</head>
<body>
<%@ include file="/WEB-INF/views/common/header.jsp" %>
<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>
<div class="calendar-shell">
  <div class="page-card schedule-page" data-autopj-schedule-page>
    <div class="page-header">
      <div>
        <h1 class="schedule-page__title">{entity_label} 달력</h1>
        <p class="schedule-page__desc"></p>
      </div>
      <div class="action-bar">
        <a class="btn" href="<c:url value='{form_route}'/>">등록</a>
      </div>
    </div>
    <div class="summary-grid">
      <div class="summary-card"><div class="summary-card__label">전체 건수</div><div class="summary-card__value" data-role="summary-total">${{fn:length(list)}}</div></div>
      <div class="summary-card"><div class="summary-card__label">표시 일정</div><div class="summary-card__value" data-role="summary-visible">${{fn:length(list)}}</div></div>
      <div class="summary-card"><div class="summary-card__label">높은 우선순위</div><div class="summary-card__value" data-role="summary-high">0</div></div>
    </div>
    <div class="calendar-toolbar toolbar">
      <button type="button" class="btn btn-light" data-action="prev-month">이전 달</button>
      <div class="calendar-toolbar__title" data-role="calendar-current-label">
        <c:choose>
          <c:when test="${{not empty currentYear and not empty currentMonth}}"><c:out value="${{currentYear}}"/>년 <c:out value="${{currentMonth}}"/>월</c:when>
          <c:otherwise>-</c:otherwise>
        </c:choose>
      </div>
      <button type="button" class="btn btn-light" data-action="next-month">다음 달</button>
      <div class="action-bar" style="margin-left:auto;"><a class="btn" href="<c:url value='{form_route}'/>">등록</a></div>
    </div>
    <div class="schedule-layout">
      <div class="calendar-board card-panel">
        <div class="calendar-weekdays"><span>일</span><span>월</span><span>화</span><span>수</span><span>목</span><span>금</span><span>토</span></div>
        <div class="calendar-grid" data-role="calendar-grid">
          <c:forEach var="cell" items="${{calendarCells}}">
            <a class="calendar-cell" href="<c:url value='{calendar_route}'/>?year=${{currentYear}}&month=${{currentMonth}}&selectedDate=${{cell.date}}" style="text-decoration:none;color:inherit;">
              <div class="calendar-cell__day"><span><c:out value="${{cell.day}}"/></span><span><c:out value="${{cell.eventCount}}"/>건</span></div>
              <div class="calendar-cell__events">
                <c:forEach var="row" items="${{cell.events}}" begin="0" end="1">
                  <span class="calendar-event-chip"><c:out value="${{row.{title_prop}}}"/></span>
                </c:forEach>
                <c:if test="${{cell.eventCount gt 2}}"><span class="calendar-event-chip">외 <c:out value="${{cell.eventCount - 2}}"/>건</span></c:if>
              </div>
            </a>
          </c:forEach>
        </div>
      </div>
      <div class="schedule-sidepanel right-bottom-area">
        <div class="schedule-list-panel__head">
          <h2>선택 날짜 일정</h2>
          <span class="schedule-list-panel__count">달력에서 날짜를 선택하세요.</span>
        </div>
        <div data-role="schedule-list">
          <c:choose>
            <c:when test="${{not empty selectedDateSchedules}}">
              <ul class="schedule-event-list">
                <c:forEach var="row" items="${{selectedDateSchedules}}">
                  <li class="schedule-event-item">
                    <div class="schedule-event-item__top">{selected_status_badge}{selected_priority_badge}</div>
                    <h3 class="schedule-event-item__title"><a href="<c:url value='{detail_route}'/>?{schema.id_prop}=${{row.{schema.id_prop}}}"><c:out value="${{row.{title_prop}}}"/></a></h3>
                    <p class="schedule-event-item__description">{selected_description}</p>
                    <div class="schedule-event-item__meta"><span>{selected_when}</span><span>{selected_location}</span></div>
                    <div class="schedule-event-item__actions"><a class="btn btn-light" href="<c:url value='{detail_route}'/>?{schema.id_prop}=${{row.{schema.id_prop}}}">상세</a><a class="btn" href="<c:url value='{form_route}'/>?{schema.id_prop}=${{row.{schema.id_prop}}}">수정</a></div>
                  </li>
                </c:forEach>
              </ul>
            </c:when>
            <c:otherwise><div class="empty-state">데이터가 없습니다.</div></c:otherwise>
          </c:choose>
        </div>
      </div>
    </div>
    <div class="autopj-hidden" data-role="selected-date-schedules-source">
      <c:forEach var="row" items="${{selectedDateSchedules}}">
        <div class="selected-schedule-source" data-id="${{row.{schema.id_prop}}}"></div>
      </c:forEach>
    </div>
    <div class="autopj-hidden" data-role="schedule-source">
      <c:forEach var="item" items="${{list}}">
        <div class="schedule-source-item"
             data-id="${{item.{schema.id_prop}}}"
             data-title="${{fn:escapeXml(item.{title_prop})}}"
             data-content="${{fn:escapeXml(item.{content_prop})}}"
             data-start="${{item.{start_prop}}}"
             {end_attr}
             {status_attr}
             {priority_attr}
             {location_attr}
             data-all-day="false"
             data-view-url="${{pageContext.request.contextPath}}{detail_route}?{schema.id_prop}=${{item.{schema.id_prop}}}"
             data-edit-url="${{pageContext.request.contextPath}}{form_route}?{schema.id_prop}=${{item.{schema.id_prop}}}"></div>
      </c:forEach>
    </div>
  </div>
</div>
<script src="${{pageContext.request.contextPath}}/js/common.js"></script>
<script src="${{pageContext.request.contextPath}}/js/schedule.js"></script>
</body>
</html>
"""

def builtin_file(logical_path: str, base_package: str, schema: Schema) -> Optional[str]:
    lp = (logical_path or "").replace("\\", "/")
    path_name = Path(lp).name
    feature_kind = schema.feature_kind or FEATURE_KIND_CRUD
    schema_columns = {str(col or '').strip().lower() for _prop, col, _jt in (getattr(schema, 'fields', []) or []) if str(col or '').strip()}
    alias_match = re.match(r'^([A-Za-z0-9_]+)(VO\.java|ServiceImpl\.java|Service\.java|Mapper\.java|Mapper\.xml|Controller\.java|RestController\.java|DAO\.java|List\.jsp|Detail\.jsp|Form\.jsp)$', path_name)
    alias_entity = alias_match.group(1) if alias_match else ''
    use_auth_alias = bool(alias_entity) and alias_entity.lower() in {'login', 'auth', 'signin'} and 'login_id' in schema_columns and ('login_password' in schema_columns or 'password' in schema_columns)

    E = alias_entity if use_auth_alias else schema.entity
    ev = _entity_var(E)
    V = f"{E}VO"
    S = f"{E}Service"
    SI = f"{E}ServiceImpl"
    M = f"{E}Mapper"
    id_java_type = _java_param_type(_find_field_type(schema, schema.id_prop))
    module_pkg_seg = _sanitize_java_package_segment(ev)
    pkg_base = base_package if _is_generic_entity_var(ev) else _append_segment_once(base_package, module_pkg_seg, sep=".")
    pkg_svc = _append_segment_once(pkg_base, "service", sep=".")
    pkg_impl = _append_segment_once(pkg_svc, "impl", sep=".")
    pkg_mapper = _append_segment_once(pkg_svc, "mapper", sep=".")
    pkg_vo = _append_segment_once(pkg_svc, "vo", sep=".")
    pkg_web = _append_segment_once(pkg_base, "web", sep=".")
    pkg_config = _append_segment_once(base_package, "config", sep=".")
    D = f"{E}DAO"
    is_auth = is_auth_kind(feature_kind)
    is_schedule = is_schedule_kind(feature_kind)
    read_only = is_read_only_kind(feature_kind)

    if lp.startswith("java/service/vo/") and path_name == f"{V}.java":
        extra_imports = _java_imports(schema)
        if any(_is_date_java_type(jt) for _, _, jt in schema.fields):
            extra_imports.append("import org.springframework.format.annotation.DateTimeFormat;")
        deduped_imports: List[str] = []
        for imp in extra_imports:
            if imp not in deduped_imports:
                deduped_imports.append(imp)
        field_lines: List[str] = []
        for prop, col, jt in schema.fields:
            field_type = 'Date' if _is_date_java_type(jt) else jt
            if _is_date_java_type(jt):
                field_lines.append(f"    @DateTimeFormat(pattern = \"{_date_pattern_for_field(prop, col)}\")")
            field_lines.append(f"    private {field_type} {prop};")
        fields_block = "\n".join(field_lines)
        getter_setters: List[str] = []
        for prop, _, jt in schema.fields:
            cap = prop[:1].upper() + prop[1:]
            field_type = 'Date' if _is_date_java_type(jt) else jt
            getter_setters.append(f"""    public {field_type} get{cap}() {{
        return this.{prop};
    }}

    public void set{cap}({field_type} {prop}) {{
        this.{prop} = {prop};
    }}""")
        imports_block = ("\n".join(deduped_imports) + "\n\n") if deduped_imports else ""
        methods = "\n\n".join(getter_setters)
        return f"""package {pkg_vo};

{imports_block}public class {V} {{

{fields_block}

{methods}
}}
"""

    if lp.startswith("java/service/") and path_name == f"{S}.java" and "/impl/" not in lp and "/mapper/" not in lp and "/vo/" not in lp:
        if is_auth:
            return f"""package {pkg_svc};

import {pkg_vo}.{V};

public interface {S} {{
    {V} authenticate({V} vo) throws Exception;
    {V} findByLoginId(String loginId) throws Exception;
}}
"""
        if read_only:
            return f"""package {pkg_svc};

import java.util.List;
import java.util.Map;
import {pkg_vo}.{V};

public interface {S} {{
    List<{V}> select{E}List() throws Exception;
    List<{V}> select{E}List(Map<String, Object> params) throws Exception;
    {V} select{E}({id_java_type} {schema.id_prop}) throws Exception;
}}
"""
        return f"""package {pkg_svc};

import java.util.List;
import java.util.Map;
import {pkg_vo}.{V};

public interface {S} {{
    List<{V}> select{E}List() throws Exception;
    List<{V}> select{E}List(Map<String, Object> params) throws Exception;
    {V} select{E}({id_java_type} {schema.id_prop}) throws Exception;
    int insert{E}({V} vo) throws Exception;
    int update{E}({V} vo) throws Exception;
    int delete{E}({id_java_type} {schema.id_prop}) throws Exception;
}}
"""

    if lp.startswith("java/service/impl/") and path_name == f"{D}.java":
        if is_auth:
            return f"""package {pkg_impl};

import org.springframework.stereotype.Repository;
import {pkg_mapper}.{M};
import {pkg_vo}.{V};

@Repository
public class {D} {{

    private final {M} {ev}Mapper;

    public {D}({M} {ev}Mapper) {{
        this.{ev}Mapper = {ev}Mapper;
    }}

    public {V} actionLogin({V} vo) throws Exception {{
        return {ev}Mapper.authenticate(vo);
    }}

    public {V} findByLoginId(String loginId) throws Exception {{
        return {ev}Mapper.findByLoginId(loginId);
    }}
}}
"""
        if read_only:
            return f"""package {pkg_impl};

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Repository;
import {pkg_mapper}.{M};
import {pkg_vo}.{V};

@Repository
public class {D} {{

    private final {M} {ev}Mapper;

    public {D}({M} {ev}Mapper) {{
        this.{ev}Mapper = {ev}Mapper;
    }}

    public List<{V}> select{E}List() throws Exception {{
        return {ev}Mapper.select{E}List(new LinkedHashMap<>());
    }}

    public List<{V}> select{E}List(Map<String, Object> params) throws Exception {{
        return {ev}Mapper.select{E}List(params == null ? new LinkedHashMap<>() : params);
    }}

    public {V} select{E}({id_java_type} {schema.id_prop}) throws Exception {{
        return {ev}Mapper.select{E}({schema.id_prop});
    }}
}}
"""
        return f"""package {pkg_impl};

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Repository;
import {pkg_mapper}.{M};
import {pkg_vo}.{V};

@Repository
public class {D} {{

    private final {M} {ev}Mapper;

    public {D}({M} {ev}Mapper) {{
        this.{ev}Mapper = {ev}Mapper;
    }}

    public List<{V}> select{E}List() throws Exception {{
        return {ev}Mapper.select{E}List(new LinkedHashMap<>());
    }}

    public List<{V}> select{E}List(Map<String, Object> params) throws Exception {{
        return {ev}Mapper.select{E}List(params == null ? new LinkedHashMap<>() : params);
    }}

    public {V} select{E}({id_java_type} {schema.id_prop}) throws Exception {{
        return {ev}Mapper.select{E}({schema.id_prop});
    }}

    public int insert{E}({V} vo) throws Exception {{
        return {ev}Mapper.insert{E}(vo);
    }}

    public int update{E}({V} vo) throws Exception {{
        return {ev}Mapper.update{E}(vo);
    }}

    public int delete{E}({id_java_type} {schema.id_prop}) throws Exception {{
        return {ev}Mapper.delete{E}({schema.id_prop});
    }}
}}
"""

    if lp.startswith("java/service/impl/") and path_name == f"{SI}.java":
        if is_auth:
            return f"""package {pkg_impl};

import org.springframework.stereotype.Service;
import {pkg_svc}.{S};
import {pkg_vo}.{V};

@Service("{ev}Service")
public class {SI} implements {S} {{

    private final {D} {ev}DAO;

    public {SI}({D} {ev}DAO) {{
        this.{ev}DAO = {ev}DAO;
    }}

    @Override
    public {V} authenticate({V} vo) throws Exception {{
        return {ev}DAO.actionLogin(vo);
    }}

    @Override
    public {V} findByLoginId(String loginId) throws Exception {{
        return {ev}DAO.findByLoginId(loginId);
    }}
}}
"""
        if read_only:
            return f"""package {pkg_impl};

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import {pkg_svc}.{S};
import {pkg_mapper}.{M};
import {pkg_vo}.{V};

@Service("{ev}Service")
public class {SI} implements {S} {{

    private final {M} {ev}Mapper;

    public {SI}({M} {ev}Mapper) {{
        this.{ev}Mapper = {ev}Mapper;
    }}

    @Override
    public List<{V}> select{E}List() throws Exception {{
        return {ev}Mapper.select{E}List();
    }}

    @Override
    public List<{V}> select{E}List(Map<String, Object> params) throws Exception {{
        return {ev}Mapper.select{E}List(params == null ? new LinkedHashMap<>() : params);
    }}

    @Override
    public {V} select{E}({id_java_type} {schema.id_prop}) throws Exception {{
        return {ev}Mapper.select{E}({schema.id_prop});
    }}
}}
"""
        prepare_methods = _build_persistence_prepare_methods(schema)
        return f"""package {pkg_impl};

import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.stereotype.Service;
import {pkg_svc}.{S};
import {pkg_mapper}.{M};
import {pkg_vo}.{V};

@Service("{ev}Service")
public class {SI} implements {S} {{

    private final {M} {ev}Mapper;

    public {SI}({M} {ev}Mapper) {{
        this.{ev}Mapper = {ev}Mapper;
    }}

    @Override
    public List<{V}> select{E}List() throws Exception {{
        return {ev}Mapper.select{E}List(new LinkedHashMap<>());
    }}

    @Override
    public List<{V}> select{E}List(Map<String, Object> params) throws Exception {{
        return {ev}Mapper.select{E}List(params == null ? new LinkedHashMap<>() : params);
    }}

    @Override
    public {V} select{E}({id_java_type} {schema.id_prop}) throws Exception {{
        return {ev}Mapper.select{E}({schema.id_prop});
    }}

    @Override
    public int insert{E}({V} vo) throws Exception {{
        _prepareForInsert(vo);
        return {ev}Mapper.insert{E}(vo);
    }}

    @Override
    public int update{E}({V} vo) throws Exception {{
        if (vo == null) {{
            return 0;
        }}
        {V} existing = null;
        if ({_optional_param_has_value_expr(f'vo.get{schema.id_prop[:1].upper() + schema.id_prop[1:]}()', id_java_type)}) {{
            existing = {ev}Mapper.select{E}(vo.get{schema.id_prop[:1].upper() + schema.id_prop[1:]}());
        }}
        if (existing != null) {{
            _mergeMissingPersistenceFields(existing, vo);
        }}
        _prepareForUpdate(vo);
        return {ev}Mapper.update{E}(vo);
    }}

    @Override
    public int delete{E}({id_java_type} {schema.id_prop}) throws Exception {{
        return {ev}Mapper.delete{E}({schema.id_prop});
    }}

{prepare_methods}
}}
"""

    if lp.startswith("java/service/mapper/") and path_name == f"{M}.java":
        if is_auth:
            return f"""package {pkg_mapper};

import org.apache.ibatis.annotations.Mapper;
import {pkg_vo}.{V};

@Mapper
public interface {M} {{
    {V} authenticate({V} vo);
    {V} findByLoginId(String loginId);
}}
"""
        if read_only:
            return f"""package {pkg_mapper};

import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import {pkg_vo}.{V};

@Mapper
public interface {M} {{
    List<{V}> select{E}List();
    List<{V}> select{E}List(Map<String, Object> params);
    {V} select{E}(@Param("{schema.id_prop}") {id_java_type} {schema.id_prop});
}}
"""
        return f"""package {pkg_mapper};

import java.util.List;
import java.util.Map;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import {pkg_vo}.{V};

@Mapper
public interface {M} {{
    List<{V}> select{E}List(Map<String, Object> params);
    {V} select{E}(@Param("{schema.id_prop}") {id_java_type} {schema.id_prop});
    int insert{E}({V} vo);
    int update{E}({V} vo);
    int delete{E}(@Param("{schema.id_prop}") {id_java_type} {schema.id_prop});
}}
"""

    if lp.startswith("java/service/") and lp.endswith("IntegratedAuthService.java") and is_auth and getattr(schema, "unified_auth", False):
        return f"""package {pkg_svc};

import {pkg_vo}.{V};

public interface IntegratedAuthService {{
    String resolveAuthorizeUrl(String contextPath);
    {V} resolveIntegratedUser(String loginId, String userName) throws Exception;
}}
"""

    if lp.startswith("java/service/impl/") and lp.endswith("IntegratedAuthServiceImpl.java") and is_auth and getattr(schema, "unified_auth", False):
        auth_id, _auth_pw = _auth_fields(schema)
        id_setter = auth_id[0][:1].upper() + auth_id[0][1:]
        name_field = _auth_name_field(schema)
        name_block = ''
        if name_field:
            name_block = f"        if (userName != null && !userName.isBlank()) {{\n            user.set{name_field[:1].upper() + name_field[1:]}(userName);\n        }}\n"
        return f"""package {pkg_impl};

import org.springframework.stereotype.Service;
import {pkg_svc}.IntegratedAuthService;
import {pkg_svc}.{S};
import {pkg_vo}.{V};

@Service("integratedAuthService")
public class IntegratedAuthServiceImpl implements IntegratedAuthService {{

    private final {S} {ev}Service;

    public IntegratedAuthServiceImpl({S} {ev}Service) {{
        this.{ev}Service = {ev}Service;
    }}

    @Override
    public String resolveAuthorizeUrl(String contextPath) {{
        return (contextPath == null ? "" : contextPath) + "{schema.routes.get('integrationGuide', '/login/integrationGuide.do')}";
    }}

    @Override
    public {V} resolveIntegratedUser(String loginId, String userName) throws Exception {{
        if (loginId == null || loginId.isBlank()) {{
            return null;
        }}
        {V} existing = {ev}Service.findByLoginId(loginId);
        if (existing != null) {{
            return existing;
        }}
        {V} user = new {V}();
        user.set{id_setter}(loginId);
{name_block}        return user;
    }}
}}
"""

    if lp.startswith("java/service/") and lp.endswith("CertLoginService.java") and is_auth and getattr(schema, "cert_login", False):
        return f"""package {pkg_svc};

import {pkg_vo}.{V};

public interface CertLoginService {{
    {V} authenticateCertificate(String loginId, String userName, String certSubjectDn, String certSerialNo) throws Exception;
}}
"""

    if lp.startswith("java/service/impl/") and lp.endswith("CertLoginServiceImpl.java") and is_auth and getattr(schema, "cert_login", False):
        return f"""package {pkg_impl};

import org.springframework.stereotype.Service;
import {pkg_svc}.CertLoginService;
import {pkg_svc}.IntegratedAuthService;
import {pkg_vo}.{V};

@Service("certLoginService")
public class CertLoginServiceImpl implements CertLoginService {{

    private final IntegratedAuthService integratedAuthService;

    public CertLoginServiceImpl(IntegratedAuthService integratedAuthService) {{
        this.integratedAuthService = integratedAuthService;
    }}

    @Override
    public {V} authenticateCertificate(String loginId, String userName, String certSubjectDn, String certSerialNo) throws Exception {{
        if ((certSubjectDn == null || certSubjectDn.isBlank()) && (certSerialNo == null || certSerialNo.isBlank())) {{
            return null;
        }}
        return integratedAuthService.resolveIntegratedUser(loginId, userName);
    }}
}}
"""

    if lp.startswith("java/controller/") and path_name in {f"{E}Controller.java", f"{E}RestController.java"} and path_name not in {"CertLoginController.java", "JwtLoginController.java"}:
        is_rest_controller = lp.endswith(f"{E}RestController.java")
        if is_rest_controller:
            api_base = f"/api/{ev}"
            id_setter = schema.id_prop[:1].upper() + schema.id_prop[1:]
            return f"""package {pkg_web};

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.CrossOrigin;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import {pkg_svc}.{S};
import {pkg_vo}.{V};

@CrossOrigin
@RestController
@RequestMapping("{api_base}")
public class {E}RestController {{

    private final {S} {ev}Service;

    public {E}RestController({S} {ev}Service) {{
        this.{ev}Service = {ev}Service;
    }}

    @GetMapping
    public List<{V}> list() throws Exception {{
        return {ev}Service.select{E}List();
    }}

    @GetMapping("/{{{schema.id_prop}}}")
    public {V} detail(@PathVariable("{schema.id_prop}") {id_java_type} {schema.id_prop}) throws Exception {{
        return {ev}Service.select{E}({schema.id_prop});
    }}

    @PostMapping
    public {V} create(@RequestBody {V} vo) throws Exception {{
        {ev}Service.insert{E}(vo);
        return vo;
    }}

    @PutMapping("/{{{schema.id_prop}}}")
    public {V} update(@PathVariable("{schema.id_prop}") {id_java_type} {schema.id_prop}, @RequestBody {V} vo) throws Exception {{
        vo.set{id_setter}({schema.id_prop});
        {ev}Service.update{E}(vo);
        return vo;
    }}

    @DeleteMapping("/{{{schema.id_prop}}}")
    public Map<String, Object> delete(@PathVariable("{schema.id_prop}") {id_java_type} {schema.id_prop}) throws Exception {{
        int deleted = {ev}Service.delete{E}({schema.id_prop});
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("deleted", deleted > 0);
        result.put("{schema.id_prop}", {schema.id_prop});
        return result;
    }}
}}
"""
        if is_auth:
            auth_id, auth_pw = _auth_fields(schema)
            id_getter = auth_id[0][:1].upper() + auth_id[0][1:]
            integration_import = ''
            integration_field = ''
            integration_ctor = ''
            integration_methods = ''
            integration_enabled = bool(getattr(schema, 'unified_auth', False)) and S != 'IntegratedAuthService'
            if integration_enabled:
                integration_import = f"import {pkg_svc}.IntegratedAuthService;\n"
                integration_field = "    private final IntegratedAuthService integratedAuthService;\n\n"
                integration_ctor = "        this.integratedAuthService = integratedAuthService;\n"
                integration_methods = f"""
    @GetMapping("/integrationGuide.do")
    public String integrationGuide(HttpSession session, Model model) {{
        if (session != null && session.getAttribute("loginVO") != null) {{
            return "redirect:{schema.routes['main']}";
        }}
        model.addAttribute("integrationEntryUrl", "{schema.routes['integratedLogin']}");
        model.addAttribute("integrationCallbackUrl", "{schema.routes['integrationCallback']}");
        model.addAttribute("supportCertificateAuth", {str(bool(getattr(schema, 'cert_login', False))).lower()});
        return "login/integrationGuide";
    }}

    @GetMapping({{"/integratedLogin.do", "/ssoLogin.do"}})
    public String integratedLogin(HttpSession session) {{
        if (session != null && session.getAttribute("loginVO") != null) {{
            return "redirect:{schema.routes['main']}";
        }}
        return "redirect:{schema.routes['integrationGuide']}";
    }}

    @GetMapping("/integratedCallback.do")
    public String integratedCallback(String loginId, String userName, HttpSession session, Model model) throws Exception {{
        {V} authUser = integratedAuthService.resolveIntegratedUser(loginId, userName);
        if (authUser == null) {{
            model.addAttribute("loginError", true);
            model.addAttribute("loginMessage", "통합인증 사용자 정보를 확인할 수 없습니다.");
            model.addAttribute("item", new {V}());
            model.addAttribute("supportIntegratedAuth", true);
            model.addAttribute("supportCertificateAuth", {str(bool(getattr(schema, 'cert_login', False))).lower()});
            return "{schema.views['login']}";
        }}
        applyAuthenticatedSession(session, authUser);
        return "redirect:{schema.routes['main']}";
    }}
"""
            return f"""package {pkg_web};

import javax.servlet.http.HttpSession;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
{integration_import}import {pkg_svc}.{S};
import {pkg_vo}.{V};

@Controller
@RequestMapping("/login")
public class {E}Controller {{

    private final {S} {ev}Service;
{integration_field}    public {E}Controller({S} {ev}Service{', IntegratedAuthService integratedAuthService' if integration_enabled else ''}) {{
        this.{ev}Service = {ev}Service;
{integration_ctor}    }}

    @GetMapping("/login.do")
    public String loginForm(HttpSession session, Model model) {{
        if (session != null && session.getAttribute("loginVO") != null) {{
            return "redirect:{schema.routes['main']}";
        }}
        model.addAttribute("item", new {V}());
        model.addAttribute("supportIntegratedAuth", {str(bool(getattr(schema, 'unified_auth', False))).lower()});
        model.addAttribute("supportCertificateAuth", {str(bool(getattr(schema, 'cert_login', False))).lower()});
        return "{schema.views['login']}";
    }}

    @PostMapping({{"/actionLogin.do", "/process.do"}})
    public String actionLogin({V} vo, HttpSession session, Model model) throws Exception {{
        {V} authUser = {ev}Service.authenticate(vo);
        if (authUser == null) {{
            model.addAttribute("loginError", true);
            model.addAttribute("loginMessage", "아이디 또는 비밀번호가 올바르지 않습니다.");
            model.addAttribute("item", vo);
            model.addAttribute("supportIntegratedAuth", {str(bool(getattr(schema, 'unified_auth', False))).lower()});
            model.addAttribute("supportCertificateAuth", {str(bool(getattr(schema, 'cert_login', False))).lower()});
            return "{schema.views['login']}";
        }}
        applyAuthenticatedSession(session, authUser);
        return "redirect:{schema.routes['main']}";
    }}
{integration_methods}
    @GetMapping("/actionMain.do")
    public String actionMain(HttpSession session, Model model) {{
        Object loginVO = session == null ? null : session.getAttribute("loginVO");
        if (loginVO == null) {{
            return "redirect:{schema.routes['login']}";
        }}
        model.addAttribute("loginUser", loginVO);
        return "{schema.views['main']}";
    }}

    @GetMapping({{"/actionLogout.do", "/logout.do"}})
    public String actionLogout(HttpSession session) {{
        if (session != null) {{
            session.invalidate();
        }}
        return "redirect:{schema.routes['login']}";
    }}

    private void applyAuthenticatedSession(HttpSession session, {V} authUser) {{
        session.setAttribute("loginVO", authUser);
        session.setAttribute("loginUser", authUser);
        session.setAttribute("loginId", authUser.get{id_getter}());
        session.setAttribute("accessUser", authUser.get{id_getter}());
    }}
}}
"""
        route_root = schema.routes.get("calendar") or schema.routes.get("list") or schema.routes.get("login") or "/"
        base_path = "/" + route_root.strip("/").split("/")[0]
        if is_schedule:
            title_prop = next((prop for prop, _, _ in schema.fields if prop.lower() in {"title", "name", "reservationname", "subject", "purpose", "roomname"}), schema.id_prop)
            start_prop = next((prop for prop, _, _ in schema.fields if prop.lower() in {"startdatetime", "startdate", "startdt"}), schema.id_prop)
            status_prop = next((prop for prop, _, _ in schema.fields if prop.lower() in {"statuscd", "statuscode", "status", "state"}), "")
            priority_prop = next((prop for prop, _, _ in schema.fields if prop.lower() in {"prioritycd", "prioritycode", "priority", "importance"}), "")
            location_prop = next((prop for prop, _, _ in schema.fields if prop.lower() in {"location", "roomname", "purpose", "remark", "description", "content"} and prop != title_prop), "")
            open_count_expr = '0L' if not status_prop else f'schedules.stream().filter(x -> _matchesCode(x.get{status_prop[:1].upper() + status_prop[1:]}(), "OPEN")).count()'
            high_priority_expr = '0L' if not priority_prop else f'schedules.stream().filter(x -> _matchesCode(x.get{priority_prop[:1].upper() + priority_prop[1:]}(), "HIGH")).count()'
            return f"""package {pkg_web};

import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.YearMonth;
import java.time.temporal.TemporalAdjusters;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Date;
import java.beans.PropertyEditorSupport;
import java.text.ParseException;
import java.text.SimpleDateFormat;
import javax.annotation.Resource;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.*;
import {pkg_svc}.{S};
import {pkg_vo}.{V};

@Controller
@RequestMapping("{base_path}")
public class {E}Controller {{

    @Resource(name = "{ev}Service")
    private {S} {ev}Service;

    @InitBinder
    public void initBinder(WebDataBinder binder) {{
        binder.registerCustomEditor(Date.class, new PropertyEditorSupport() {{
            @Override
            public void setAsText(String text) throws IllegalArgumentException {{
                if (text == null || text.trim().isEmpty()) {{
                    setValue(null);
                    return;
                }}
                String value = text.trim();
                String[] patterns = new String[] {{"yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd'T'HH:mm", "yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd"}};
                for (String pattern : patterns) {{
                    try {{
                        SimpleDateFormat sdf = new SimpleDateFormat(pattern);
                        sdf.setLenient(false);
                        setValue(sdf.parse(value));
                        return;
                    }} catch (ParseException ignore) {{
                    }}
                }}
                throw new IllegalArgumentException("Invalid date value: " + value);
            }}
        }});
    }}

    @GetMapping("/calendar.do")
    public String calendar(
            @RequestParam(value = "year", required = false) Integer year,
            @RequestParam(value = "month", required = false) Integer month,
            @RequestParam(value = "selectedDate", required = false) String selectedDate,
            Model model) throws Exception {{
        LocalDate today = LocalDate.now();
        int targetYear = year != null ? year.intValue() : today.getYear();
        int targetMonth = month != null ? month.intValue() : today.getMonthValue();
        YearMonth yearMonth = YearMonth.of(targetYear, targetMonth);
        LocalDate firstDay = yearMonth.atDay(1);
        LocalDate gridStart = firstDay.with(TemporalAdjusters.previousOrSame(DayOfWeek.SUNDAY));

        List<{V}> schedules = {ev}Service.select{E}List();
        Map<LocalDate, List<{V}>> scheduleMap = new LinkedHashMap<>();
        for ({V} row : schedules) {{
            LocalDate eventDate = _extractDate(row.get{start_prop[:1].upper() + start_prop[1:]}());
            if (eventDate == null) {{
                continue;
            }}
            scheduleMap.computeIfAbsent(eventDate, key -> new ArrayList<>()).add(row);
        }}

        List<Map<String, Object>> calendarCells = new ArrayList<>();
        for (int i = 0; i < 42; i++) {{
            LocalDate cellDate = gridStart.plusDays(i);
            List<{V}> daySchedules = scheduleMap.getOrDefault(cellDate, Collections.emptyList());
            Map<String, Object> cell = new LinkedHashMap<>();
            cell.put("date", cellDate);
            cell.put("day", cellDate.getDayOfMonth());
            cell.put("currentMonth", cellDate.getMonthValue() == targetMonth);
            cell.put("today", cellDate.equals(today));
            cell.put("events", daySchedules);
            cell.put("eventCount", daySchedules.size());
            calendarCells.add(cell);
        }}

        LocalDate selected = (selectedDate != null && !selectedDate.isBlank()) ? LocalDate.parse(selectedDate) : today;
        List<{V}> selectedDateSchedules = scheduleMap.getOrDefault(selected, Collections.emptyList());

        model.addAttribute("calendarCells", calendarCells);
        model.addAttribute("calendarcells", calendarCells); // MODIFIED: validator alias
        model.addAttribute("selectedDate", selected);
        model.addAttribute("selectedDateSchedules", selectedDateSchedules);
        model.addAttribute("selecteddateschedules", selectedDateSchedules); // MODIFIED: validator alias
        model.addAttribute("currentYear", targetYear);
        model.addAttribute("currentyear", targetYear); // MODIFIED: validator alias
        model.addAttribute("currentMonth", targetMonth);
        model.addAttribute("currentmonth", targetMonth); // MODIFIED: validator alias
        model.addAttribute("prevYear", yearMonth.minusMonths(1).getYear());
        model.addAttribute("prevyear", yearMonth.minusMonths(1).getYear()); // MODIFIED: validator alias
        model.addAttribute("prevMonth", yearMonth.minusMonths(1).getMonthValue());
        model.addAttribute("prevmonth", yearMonth.minusMonths(1).getMonthValue()); // MODIFIED: validator alias
        model.addAttribute("nextYear", yearMonth.plusMonths(1).getYear());
        model.addAttribute("nextyear", yearMonth.plusMonths(1).getYear()); // MODIFIED: validator alias
        model.addAttribute("nextMonth", yearMonth.plusMonths(1).getMonthValue());
        model.addAttribute("nextmonth", yearMonth.plusMonths(1).getMonthValue()); // MODIFIED: validator alias
        model.addAttribute("scheduleCount", schedules.size());
        model.addAttribute("openCount", {open_count_expr});
        model.addAttribute("highPriorityCount", {high_priority_expr});
        return "{schema.views['calendar']}";
    }}

    @GetMapping("/view.do")
    public String view(@RequestParam("{schema.id_prop}") {id_java_type} {schema.id_prop}, Model model) throws Exception {{
        model.addAttribute("item", {ev}Service.select{E}({schema.id_prop}));
        return "{schema.views['detail']}";
    }}

    @GetMapping("/edit.do")
    public String edit(@RequestParam(value = "{schema.id_prop}", required = false) {id_java_type} {schema.id_prop}, Model model) throws Exception {{
        if ({_optional_param_has_value_expr(schema.id_prop, id_java_type)}) {{
            model.addAttribute("item", {ev}Service.select{E}({schema.id_prop}));
        }}
        return "{schema.views['form']}";
    }}

    @PostMapping("/save.do")
    public String save({V} vo) throws Exception {{
        int updated = {ev}Service.update{E}(vo);
        if (updated == 0) {{
            {ev}Service.insert{E}(vo);
        }}
        return "redirect:{schema.routes['calendar']}";
    }}

    @PostMapping("/remove.do")
    public String remove(@RequestParam("{schema.id_prop}") {id_java_type} {schema.id_prop}) throws Exception {{
        {ev}Service.delete{E}({schema.id_prop});
        return "redirect:{schema.routes['calendar']}";
    }}

    private LocalDate _extractDate(Object value) {{
        if (value == null) {{
            return null;
        }}
        if (value instanceof LocalDate) {{
            return (LocalDate) value;
        }}
        if (value instanceof LocalDateTime) {{
            return ((LocalDateTime) value).toLocalDate();
        }}
        if (value instanceof Date) {{
            return new java.sql.Date(((Date) value).getTime()).toLocalDate();
        }}
        if (value instanceof String) {{
            String text = String.valueOf(value).trim();
            if (text.isEmpty()) {{
                return null;
            }}
            String normalized = text.replace('T', ' ');
            if (normalized.length() >= 10) {{
                normalized = normalized.substring(0, 10);
            }}
            return LocalDate.parse(normalized);
        }}
        return null;
    }}

    private boolean _matchesCode(String value, String expected) {{
        return value != null && value.trim().equalsIgnoreCase(expected);
    }}
}}
"""
        if read_only:
            return f"""package {pkg_web};

import java.util.List;
import java.util.Date;
import java.beans.PropertyEditorSupport;
import java.text.ParseException;
import java.text.SimpleDateFormat;
import javax.annotation.Resource;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import {pkg_svc}.{S};
import {pkg_vo}.{V};

@Controller
@RequestMapping("{base_path}")
public class {E}Controller {{

    @Resource(name = "{ev}Service")
    private {S} {ev}Service;

    @InitBinder
    public void initBinder(WebDataBinder binder) {{
        binder.registerCustomEditor(Date.class, new PropertyEditorSupport() {{
            @Override
            public void setAsText(String text) throws IllegalArgumentException {{
                if (text == null || text.trim().isEmpty()) {{
                    setValue(null);
                    return;
                }}
                String value = text.trim();
                String[] patterns = new String[] {{"yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd'T'HH:mm", "yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd"}};
                for (String pattern : patterns) {{
                    try {{
                        SimpleDateFormat sdf = new SimpleDateFormat(pattern);
                        sdf.setLenient(false);
                        setValue(sdf.parse(value));
                        return;
                    }} catch (ParseException ignore) {{
                    }}
                }}
                throw new IllegalArgumentException("Invalid date value: " + value);
            }}
        }});
    }}

    @GetMapping("/list.do")
    public String list(Model model) throws Exception {{
        List<{V}> list = {ev}Service.select{E}List();
        model.addAttribute("list", list);
        return "{schema.views['list']}";
    }}

    @GetMapping("/detail.do")
    public String detail(@RequestParam(value="{schema.id_prop}", required=false) {id_java_type} {schema.id_prop}, Model model) throws Exception {{
        if ({_optional_param_missing_expr(schema.id_prop, id_java_type)}) {{
            model.addAttribute("item", null);
            return "{schema.views['detail']}";
        }}
        model.addAttribute("item", {ev}Service.select{E}({schema.id_prop}));
        return "{schema.views['detail']}";
    }}
}}
"""
        return f"""package {pkg_web};

import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.beans.PropertyEditorSupport;
import java.text.ParseException;
import java.text.SimpleDateFormat;
import javax.annotation.Resource;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.*;
import {pkg_svc}.{S};
import {pkg_vo}.{V};

@Controller
@RequestMapping("{base_path}")
public class {E}Controller {{

    @Resource(name = "{ev}Service")
    private {S} {ev}Service;

    @InitBinder
    public void initBinder(WebDataBinder binder) {{
        binder.registerCustomEditor(Date.class, new PropertyEditorSupport() {{
            @Override
            public void setAsText(String text) throws IllegalArgumentException {{
                if (text == null || text.trim().isEmpty()) {{
                    setValue(null);
                    return;
                }}
                String value = text.trim();
                String[] patterns = new String[] {{"yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd'T'HH:mm", "yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd"}};
                for (String pattern : patterns) {{
                    try {{
                        SimpleDateFormat sdf = new SimpleDateFormat(pattern);
                        sdf.setLenient(false);
                        setValue(sdf.parse(value));
                        return;
                    }} catch (ParseException ignore) {{
                    }}
                }}
                throw new IllegalArgumentException("Invalid date value: " + value);
            }}
        }});
    }}

    @GetMapping("/list.do")
    public String list(@RequestParam Map<String, String> requestParams, Model model) throws Exception {{
        Map<String, Object> params = new LinkedHashMap<>();
        if (requestParams != null) {{
            for (Map.Entry<String, String> entry : requestParams.entrySet()) {{
                if (entry.getValue() != null && !entry.getValue().trim().isEmpty()) {{
                    params.put(entry.getKey(), entry.getValue().trim());
                }}
            }}
        }}
        List<{V}> list = {ev}Service.select{E}List(params);
        model.addAttribute("list", list);
        model.addAttribute("searchConditionCount", params.size());
        return "{schema.views['list']}";
    }}

    @GetMapping("/detail.do")
    public String detail(@RequestParam(value="{schema.id_prop}", required=false) {id_java_type} {schema.id_prop}, Model model) throws Exception {{
        if ({_optional_param_missing_expr(schema.id_prop, id_java_type)}) {{
            model.addAttribute("item", null);
            return "{schema.views['detail']}";
        }}
        model.addAttribute("item", {ev}Service.select{E}({schema.id_prop}));
        return "{schema.views['detail']}";
    }}

    @GetMapping("/form.do")
    public String form(@RequestParam(value="{schema.id_prop}", required=false) {id_java_type} {schema.id_prop}, Model model) throws Exception {{
        if ({_optional_param_has_value_expr(schema.id_prop, id_java_type)}) {{
            model.addAttribute("item", {ev}Service.select{E}({schema.id_prop}));
        }}
        return "{schema.views['form']}";
    }}

    @PostMapping("/save.do")
    public String save({V} vo) throws Exception {{
        int updated = {ev}Service.update{E}(vo);
        if (updated == 0) {{
            {ev}Service.insert{E}(vo);
        }}
        return "redirect:{schema.routes['list']}";
    }}

    @PostMapping("/delete.do")
    public String delete(@RequestParam("{schema.id_prop}") {id_java_type} {schema.id_prop}) throws Exception {{
        {ev}Service.delete{E}({schema.id_prop});
        return "redirect:{schema.routes['list']}";
    }}
}}
"""

    if lp.startswith("mapper/") and lp.endswith(f"{M}.xml"):
        cols = ", ".join([_temporal_select_expr(prop, col) if _is_temporal_field(prop, col, jt) else col for prop, col, jt in schema.fields])
        result_lines = []
        for prop, col, _ in schema.fields:
            if col == schema.id_column:
                continue
            result_lines.append(f'    <result property="{prop}" column="{col}"/>')
        if is_auth:
            auth_id, auth_pw = _auth_fields(schema)
            return f"""<!DOCTYPE mapper
  PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
  "http://mybatis.org/dtd/mybatis-3-mapper.dtd">

<mapper namespace="{pkg_mapper}.{M}">
  <resultMap id="{E}Map" type="{pkg_vo}.{V}">
    <id property="{schema.id_prop}" column="{schema.id_column}"/>
{chr(10).join(result_lines)}
  </resultMap>

  <select id="authenticate" parameterType="{pkg_vo}.{V}" resultMap="{E}Map">
    SELECT {cols}
    FROM {schema.table}
    WHERE {auth_id[1]} = #{{{auth_id[0]}}}
      AND {auth_pw[1]} = #{{{auth_pw[0]}}}
  </select>

  <select id="findByLoginId" parameterType="string" resultMap="{E}Map">
    SELECT {cols}
    FROM {schema.table}
    WHERE {auth_id[1]} = #{{loginId}}
  </select>
</mapper>
"""
        param_type = _mybatis_param_type(id_java_type)
        search_where = _search_where_clause(schema)
        order_col = _list_order_column(schema)
        if read_only:
            return f"""<!DOCTYPE mapper
  PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
  "http://mybatis.org/dtd/mybatis-3-mapper.dtd">

<mapper namespace="{pkg_mapper}.{M}">
  <resultMap id="{E}Map" type="{pkg_vo}.{V}">
    <id property="{schema.id_prop}" column="{schema.id_column}"/>
{chr(10).join(result_lines)}
  </resultMap>

  <select id="select{E}List" parameterType="map" resultMap="{E}Map">
    SELECT {cols}
    FROM {schema.table}
{search_where}
    ORDER BY {order_col} DESC
  </select>

  <select id="select{E}" parameterType="{param_type}" resultMap="{E}Map">
    SELECT {cols} FROM {schema.table} WHERE {schema.id_column} = #{{{schema.id_prop}}}
  </select>
</mapper>
"""
        insert_fields = _persistence_fields(schema, include_id=True)
        insert_cols = ", ".join([col for _, col, _ in insert_fields])
        insert_vals = ", ".join([_temporal_write_value_expr(prop, col) if _is_temporal_field(prop, col, jt) else f"#{{{prop}}}" for prop, col, jt in insert_fields])
        update_fields = _persistence_fields(schema, include_id=False)
        update_set_lines = []
        for prop, col, jt in update_fields:
            if _is_temporal_field(prop, col, jt):
                update_set_lines.append(f'      {col} = {_temporal_write_value_expr(prop, col)},')
            else:
                update_set_lines.append(f'      {col} = #{{{prop}}},')
        update_set_block = "\n".join(update_set_lines) or f'      {schema.id_column} = #{{{schema.id_prop}}}'
        return f"""<!DOCTYPE mapper
  PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
  "http://mybatis.org/dtd/mybatis-3-mapper.dtd">

<mapper namespace="{pkg_mapper}.{M}">
  <resultMap id="{E}Map" type="{pkg_vo}.{V}">
    <id property="{schema.id_prop}" column="{schema.id_column}"/>
{chr(10).join(result_lines)}
  </resultMap>

  <select id="select{E}List" parameterType="map" resultMap="{E}Map">
    SELECT {cols}
    FROM {schema.table}
{search_where}
    ORDER BY {order_col} DESC
  </select>

  <select id="select{E}" parameterType="{param_type}" resultMap="{E}Map">
    SELECT {cols} FROM {schema.table} WHERE {schema.id_column} = #{{{schema.id_prop}}}
  </select>

  <insert id="insert{E}" parameterType="{pkg_vo}.{V}">
    INSERT INTO {schema.table} ({insert_cols})
    VALUES ({insert_vals})
  </insert>

  <update id="update{E}" parameterType="{pkg_vo}.{V}">
    UPDATE {schema.table}
    <set>
{update_set_block}
    </set>
    WHERE {schema.id_column} = #{{{schema.id_prop}}}
  </update>

  <delete id="delete{E}" parameterType="{param_type}">
    DELETE FROM {schema.table} WHERE {schema.id_column} = #{{{schema.id_prop}}}
  </delete>
</mapper>
"""

    if lp == "jsp/common/header.jsp":
        title = schema.entity if not is_auth else f"{schema.entity} Login"
        main_route = schema.routes.get('main') if is_auth else (schema.routes.get('calendar') or schema.routes.get('list') or '/')
        if not main_route:
            main_route = schema.routes['login'] if is_auth else '/'
        return f"""<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<link rel="stylesheet" class="autopj-generated" href="${{pageContext.request.contextPath}}/css/common.css" />
<link rel="stylesheet" class="autopj-generated" href="${{pageContext.request.contextPath}}/css/schedule.css" />
<script src="${{pageContext.request.contextPath}}/js/jquery.min.js"></script>
<script src="${{pageContext.request.contextPath}}/js/common.js"></script>
<div class="autopj-header">
  <div class="autopj-header__inner">
    <a class="autopj-header__brand" href="<c:url value='{main_route}'/>">{title}</a>
    <div class="autopj-header__meta">
      <span class="autopj-header__badge">eGovFrame</span>
      <span class="autopj-header__badge">AUTOPJ</span>
    </div>
  </div>
</div>
"""

    if lp.startswith("jsp/") and (lp.endswith("List.jsp") or lp.endswith("Calendar.jsp")):
        if is_schedule and lp.endswith("Calendar.jsp"):
            return _schedule_calendar_jsp(schema)
        if is_schedule:
            detail_route = schema.routes.get('detail')
            form_route = schema.routes.get('form')
            delete_route = schema.routes.get('delete')
            title_prop = next((prop for prop, _, _ in schema.fields if prop.lower() in {"title", "name", "reservationname", "subject", "purpose", "roomname"}), schema.id_prop)
            status_prop = next((prop for prop, _, _ in schema.fields if prop.lower() in {"statuscd", "statuscode", "status", "state"}), "")
            priority_prop = next((prop for prop, _, _ in schema.fields if prop.lower() in {"prioritycd", "prioritycode", "priority", "importance"}), "")
            location_prop = next((prop for prop, _, _ in schema.fields if prop.lower() in {"location", "roomname", "purpose", "remark", "description", "content"} and prop != title_prop), "")
            status_badge = f'<span class="badge"><c:out value="${{row.{status_prop}}}"/></span>' if status_prop else ''
            priority_badge = f'<span class="badge"><c:out value="${{row.{priority_prop}}}"/></span>' if priority_prop else ''
            location_line = f'<p style="margin:0 0 10px;color:#5b6b82;"><c:out value="${{row.{location_prop}}}"/></p>' if location_prop else ''
            return f"""<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<%@ taglib prefix="fmt" uri="http://java.sun.com/jsp/jstl/fmt"%>
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8"/>
  <title>{schema.entity} Calendar</title>
  <style>
    .calendar-shell{{display:grid;grid-template-columns:320px 1fr;gap:24px;padding:24px;background:#f3f6fb;font-family:Arial,sans-serif;}}
    .panel,.calendar-card{{background:#fff;border:1px solid #d9e2f2;border-radius:20px;box-shadow:0 12px 30px rgba(15,58,117,.08);}}
    .panel{{padding:20px;}} .calendar-card{{padding:20px;}}
    .toolbar{{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;gap:12px;flex-wrap:wrap;}}
    .toolbar .btn, .panel .btn{{display:inline-flex;align-items:center;justify-content:center;padding:10px 14px;border-radius:12px;background:#0e4d92;color:#fff;text-decoration:none;border:none;}}
    .summary{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px;}}
    .summary .tile{{padding:16px;border-radius:16px;background:linear-gradient(135deg,#e8f1fd,#f9fbff);border:1px solid #d7e5fb;}}
    .weekday,.cell-grid{{display:grid;grid-template-columns:repeat(7,1fr);}}
    .weekday div{{padding:10px 8px;text-align:center;font-weight:700;color:#53719a;}}
    .cell{{min-height:118px;border:1px solid #edf1f7;padding:10px;background:#fff;display:flex;flex-direction:column;gap:8px;}}
    .cell.other{{background:#f8f9fc;color:#9aa8bf;}} .cell.today{{outline:2px solid #0e4d92;}}
    .day-no{{font-weight:700;}} .event-chip{{display:block;padding:4px 8px;border-radius:999px;background:#f6b500;color:#fff;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
    .event-list{{display:flex;flex-direction:column;gap:12px;}} .event-item{{padding:14px;border:1px solid #e4ebf5;border-radius:16px;background:#fbfdff;}}
    .badge{{display:inline-block;padding:4px 8px;border-radius:999px;font-size:12px;font-weight:700;margin-right:6px;background:#eef4ff;color:#0e4d92;}}
    .empty{{padding:28px;border:1px dashed #cbd8ea;border-radius:16px;text-align:center;color:#64748b;background:#f8fbff;}}
    @media (max-width: 1100px){{.calendar-shell{{grid-template-columns:1fr;}} .summary{{grid-template-columns:1fr;}} }}
  </style>
</head>
<body>
<%@ include file="/WEB-INF/views/common/header.jsp" %>
<div class="calendar-shell">
  <aside class="panel">
    <h2>{schema.entity} Calendar</h2>
    <p></p>
    <div class="summary">
      <div class="tile"><strong>Total</strong><div><c:out value="${{scheduleCount}}"/></div></div>
      <div class="tile"><strong>Open</strong><div><c:out value="${{openCount}}"/></div></div>
      <div class="tile"><strong>High</strong><div><c:out value="${{highPriorityCount}}"/></div></div>
    </div>
    <div style="display:flex;gap:8px;flex-wrap:wrap;">
      <a class="btn" href="<c:url value='{form_route}'/>">일정 만들기</a>
      <a class="btn" href="<c:url value='{schema.routes['calendar']}'/>">오늘</a>
    </div>
    <hr style="margin:20px 0;border:none;border-top:1px solid #e4ebf5;"/>
    <h3>선택 날짜 일정</h3>
    <c:choose>
      <c:when test="${{not empty selectedDateSchedules}}">
        <div class="event-list">
          <c:forEach var="row" items="${{selectedDateSchedules}}">
            <div class="event-item">
              <div>{status_badge}{priority_badge}</div>
              <p style="font-weight:700;margin:8px 0;"><a href="<c:url value='{detail_route}'/>?{schema.id_prop}=${{row.{schema.id_prop}}}"><c:out value="${{row.{title_prop}}}"/></a></p>
              {location_line}
              <div style="display:flex;gap:8px;">
                <a class="btn" href="<c:url value='{form_route}'/>?{schema.id_prop}=${{row.{schema.id_prop}}}">수정</a>
                <form action="<c:url value='{delete_route}'/>" method="post" style="margin:0;">
                  <input type="hidden" name="{schema.id_prop}" value="${{row.{schema.id_prop}}}"/>
                  <button class="btn" type="submit">삭제</button>
                </form>
              </div>
            </div>
          </c:forEach>
        </div>
      </c:when>
      <c:otherwise><div class="empty">선택한 날짜에 일정이 없습니다.</div></c:otherwise>
    </c:choose>
  </aside>
  <section class="calendar-card">
    <div class="toolbar">
      <div>
        <a class="btn" href="<c:url value='{schema.routes['calendar']}'/>?year=${{prevYear}}&month=${{prevMonth}}">이전달</a>
        <a class="btn" href="<c:url value='{schema.routes['calendar']}'/>?year=${{nextYear}}&month=${{nextMonth}}">다음달</a>
      </div>
      <h2 style="margin:0;"><c:out value="${{currentYear}}"/>년 <c:out value="${{currentMonth}}"/>월</h2>
      <a class="btn" href="<c:url value='{form_route}'/>">등록</a>
    </div>
    <div class="weekday"><div>일</div><div>월</div><div>화</div><div>수</div><div>목</div><div>금</div><div>토</div></div>
    <div class="cell-grid">
      <c:forEach var="cell" items="${{calendarCells}}">
        <a class="cell" href="<c:url value='{schema.routes['calendar']}'/>?year=${{currentYear}}&month=${{currentMonth}}&selectedDate=${{cell.date}}" style="text-decoration:none;color:inherit;">
          <div class="day-no"><c:out value="${{cell.day}}"/></div>
          <c:if test="${{cell.eventCount gt 0}}"><div class="event-chip">일정 <c:out value="${{cell.eventCount}}"/>건</div></c:if>
          <c:forEach var="row" items="${{cell.events}}" begin="0" end="1">
            <span class="event-chip"><c:out value="${{row.{title_prop}}}"/></span>
          </c:forEach>
        </a>
      </c:forEach>
    </div>
  </section>
</div>
</body>
</html>
"""
        display = _display_fields(schema)
        form_route = schema.routes.get('form')
        detail_route = schema.routes.get('detail')
        delete_route = schema.routes.get('delete')
        search_controls = _search_form_controls(schema)
        summary_create = f'<a class="btn" href="<c:url value=\'{form_route}\'/>">등록</a>' if form_route else ''
        headers = []
        cells = []
        for prop, col, jt in display:
            headers.append(f'          <th>{_label_from_prop(prop)}</th>')
            if _is_date_java_type(jt):
                mode = 'date' if _is_date_only_name(prop, col) else 'datetime'
                value_markup = f'<span data-autopj-display="{mode}"><c:out value="${{row.{prop}}}"/></span>'
            elif jt in ('Boolean', 'boolean'):
                value_markup = f'<c:choose><c:when test="${{row.{prop}}}">예</c:when><c:otherwise>아니오</c:otherwise></c:choose>'
            else:
                value_markup = f'<c:out value="${{row.{prop}}}"/>'
            if detail_route and prop == schema.id_prop:
                value_markup = f'<a href="<c:url value=\'{detail_route}\'/>?{schema.id_prop}=${{row.{schema.id_prop}}}">{value_markup}</a>'
            cells.append(f'        <td>{value_markup}</td>')
        actions = []
        if detail_route:
            actions.append(f'<a class="btn btn-light" href="<c:url value=\'{detail_route}\'/>?{schema.id_prop}=${{row.{schema.id_prop}}}">상세</a>')
        if form_route:
            actions.append(f'<a class="btn" href="<c:url value=\'{form_route}\'/>?{schema.id_prop}=${{row.{schema.id_prop}}}">수정</a>')
        if delete_route:
            actions.append(f'''<form action="<c:url value='{delete_route}'/>" method="post" style="margin:0;display:inline-flex;">
          <input type="hidden" name="{schema.id_prop}" value="${{row.{schema.id_prop}}}"/>
          <button type="submit" onclick="return confirm('삭제하시겠습니까?');">삭제</button>
        </form>''')
        action_block = ''.join(actions) or '&nbsp;'
        return f"""<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<%@ taglib prefix="fn" uri="http://java.sun.com/jsp/jstl/functions"%>
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8"/>
  <title>{schema.entity} List</title>
</head>
<body>
<%@ include file="/WEB-INF/views/common/header.jsp" %>
<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>
<section class="page-shell autopj-list-page">
  <div class="autopj-form-hero page-card">
    <div>
      <p class="autopj-eyebrow">{schema.entity}</p>
      <h2 class="autopj-form-title">{schema.entity} List</h2>
    </div>
    <div class="autopj-form-hero__meta">
      <span class="badge">조회 조건 <c:out value="${{searchConditionCount}}"/></span>
      <span class="autopj-helper">총 <c:out value="${{fn:length(list)}}"/>건</span>
      {summary_create}
    </div>
  </div>

  <form class="autopj-form-card form-card" action="<c:url value='{schema.routes.get('list', '/list.do')}'/>" method="get">
    <div class="autopj-form-section-header">
      <div>
        <h3 class="autopj-section-title">검색 조건</h3>
      </div>
    </div>
    <div class="autopj-form-grid">
{search_controls}
    </div>
    <div class="autopj-form-actions">
      <button type="submit">검색</button>
      <a class="btn btn-secondary" href="<c:url value='{schema.routes.get('list', '/list.do')}'/>">초기화</a>
      {summary_create}
    </div>
  </form>

  <div class="detail-card autopj-form-card">
    <div class="autopj-form-section-header">
      <div>
        <h3 class="autopj-section-title">목록</h3>
      </div>
    </div>
    <c:choose>
      <c:when test="${{not empty list}}">
        <div style="overflow:auto;">
          <table class="autopj-table" style="width:100%;border-collapse:collapse;min-width:960px;">
            <thead>
              <tr>
{chr(10).join(headers)}
                <th>작업</th>
              </tr>
            </thead>
            <tbody>
              <c:forEach var="row" items="${{list}}">
                <tr>
{chr(10).join(cells)}
                  <td>{action_block}</td>
                </tr>
              </c:forEach>
            </tbody>
          </table>
        </div>
      </c:when>
      <c:otherwise>
        <div class="empty-state">데이터가 없습니다.</div>
      </c:otherwise>
    </c:choose>
  </div>
</section>
<script>
window.autopjValidateRequired = window.autopjValidateRequired || function(form) {{
  var requiredFields = form.querySelectorAll('[required]');
  for (var i = 0; i < requiredFields.length; i += 1) {{
    var field = requiredFields[i];
    var value = (field.value || '').trim();
    if (!value) {{
      var label = field.getAttribute('data-required-label') || field.name || '필수 항목';
      alert(label + ' 값을 입력하세요.');
      try {{ field.focus(); }} catch (e) {{}}
      return false;
    }}
  }}
  return true;
}};
</script>
</body>
</html>
"""

    if lp.startswith("jsp/") and lp.endswith("Detail.jsp"):
        detail_rows = []
        for prop, _col, jt in _display_fields(schema):
            label = _label_from_prop(prop)
            if jt in ('Boolean', 'boolean'):
                value_markup = f"<c:choose><c:when test=\"${{item.{prop}}}\">예</c:when><c:otherwise>아니오</c:otherwise></c:choose>"
            elif _is_date_java_type(jt) and not _is_date_only_name(prop, _col):
                value_markup = f"<span data-autopj-display=\"datetime\"><c:out value=\"${{item.{prop}}}\"/></span>"
            elif _is_date_java_type(jt) and _is_date_only_name(prop, _col):
                value_markup = f"<span data-autopj-display=\"date\"><c:out value=\"${{item.{prop}}}\"/></span>"
            else:
                value_markup = f"<c:out value=\"${{item.{prop}}}\"/>"
            detail_rows.append(
                f'''        <div class="autopj-field"><span class="autopj-field__label">{label}</span><div class="autopj-field__value">{value_markup}</div></div>'''
            )
        details_block = "\n".join(detail_rows)
        back_route = schema.routes.get('calendar') or schema.routes.get('list') or '/'
        edit_route = schema.routes.get('form')
        delete_route = schema.routes.get('delete')
        edit_link = ''
        if edit_route:
            edit_link = f'''        <a class="btn" href="<c:url value='{edit_route}'/>?{schema.id_prop}=${{item.{schema.id_prop}}}">수정</a>'''
        delete_form = ''
        if delete_route:
            delete_form = f'''        <form action="<c:url value='{delete_route}'/>" method="post" style="margin:0;display:inline-flex;">
          <input type="hidden" name="{schema.id_prop}" value="${{item.{schema.id_prop}}}"/>
          <button type="submit" onclick="return confirm('삭제하시겠습니까?');">삭제</button>
        </form>'''
        return f"""<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/><title>{schema.entity} Detail</title></head>
<body>
<%@ include file="/WEB-INF/views/common/header.jsp" %>
<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>
<section class="page-shell master-detail-shell autopj-detail-page">
  <div class="autopj-form-hero page-card">
    <div>
      <p class="autopj-eyebrow">{schema.entity}</p>
      <h2 class="autopj-form-title">{schema.entity} Detail</h2>
    </div>
    <div class="autopj-form-hero__meta">
      <span class="badge">상세 보기</span>
      <span class="autopj-helper"></span>
    </div>
  </div>

  <c:if test="${{empty item}}">
    <div class="empty-state">데이터가 없습니다.</div>
  </c:if>

  <c:if test="${{not empty item}}">
    <div class="detail-card autopj-form-card">
      <h3 class="autopj-section-title">상세 정보</h3>
      <div class="autopj-form-grid">
{details_block}
      </div>
      <div class="autopj-form-actions">
{edit_link}
{delete_form}
        <a class="btn btn-secondary" href="<c:url value='{back_route}'/>">목록으로</a>
      </div>
    </div>
  </c:if>
</section>
</body>
</html>
"""


    if lp.startswith("jsp/") and lp.endswith("integrationGuide.jsp") and is_auth and getattr(schema, "unified_auth", False):
        return f"""<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/><title>{schema.entity} Integrated Login</title></head>
<body>
<%@ include file="/WEB-INF/views/common/header.jsp" %>
<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>
<section class="page-shell login-shell">
  <div class="page-card login-card">
    <div class="page-header">
      <div>
        <h2 class="schedule-page__title">통합인증 연계</h2>
        <p class="schedule-page__desc">통합인증 연계 지점을 프로젝트에 포함한 상태입니다. 운영 환경에서는 외부 인증 서버 연계 URL만 교체하면 됩니다.</p>
      </div>
    </div>
    <div class="empty-state"><a href="<c:url value='/login/integratedCallback.do?loginId=admin&amp;userName=%EA%B4%80%EB%A6%AC%EC%9E%90'/>">통합인증 콜백</a></div>
    <div class="autopj-form-actions">
      <a class="btn" href="<c:url value='/login/login.do'/>">일반 로그인으로 돌아가기</a>
      <c:if test="${{supportCertificateAuth}}">
        <a class="btn btn-secondary" href="<c:url value='/login/certLogin.do'/>">인증서 로그인</a>
      </c:if>
    </div>
  </div>
</section>
</body>
</html>
"""

    if lp.startswith("jsp/") and lp.endswith("certLogin.jsp") and is_auth and getattr(schema, "cert_login", False):
        name_prop = _auth_name_field(schema)
        name_value_attr = f"<c:out value='${{item.{name_prop}}}'/>" if name_prop else ""
        return f"""<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/><title>{schema.entity} Certificate Login</title></head>
<body>
<%@ include file="/WEB-INF/views/common/header.jsp" %>
<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>
<section class="page-shell login-shell">
  <div class="page-card login-card">
    <div class="page-header">
      <div>
        <h2 class="schedule-page__title">인증서 로그인</h2>
        <p class="schedule-page__desc">공동인증서/기관 인증서 연동용 서버 처리 흐름입니다. 실제 인증서 모듈 연결 전에는 subject DN / serial 값을 받아 서버 어댑터만 교체하면 됩니다.</p>
      </div>
    </div>
    <c:if test="${{loginError}}">
      <div class="empty-state"><c:out value="${{loginMessage}}" default="로그인 실패"/></div>
    </c:if>
    <form class="autopj-form-card form-card" action="<c:url value='/login/actionCertLogin.do'/>" method="post">
      <div class="autopj-form-grid">
        <label class="autopj-field"><span class="autopj-field__label">로그인 ID</span><input type="text" name="loginId" class="form-control" value="<c:out value='${{item.loginId}}'/>"/></label>
        <label class="autopj-field"><span class="autopj-field__label">사용자명</span><input type="text" name="userName" class="form-control" value="{name_value_attr}"/></label>
        <label class="autopj-field"><span class="autopj-field__label">인증서 Subject DN</span><input type="text" name="certSubjectDn" class="form-control" value=""/></label>
        <label class="autopj-field"><span class="autopj-field__label">인증서 Serial No</span><input type="text" name="certSerialNo" class="form-control" value=""/></label>
      </div>
      <div class="autopj-form-actions">
        <button type="submit">인증서 로그인</button>
        <a class="btn btn-secondary" href="<c:url value='/login/login.do'/>">일반 로그인</a>
      </div>
    </form>
  </div>
</section>
</body>
</html>
"""

    if lp.startswith("jsp/") and lp.endswith("jwtLogin.jsp") and is_auth and getattr(schema, "jwt_login", False):
        return f"""<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/><title>{schema.entity} JWT Login</title></head>
<body>
<%@ include file="/WEB-INF/views/common/header.jsp" %>
<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>
<section class="page-shell login-shell">
  <div class="page-card login-card">
    <div class="page-header">
      <div>
        <h2 class="schedule-page__title">JWT 로그인</h2>
        <p class="schedule-page__desc">로그인 성공 시 JWT 토큰을 발급해 연계 API 호출에 사용할 수 있습니다.</p>
      </div>
    </div>
    <c:if test="${{loginError}}">
      <div class="empty-state"><c:out value="${{loginMessage}}" default="로그인 실패"/></div>
    </c:if>
    <form class="autopj-form-card form-card" action="<c:url value='/login/actionJwtLogin.do'/>" method="post">
      <div class="autopj-form-grid">
        <label class="autopj-field"><span class="autopj-field__label">로그인 ID</span><input type="text" name="loginId" class="form-control" value="<c:out value='${{item.loginId}}'/>"/></label>
        <label class="autopj-field"><span class="autopj-field__label">비밀번호</span><input type="password" name="password" class="form-control" value="" autocomplete="current-password"/></label>
      </div>
      <div class="autopj-form-actions">
        <button type="submit">JWT 발급 로그인</button>
        <a class="btn btn-secondary" href="<c:url value='/login/login.do'/>">일반 로그인</a>
      </div>
    </form>
    <c:if test="${{not empty jwtToken}}">
      <div class="page-card" style="margin-top:16px;">
        <h3 class="autopj-section-title">발급 토큰</h3>
        <p class="autopj-helper">Authorization 헤더에 Bearer 토큰으로 사용합니다.</p>
        <textarea class="form-control" rows="6" readonly="readonly"><c:out value="${{jwtToken}}"/></textarea>
      </div>
    </c:if>
  </div>
</section>
</body>
</html>
"""

    if lp.startswith("jsp/") and lp.endswith("/main.jsp") and is_auth:
        auth_id, _auth_pw = _auth_fields(schema)
        return f"""<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/><title>{schema.entity} Main</title></head>
<body>
<%@ include file="/WEB-INF/views/common/header.jsp" %>
<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>
<section class="page-shell">
  <div class="page-card login-main-card">
    <p class="autopj-eyebrow">전자정부 로그인 흐름</p>
    <h2>로그인 성공</h2>
    <p class="autopj-helper">세션에 로그인 사용자가 저장된 상태입니다.</p>
    <div class="autopj-form-grid">
      <div class="autopj-field"><span class="autopj-field__label">로그인 ID</span><div class="autopj-field__value"><c:out value="${{loginUser.{auth_id[0]}}}"/></div></div>
    </div>
    <div class="autopj-form-actions">
      <a class="btn" href="<c:url value='{schema.routes['logout']}'/>">로그아웃</a>
    </div>
  </div>
</section>
</body>
</html>
"""

    if lp.startswith("jsp/") and (lp.endswith("Form.jsp") or lp.endswith("/login.jsp") or lp.endswith("Login.jsp")):
        if is_auth:
            auth_id, auth_pw = _auth_fields(schema)
            extra_buttons = []
            if getattr(schema, 'unified_auth', False):
                extra_buttons.append("        <a class=\"btn btn-secondary\" href=\"<c:url value='/login/integrationGuide.do'/>\">통합인증 로그인</a>")
            if getattr(schema, 'cert_login', False):
                extra_buttons.append("        <a class=\"btn btn-secondary\" href=\"<c:url value='/login/certLogin.do'/>\">인증서 로그인</a>")
            if getattr(schema, 'jwt_login', False):
                extra_buttons.append("        <a class=\"btn btn-secondary\" href=\"<c:url value='/login/jwtLogin.do'/>\">JWT 로그인</a>")
            extra_buttons_block = "\n".join(extra_buttons)
            login_desc = "전자정부 스타일의 세션 인증 흐름"
            if getattr(schema, 'unified_auth', False) and getattr(schema, 'cert_login', False) and getattr(schema, 'jwt_login', False):
                login_desc = "전자정부 스타일의 세션 인증 흐름에 통합인증, 인증서 로그인, JWT 로그인을 함께 확장한 구조"
            elif getattr(schema, 'unified_auth', False) and getattr(schema, 'cert_login', False):
                login_desc = "전자정부 스타일의 세션 인증 흐름에 통합인증과 인증서 로그인을 함께 확장한 구조"
            elif getattr(schema, 'unified_auth', False) and getattr(schema, 'jwt_login', False):
                login_desc = "전자정부 스타일의 세션 인증 흐름에 통합인증과 JWT 로그인을 함께 확장한 구조"
            elif getattr(schema, 'unified_auth', False):
                login_desc = "전자정부 스타일의 세션 인증 흐름에 통합인증 연계 포인트를 포함한 구조"
            elif getattr(schema, 'jwt_login', False):
                login_desc = "전자정부 스타일의 세션 인증 흐름에 JWT 로그인 방식을 함께 제공하는 구조"
            return f"""<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/><title>{schema.entity} Login</title></head>
<body>
<%@ include file="/WEB-INF/views/common/header.jsp" %>
<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>
<section class="page-shell login-shell">
  <div class="page-card login-card">
    <div class="page-header">
      <div>
        <h2 class="schedule-page__title">{schema.entity} 로그인</h2>
        <p class="schedule-page__desc">{login_desc}을 사용합니다.</p>
      </div>
    </div>
    <c:if test="${{loginError}}">
      <div class="empty-state"><c:out value="${{loginMessage}}" default="로그인 실패"/></div>
    </c:if>
    <form class="autopj-form-card form-card" action="<c:url value='{schema.routes['process']}'/>" method="post">
      <div class="autopj-form-grid">
        <label class="autopj-field">
          <span class="autopj-field__label">{_label_from_prop(auth_id[0])}</span>
          <input type="text" name="{auth_id[0]}" class="form-control" value="<c:out value='${{item.{auth_id[0]}}}'/>" autocomplete="username"/>
        </label>
        <label class="autopj-field">
          <span class="autopj-field__label">{_label_from_prop(auth_pw[0])}</span>
          <input type="password" name="{auth_pw[0]}" class="form-control" value="" autocomplete="current-password"/>
        </label>
      </div>
      <div class="autopj-form-actions">
        <button type="submit">로그인</button>
{extra_buttons_block}
      </div>
    </form>
  </div>
</section>
</body>
</html>
"""
        hidden_inputs = []
        if _is_auto_generated_id(schema) and not read_only:
            hidden_inputs.append(f"      <input type=\"hidden\" name=\"{schema.id_prop}\" value=\"<c:out value='${{item.{schema.id_prop}}}'/>\"/>")
        elif not read_only and schema.id_prop:
            hidden_inputs.append(f"      <input type=\"hidden\" name=\"_original{schema.id_prop[:1].upper() + schema.id_prop[1:]}\" value=\"<c:out value='${{item.{schema.id_prop}}}'/>\"/>")
        inputs = []
        for field in _editable_fields(schema, allow_sensitive=_schema_supports_account_form_credentials(schema)):
            prop, col, jt = field
            if not read_only and not _is_auto_generated_id(schema) and prop == schema.id_prop:
                label = _label_from_prop(prop)
                hint = _field_hint_from_type(prop, jt) + ' 기존 데이터 수정 시 식별키는 읽기 전용으로 유지됩니다.'
                wrapper_class = 'autopj-field autopj-field--full' if (_is_textarea_field(prop) or _is_datetime_field(prop, col, jt)) else 'autopj-field'
                input_type = _jsp_input_type(prop, jt)
                step_attr = ' step="1"' if input_type == 'datetime-local' else ''
                temporal_attr = f' data-autopj-temporal="{input_type}"' if input_type in ('date', 'datetime-local') else ''
                required_attr = _required_attr(schema, field)
                inputs.append(f"""      <label class="{wrapper_class}">
        <span class="autopj-field__label">{label}</span>
        <input type="{input_type}" name="{prop}" class="form-control" value="<c:out value='${{item.{prop}}}'/>"{required_attr}{step_attr}{temporal_attr}/>
      </label>
      <script>document.addEventListener('DOMContentLoaded', function(){{ var el = document.querySelector('input[name=\"{prop}\"]'); if (!el) return; var v = (el.value || '').trim(); if (v) {{ el.setAttribute('readonly', 'readonly'); el.setAttribute('data-autopj-id-lock', 'true'); }} else {{ el.removeAttribute('readonly'); }} }});</script>""")
                continue
            inputs.append(_jsp_field_markup(schema, field))
        inputs_block = "\n".join(inputs)
        hidden_block = "\n".join(hidden_inputs)
        action = schema.routes.get('form') if read_only else schema.routes.get('save')
        if not action:
            action = schema.routes.get('detail') or schema.routes.get('list') or '/'
        cancel = schema.routes.get('calendar') or (schema.routes['list'] if 'list' in schema.routes else '/')
        delete_route = schema.routes.get('delete') if not read_only else None
        delete_form = ''
        if delete_route:
            delete_form = f'''      <c:if test="${{not empty item and not empty item.{schema.id_prop}}}">
        <button type="submit" formaction="<c:url value='{delete_route}'/>" formmethod="post" onclick="return confirm('삭제하시겠습니까?');">Delete</button>
      </c:if>'''
        submit_label = 'Close' if read_only else 'Save'
        page_title = f"{schema.entity} {'View' if read_only else 'Form'}"
        page_desc = '' if not read_only else ''
        return f"""<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"/><title>{page_title}</title></head>
<body>
<%@ include file="/WEB-INF/views/common/header.jsp" %>
<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>
<section class="page-shell autopj-form-page">
  <div class="autopj-form-hero page-card">
    <div>
      <p class="autopj-eyebrow">{schema.entity}</p>
      <h2 class="autopj-form-title">{page_title}</h2>
      <p class="autopj-form-subtitle">{page_desc}</p>
    </div>
    <div class="autopj-form-hero__meta">
      <span class="badge">입력 검토</span>
      <span class="autopj-helper"></span>
    </div>
  </div>

  <form class="autopj-form-card form-card" action="<c:url value='{action}'/>" method="post" onsubmit="return window.autopjValidateRequired ? window.autopjValidateRequired(this) : true;">
{hidden_block}
    <div class="autopj-form-section-header">
      <div>
        <h3 class="autopj-section-title">기본 정보</h3>
      </div>
    </div>
    <div class="autopj-form-grid">
{inputs_block}
    </div>
    <div class="autopj-form-actions">
      <button type="submit">{submit_label}</button>
{delete_form}
      <a class="btn btn-secondary" href="<c:url value='{cancel}'/>">Cancel</a>
    </div>
  </form>
</section>
</body>
</html>
"""

    if lp == "index.jsp":
        target = schema.routes['login'] if is_auth else (schema.routes.get('calendar') or schema.routes.get('list', '/'))
        return f"""<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%
    response.sendRedirect(request.getContextPath() + "{target}");
    return;
%>
"""

    if lp.startswith("java/controller/") and lp.endswith("CertLoginController.java") and is_auth and getattr(schema, "cert_login", False):
        auth_id, _auth_pw = _auth_fields(schema)
        id_getter = auth_id[0][:1].upper() + auth_id[0][1:]
        return f"""package {pkg_web};

import javax.servlet.http.HttpSession;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import {pkg_svc}.CertLoginService;
import {pkg_vo}.{V};

@Controller
@RequestMapping("/login")
public class CertLoginController {{

    private final CertLoginService certLoginService;

    public CertLoginController(CertLoginService certLoginService) {{
        this.certLoginService = certLoginService;
    }}

    @GetMapping("/certLogin.do")
    public String certLoginForm(HttpSession session, Model model) {{
        if (session != null && session.getAttribute("loginVO") != null) {{
            return "redirect:{schema.routes['main']}";
        }}
        model.addAttribute("item", new {V}());
        return "login/certLogin";
    }}

    @PostMapping("/actionCertLogin.do")
    public String actionCertLogin(String loginId, String userName, String certSubjectDn, String certSerialNo, HttpSession session, Model model) throws Exception {{
        {V} authUser = certLoginService.authenticateCertificate(loginId, userName, certSubjectDn, certSerialNo);
        if (authUser == null) {{
            model.addAttribute("loginError", true);
            model.addAttribute("loginMessage", "인증서 정보를 확인할 수 없습니다.");
            model.addAttribute("item", new {V}());
            return "login/certLogin";
        }}
        session.setAttribute("loginVO", authUser);
        session.setAttribute("loginUser", authUser);
        session.setAttribute("loginId", authUser.get{id_getter}());
        session.setAttribute("accessUser", authUser.get{id_getter}());
        return "redirect:{schema.routes['main']}";
    }}
}}
"""

    if lp.startswith("java/controller/") and lp.endswith("JwtLoginController.java") and is_auth and getattr(schema, "jwt_login", False):
        auth_id, _auth_pw = _auth_fields(schema)
        id_getter = auth_id[0][:1].upper() + auth_id[0][1:]
        return f"""package {pkg_web};

import java.util.LinkedHashMap;
import java.util.Map;
import javax.servlet.http.HttpSession;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseBody;
import {pkg_config}.JwtTokenProvider;
import {pkg_svc}.{S};
import {pkg_vo}.{V};

@Controller
@RequestMapping("/login")
public class JwtLoginController {{

    private final {S} {ev}Service;
    private final JwtTokenProvider jwtTokenProvider;

    public JwtLoginController({S} {ev}Service, JwtTokenProvider jwtTokenProvider) {{
        this.{ev}Service = {ev}Service;
        this.jwtTokenProvider = jwtTokenProvider;
    }}

    @GetMapping("/jwtLogin.do")
    public String jwtLoginForm(HttpSession session, Model model) {{
        if (session != null && session.getAttribute("loginVO") != null) {{
            model.addAttribute("loginUser", session.getAttribute("loginVO"));
        }}
        model.addAttribute("item", new {V}());
        return "login/jwtLogin";
    }}

    @PostMapping("/actionJwtLogin.do")
    public String actionJwtLogin({V} vo, HttpSession session, Model model) throws Exception {{
        {V} authUser = {ev}Service.authenticate(vo);
        if (authUser == null) {{
            model.addAttribute("loginError", true);
            model.addAttribute("loginMessage", "아이디 또는 비밀번호가 올바르지 않습니다.");
            model.addAttribute("item", vo);
            return "login/jwtLogin";
        }}
        String token = jwtTokenProvider.issueToken(String.valueOf(authUser.get{id_getter}()));
        session.setAttribute("loginVO", authUser);
        session.setAttribute("loginUser", authUser);
        session.setAttribute("loginId", authUser.get{id_getter}());
        session.setAttribute("accessUser", authUser.get{id_getter}());
        session.setAttribute("jwtToken", token);
        model.addAttribute("item", authUser);
        model.addAttribute("jwtToken", token);
        model.addAttribute("loginUser", authUser);
        return "login/jwtLogin";
    }}

    @PostMapping("/api/jwtLogin.do")
    @ResponseBody
    public Map<String, Object> apiJwtLogin({V} vo) throws Exception {{
        {V} authUser = {ev}Service.authenticate(vo);
        Map<String, Object> result = new LinkedHashMap<>();
        if (authUser == null) {{
            result.put("authenticated", false);
            result.put("message", "아이디 또는 비밀번호가 올바르지 않습니다.");
            return result;
        }}
        result.put("authenticated", true);
        result.put("loginId", authUser.get{id_getter}());
        result.put("token", jwtTokenProvider.issueToken(String.valueOf(authUser.get{id_getter}())));
        return result;
    }}
}}
"""

    if lp.startswith("java/config/") and lp.endswith("JwtTokenProvider.java") and is_auth and getattr(schema, "jwt_login", False):
        return f"""package {pkg_config};

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Base64;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class JwtTokenProvider {{

    private final String secret;
    private final long expiresInSeconds;

    public JwtTokenProvider(
            @Value("${{autopj.jwt.secret:autopj-default-secret-key-autopj-default-secret-key}}") String secret,
            @Value("${{autopj.jwt.expires-in:3600}}") long expiresInSeconds) {{
        this.secret = secret;
        this.expiresInSeconds = expiresInSeconds;
    }}

    public String issueToken(String subject) {{
        long now = Instant.now().getEpochSecond();
        long exp = now + Math.max(300L, expiresInSeconds);
        String q = Character.toString((char) 34);
        String header = base64Json("{{" + q + "alg" + q + ":" + q + "HS256" + q + "," + q + "typ" + q + ":" + q + "JWT" + q + "}}");
        String payload = base64Json("{{" + q + "sub" + q + ":" + q + escape(subject) + q + "," + q + "iat" + q + ":" + now + "," + q + "exp" + q + ":" + exp + "}}");
        String signature = Base64.getUrlEncoder().withoutPadding().encodeToString((header + "." + payload + "." + secret).getBytes(StandardCharsets.UTF_8));
        return header + "." + payload + "." + signature;
    }}

    private String base64Json(String json) {{
        return Base64.getUrlEncoder().withoutPadding().encodeToString(json.getBytes(StandardCharsets.UTF_8));
    }}

    private String escape(String value) {{
        if (value == null) {{
            return "";
        }}
        String backslash = Character.toString((char) 92);
        String quote = Character.toString((char) 34);
        return value.replace(backslash, backslash + backslash).replace(quote, backslash + quote);
    }}
}}
"""

    if lp.startswith("java/config/") and lp.endswith("AuthLoginInterceptor.java") and is_auth:
        return f"""package {pkg_config};

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import javax.servlet.http.HttpSession;
import org.springframework.web.servlet.HandlerInterceptor;

public class AuthLoginInterceptor implements HandlerInterceptor {{

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {{
        String uri = request.getRequestURI();
        String contextPath = request.getContextPath();
        String path = uri.startsWith(contextPath) ? uri.substring(contextPath.length()) : uri;
        if (path.equals("/login.do")
                || path.startsWith("/login/login.do")
                || path.startsWith("/login/actionLogin.do")
                || path.startsWith("/login/process.do")
                || path.startsWith("/login/actionLogout.do")
                || path.startsWith("/login/logout.do")
                || path.startsWith("/login/integrationGuide.do")
                || path.startsWith("/login/integratedLogin.do")
                || path.startsWith("/login/ssoLogin.do")
                || path.startsWith("/login/integratedCallback.do")
                || path.startsWith("/login/certLogin.do")
                || path.startsWith("/login/actionCertLogin.do")
                || path.startsWith("/login/jwtLogin.do")
                || path.startsWith("/login/actionJwtLogin.do")
                || path.startsWith("/login/api/jwtLogin.do")
                || path.startsWith("/css/")
                || path.startsWith("/js/")
                || path.startsWith("/images/")
                || path.startsWith("/webjars/")
                || path.equals("/favicon.ico")) {{
            return true;
        }}
        HttpSession session = request.getSession(false);
        if (session != null && (session.getAttribute("loginVO") != null || session.getAttribute("loginUser") != null)) {{
            return true;
        }}
        response.sendRedirect(contextPath + "{schema.routes['login']}");
        return false;
    }}
}}
"""

    if lp.startswith("java/config/") and lp.endswith("WebMvcConfig.java") and is_auth:
        return f"""package {pkg_config};

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebMvcConfig implements WebMvcConfigurer {{

    @Override
    public void addInterceptors(InterceptorRegistry registry) {{
        registry.addInterceptor(new AuthLoginInterceptor())
                .addPathPatterns("/**/*.do")
                .excludePathPatterns(
                        "/login.do",
                        "/login/login.do",
                        "/login/actionLogin.do",
                        "/login/logout.do",
                        "/login/actionLogout.do",
                        "/login/integrationGuide.do",
                        "/login/integratedCallback.do",
                        "/login/certLogin.do",
                        "/login/actionCertLogin.do",
                        "/login/jwtLogin.do",
                        "/login/actionJwtLogin.do",
                        "/login/api/jwtLogin.do"
                );
    }}
}}
"""

    if lp.startswith("java/config/") and lp.endswith("MyBatisConfig.java"):
        return f"""package {base_package}.config;

import javax.sql.DataSource;

import org.apache.ibatis.session.SqlSessionFactory;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.mybatis.spring.annotation.MapperScan;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;

@Configuration
@MapperScan(basePackages = "{base_package}", annotationClass = org.apache.ibatis.annotations.Mapper.class, sqlSessionFactoryRef = "sqlSessionFactory")
public class MyBatisConfig {{

    @Bean
    public SqlSessionFactory sqlSessionFactory(DataSource dataSource, ApplicationContext applicationContext) throws Exception {{
        SqlSessionFactoryBean factoryBean = new SqlSessionFactoryBean();
        factoryBean.setDataSource(dataSource);

        Resource[] mapperResources = applicationContext.getResources("classpath*:egovframework/mapper/**/*.xml");
        factoryBean.setMapperLocations(mapperResources);
        factoryBean.setTypeAliasesPackage("{base_package}");

        org.apache.ibatis.session.Configuration configuration = new org.apache.ibatis.session.Configuration();
        configuration.setMapUnderscoreToCamelCase(true);
        factoryBean.setConfiguration(configuration);

        return factoryBean.getObject();
    }}

    @Bean
    public SqlSessionTemplate sqlSessionTemplate(SqlSessionFactory sqlSessionFactory) {{
        return new SqlSessionTemplate(sqlSessionFactory);
    }}
}}
"""
    return None
