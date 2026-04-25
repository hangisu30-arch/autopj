from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Tuple
import re

FEATURE_KIND_AUTH = "AUTH"
FEATURE_KIND_CRUD = "CRUD"
FEATURE_KIND_READONLY = "READONLY"
FEATURE_KIND_SEARCH = "SEARCH"
FEATURE_KIND_DASHBOARD = "DASHBOARD"
FEATURE_KIND_FILE = "FILE"
FEATURE_KIND_BATCH = "BATCH"
FEATURE_KIND_APPROVAL = "APPROVAL"
FEATURE_KIND_CODE = "CODE"
FEATURE_KIND_TREE = "TREE"
FEATURE_KIND_MASTER_DETAIL = "MASTER_DETAIL"
FEATURE_KIND_EXTERNAL_API = "EXTERNAL_API"
FEATURE_KIND_REPORT = "REPORT"
FEATURE_KIND_ADMIN = "ADMIN"
FEATURE_KIND_MYPAGE = "MYPAGE"
FEATURE_KIND_WORKFLOW = "WORKFLOW"
FEATURE_KIND_SCHEDULE = "SCHEDULE"
FEATURE_KIND_NOTIFICATION = "NOTIFICATION"
FEATURE_KIND_SYSTEM = "SYSTEM"
FEATURE_KIND_UNKNOWN = "UNKNOWN"

AUTH_KINDS = {FEATURE_KIND_AUTH}
CRUD_LIKE_KINDS = {
    FEATURE_KIND_CRUD,
    FEATURE_KIND_CODE,
    FEATURE_KIND_TREE,
    FEATURE_KIND_MASTER_DETAIL,
    FEATURE_KIND_ADMIN,
    FEATURE_KIND_MYPAGE,
}
READ_ONLY_KINDS = {
    FEATURE_KIND_READONLY,
    FEATURE_KIND_SEARCH,
    FEATURE_KIND_DASHBOARD,
    FEATURE_KIND_REPORT,
}
ACTION_KINDS = {
    FEATURE_KIND_BATCH,
    FEATURE_KIND_APPROVAL,
    FEATURE_KIND_WORKFLOW,
    FEATURE_KIND_NOTIFICATION,
    FEATURE_KIND_SYSTEM,
    FEATURE_KIND_EXTERNAL_API,
    FEATURE_KIND_FILE,
}

_GENERIC_ENTITY_WORDS = {
    "app", "ui", "view", "screen", "page", "home", "main", "item", "entity", "data", "model",
    "controller", "service", "mapper", "vo", "impl", "config", "module", "feature", "crud", "list",
    "detail", "form", "save", "delete", "update", "insert", "select", "search", "manage", "manager",
    "sample", "example", "default", "common", "test", "create", "define", "implement", "build", "make",
    "write", "generate", "project", "spring", "boot", "mybatis", "java", "jsp", "react", "vue", "nexacro",
}

FEATURE_PATTERNS: List[Tuple[str, Sequence[str]]] = [
    (FEATURE_KIND_AUTH, (
        "login", "logout", "signin", "sign in", "signup", "sign up", "auth", "authentication", "authorize",
        "credential", "session", "password", "비밀번호", "로그인", "로그아웃", "인증", "세션", "통합인증", "sso", "single sign-on", "single sign on", "certificate login", "cert login", "공동인증서", "인증서로그인", "인증서 로그인", "jwt", "jwt login", "token login", "bearer token", "토큰 로그인", "jwt 로그인",
    )),
    (FEATURE_KIND_APPROVAL, (
        "approve", "approval", "reject", "결재", "결재선", "승인", "반려",
    )),
    (FEATURE_KIND_WORKFLOW, (
        "workflow", "state transition", "status change", "단계", "상태전이", "프로세스",
    )),
    (FEATURE_KIND_BATCH, (
        "batch", "scheduler", "cron", "job", "배치", "스케줄러", "정산",
    )),
    (FEATURE_KIND_DASHBOARD, (
        "dashboard", "chart", "summary", "aggregate", "stat", "통계", "대시보드", "집계",
    )),
    (FEATURE_KIND_FILE, (
        "upload", "download", "attachment", "file", "excel import", "첨부", "업로드", "다운로드", "파일",
    )),
    (FEATURE_KIND_EXTERNAL_API, (
        "api", "rest", "external", "integration", "webhook", "연동", "외부", "호출",
    )),
    (FEATURE_KIND_REPORT, (
        "report", "pdf", "excel", "print", "보고서", "출력", "인쇄",
    )),
    (FEATURE_KIND_TREE, (
        "tree", "hierarchy", "folder", "category tree", "트리", "계층", "폴더",
    )),
    (FEATURE_KIND_MASTER_DETAIL, (
        "master-detail", "master detail", "header-detail", "상세행", "마스터", "헤더-상세",
    )),
    (FEATURE_KIND_CODE, (
        "code management", "common code", "lookup code", "공통코드", "코드관리",
    )),
    (FEATURE_KIND_SCHEDULE, (
        "calendar", "schedule", "reservation", "일정", "캘린더", "예약",
    )),
    (FEATURE_KIND_NOTIFICATION, (
        "notification", "alarm", "mail", "email", "sms", "push", "알림", "메일", "문자",
    )),
    (FEATURE_KIND_MYPAGE, (
        "mypage", "profile", "account", "내정보", "마이페이지", "프로필",
    )),
    (FEATURE_KIND_ADMIN, (
        "admin", "administrator", "setting", "설정", "관리자", "운영",
    )),
    (FEATURE_KIND_SEARCH, (
        "search", "filter", "keyword", "lookup", "검색", "필터", "조회조건",
    )),
    (FEATURE_KIND_READONLY, (
        "readonly", "read only", "view only", "inquiry", "read-only", "조회전용", "상세조회", "열람",
    )),
    (FEATURE_KIND_SYSTEM, (
        "system", "environment", "config", "환경설정", "시스템", "설정",
    )),
]

LOGIN_FIELD_CANDIDATES = (
    "loginid", "login_id", "userid", "user_id", "username", "user_name", "email", "memberid", "member_id", "id",
)
_EXPLICIT_CALENDAR_TERMS = ('calendar', 'calendar view', 'monthly calendar', 'month view', '캘린더', '달력', '월간 캘린더', '캘린더 화면', '달력 화면')
_CALENDAR_NEGATION_TERMS = ('캘린더는 요청하지 않았', '캘린더는 필요 없', '달력은 요청하지 않았', '달력은 필요 없', 'calendar is not required', 'no calendar', 'without calendar', 'calendar not requested')

PASSWORD_FIELD_CANDIDATES = (
    "password", "passwd", "pwd", "userpw", "user_pw", "pw", "passcode", "비밀번호",
    "loginpassword", "login_password", "loginpwd", "login_pwd", "loginpw", "login_pw",
    "loginpasswd", "login_passwd", "loginpasscode", "login_passcode",
)


def iter_text_blobs(source: Any) -> Iterable[str]:
    if isinstance(source, dict):
        for key in ("purpose", "content", "path", "sql", "ddl", "description", "name"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                yield value
        for key in ("tasks", "db_ops"):
            value = source.get(key)
            if isinstance(value, list):
                for item in value:
                    yield from iter_text_blobs(item)
    elif isinstance(source, list):
        for item in source:
            yield from iter_text_blobs(item)
    elif isinstance(source, str):
        if source.strip():
            yield source


def _normalize_token(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _iter_semantic_requirement_blobs(source: Any) -> Iterable[str]:
    if isinstance(source, dict):
        preferred_keys = (
            'extra_requirements', 'requirements', 'requirements_text', 'prompt', 'user_prompt', 'instruction', 'instructions',
            'content', 'purpose', 'description', 'summary', 'text', 'message', 'name',
        )
        yielded: set[tuple[str, str]] = set()
        for key in preferred_keys:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                yielded.add((key, value))
                yield value
        for key, value in source.items():
            key_low = str(key or '').strip().lower()
            if key_low in {'path', 'target_path', 'file_path', 'filename', 'view_name', 'route', 'url', 'jsp', 'mainjsp'}:
                continue
            if isinstance(value, str):
                if value.strip() and (key, value) not in yielded and '/' not in value.replace('\\', '/'):
                    yield value
                continue
            yield from _iter_semantic_requirement_blobs(value)
    elif isinstance(source, list):
        for item in source:
            yield from _iter_semantic_requirement_blobs(item)
    elif isinstance(source, str):
        if source.strip() and '/' not in source.replace('\\', '/'):
            yield source


def has_explicit_calendar_request(source: Any) -> bool:
    lowered = "\n".join(_iter_semantic_requirement_blobs(source)).lower()
    if not lowered.strip():
        return False
    if any(term in lowered for term in _CALENDAR_NEGATION_TERMS):
        return False
    return any(term in lowered for term in _EXPLICIT_CALENDAR_TERMS)


def classify_feature_kind(source: Any, entity: str = "") -> str:
    text_blobs = [t for t in iter_text_blobs(source)]
    if entity:
        text_blobs.append(entity)
    joined = "\n".join(text_blobs).lower()
    if not joined.strip():
        return FEATURE_KIND_CRUD

    explicit_calendar = has_explicit_calendar_request(source)
    scores: Dict[str, int] = {FEATURE_KIND_CRUD: 1}
    for kind, patterns in FEATURE_PATTERNS:
        if kind == FEATURE_KIND_SCHEDULE and not explicit_calendar:
            continue
        score = 0
        for pattern in patterns:
            pattern_low = pattern.lower()
            if pattern_low in joined:
                score += 3 if " " in pattern_low else 2
        if score:
            scores[kind] = scores.get(kind, 0) + score

    if FEATURE_KIND_AUTH in scores:
        # login/auth should outrank generic CRUD/list/detail language from existing templates
        scores[FEATURE_KIND_AUTH] += 5

    # existing CRUD artifacts may contain list/detail/form/save/delete in paths or purposes.
    # Don't let those words alone overpower domain-specific types.
    generic_crud_hits = len(re.findall(r"\b(list|detail|form|save|delete|update|insert)\b", joined))
    if generic_crud_hits >= 2:
        scores[FEATURE_KIND_CRUD] = scores.get(FEATURE_KIND_CRUD, 1) + 1

    best_kind = max(scores.items(), key=lambda kv: (kv[1], kv[0] == FEATURE_KIND_AUTH, kv[0] == FEATURE_KIND_CRUD))[0]

    # If content is clearly read-only, do not fall back to CRUD.
    if best_kind == FEATURE_KIND_CRUD:
        if re.search(r"\b(readonly|read only|view only|조회전용|열람)\b", joined):
            return FEATURE_KIND_READONLY
    return best_kind


def is_auth_kind(kind: str) -> bool:
    return (kind or "").upper() in AUTH_KINDS


def is_read_only_kind(kind: str) -> bool:
    return (kind or "").upper() in READ_ONLY_KINDS


def is_crud_like_kind(kind: str) -> bool:
    kind_up = (kind or "").upper()
    return kind_up in CRUD_LIKE_KINDS or kind_up == FEATURE_KIND_CRUD


def semantic_entity_var(entity: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", entity or "").strip()
    if not cleaned:
        return "item"
    if cleaned.isupper():
        return cleaned.lower()
    m = re.match(r"^([A-Z]{2,})([A-Z][a-z].*)$", cleaned)
    if m:
        return m.group(1).lower() + m.group(2)
    return cleaned[:1].lower() + cleaned[1:]


def looks_generic_entity(entity: str) -> bool:
    return _normalize_token(entity) in _GENERIC_ENTITY_WORDS


def choose_auth_fields(fields: Sequence[Tuple[str, str, str]], fallback_id_prop: str = "id", fallback_id_col: str = "id") -> Tuple[Tuple[str, str, str], Tuple[str, str, str], List[Tuple[str, str, str]]]:
    normalized = list(fields or [])
    id_field = None
    pw_field = None
    for prop, col, jt in normalized:
        key_prop = _normalize_token(prop)
        key_col = _normalize_token(col)
        if id_field is None and (key_prop in LOGIN_FIELD_CANDIDATES or key_col in LOGIN_FIELD_CANDIDATES):
            id_field = (prop, col, jt)
        if pw_field is None and (key_prop in PASSWORD_FIELD_CANDIDATES or key_col in PASSWORD_FIELD_CANDIDATES):
            pw_field = (prop, col, jt)
    if id_field is None:
        for prop, col, jt in normalized:
            if prop == fallback_id_prop or col == fallback_id_col:
                id_field = (prop, col, jt)
                break
    out = list(normalized)
    if id_field is None:
        id_field = ("loginId", "login_id", "String")
        out.append(id_field)
    if pw_field is None:
        pw_field = ("password", "password", "String")
        out.append(pw_field)
    return id_field, pw_field, out


def primary_display_field(fields: Sequence[Tuple[str, str, str]], excluded_props: Sequence[str] = ()) -> Tuple[str, str, str] | None:
    excluded = {p.lower() for p in excluded_props}
    for prop, col, jt in fields or []:
        low = prop.lower()
        if low in excluded:
            continue
        if any(tok in low for tok in ("name", "title", "label", "nm")):
            return prop, col, jt
    for prop, col, jt in fields or []:
        if prop.lower() not in excluded:
            return prop, col, jt
    return None


def is_schedule_kind(kind: str) -> bool:
    return (kind or "").upper() == FEATURE_KIND_SCHEDULE
