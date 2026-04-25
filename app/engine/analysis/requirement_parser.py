from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Set

from .naming_rules import normalize_token


AUTH_KEYWORDS = {
    "login", "logout", "signin", "sign in", "authenticate", "auth", "로그인", "로그아웃", "인증", "세션", "토큰",
    "통합인증", "sso", "single sign-on", "single sign on", "certificate login", "cert login", "공동인증서", "인증서로그인", "인증서 로그인",
}
UPLOAD_KEYWORDS = {"upload", "attachment", "업로드", "첨부", "multipart", "첨부파일", "파일업로드"}
SEARCH_KEYWORDS = {"search", "query", "검색", "조회"}
POPUP_KEYWORDS = {"popup", "dialog", "modal", "팝업", "모달"}
EXCEL_KEYWORDS = {"excel", "xlsx", "export", "엑셀"}
DASHBOARD_KEYWORDS = {"dashboard", "chart", "summary", "대시보드", "통계"}
REPORT_KEYWORDS = {"report", "print", "출력", "보고서", "인쇄"}
READONLY_KEYWORDS = {"read only", "readonly", "조회전용", "읽기전용", "read-only"}
APPROVAL_KEYWORDS = {"approval", "approve", "reject", "결재", "승인", "반려"}
WORKFLOW_KEYWORDS = {"workflow", "state machine", "process", "프로세스", "워크플로우"}
MASTER_DETAIL_KEYWORDS = {"master-detail", "master detail", "상세-목록", "마스터", "디테일"}
CODE_KEYWORDS = {"code", "common code", "공통코드", "코드관리"}
CALENDAR_KEYWORDS = {"calendar", "calendar view", "monthly calendar", "month view", "캘린더", "달력", "월간 캘린더", "캘린더 화면", "달력 화면"}
UPLOAD_CONTEXT_RE = re.compile(
    r"(?:파일\s*업로드|업로드\s*파일|첨부\s*파일|file\s*upload|upload\s*file|multipart)",
    re.IGNORECASE,
)
ARTIFACT_FILE_CONTEXT_RE = re.compile(
    r"(?:jsp|mapper\.xml|xml|vo|service|controller|api|route|view|화면|파일)\s*파일",
    re.IGNORECASE,
)
ENTRY_DOMAIN_STOPWORDS = {"index", "home", "main", "landing", "root", "entry"}


@dataclass
class RequirementHints:
    domain_candidates: List[str] = field(default_factory=list)
    actions: Set[str] = field(default_factory=set)
    keywords: Set[str] = field(default_factory=set)
    auth_intent: bool = False
    upload_intent: bool = False
    search_intent: bool = False
    popup_intent: bool = False
    excel_intent: bool = False
    dashboard_intent: bool = False
    report_intent: bool = False
    readonly_intent: bool = False
    approval_intent: bool = False
    workflow_intent: bool = False
    master_detail_intent: bool = False
    code_intent: bool = False
    calendar_intent: bool = False


class RequirementParser:
    DOMAIN_HINT_PATTERN = re.compile(r"([A-Za-z_][A-Za-z0-9_]+)\s*(관리|목록|상세|등록|수정|삭제|화면|crud|CRUD)?")

    KOREAN_DOMAIN_HINTS = [
        "회원", "게시판", "공지", "로그인", "사용자", "코드", "상품", "주문", "권한", "일정", "달력", "통계", "대시보드",
        "예약", "회의실", "객실", "자원", "리소스", "설비",
    ]

    DOMAIN_TRANSLATION: Dict[str, str] = {
        "회원": "member", "사용자": "user", "게시판": "board", "공지": "notice", "로그인": "login",
        "코드": "code", "상품": "product", "주문": "order", "권한": "role", "일정": "schedule",
        "달력": "schedule", "통계": "statistics", "대시보드": "dashboard",
        "예약": "reservation", "회의실": "room", "객실": "room", "자원": "resource", "리소스": "resource", "설비": "resource",
    }

    def parse(self, requirements_text: str) -> RequirementHints:
        text = (requirements_text or "").strip()
        lowered = text.lower()

        hints = RequirementHints()

        hints.actions |= self._collect_actions(lowered)
        hints.keywords |= set(hints.actions)

        hints.auth_intent = self._contains_any(text, AUTH_KEYWORDS)
        hints.upload_intent = self._detect_upload_intent(text)
        hints.search_intent = self._contains_any(text, SEARCH_KEYWORDS)
        hints.popup_intent = self._contains_any(text, POPUP_KEYWORDS)
        hints.excel_intent = self._contains_any(text, EXCEL_KEYWORDS)
        hints.dashboard_intent = self._contains_any(text, DASHBOARD_KEYWORDS)
        hints.report_intent = self._contains_any(text, REPORT_KEYWORDS)
        hints.readonly_intent = self._contains_any(text, READONLY_KEYWORDS)
        hints.approval_intent = self._contains_any(text, APPROVAL_KEYWORDS)
        hints.workflow_intent = self._contains_any(text, WORKFLOW_KEYWORDS)
        hints.master_detail_intent = self._contains_any(text, MASTER_DETAIL_KEYWORDS)
        hints.code_intent = self._contains_any(text, CODE_KEYWORDS)
        hints.calendar_intent = self._contains_any(text, CALENDAR_KEYWORDS)

        hints.domain_candidates.extend(self._extract_domains(text))
        return hints

    def _collect_actions(self, text: str) -> Set[str]:
        found = set()
        if self._contains_any(text, {"list", "목록", "조회"}):
            found.add("list")
        if self._contains_any(text, {"detail", "상세"}):
            found.add("detail")
        if self._contains_any(text, {"form", "입력", "등록폼", "수정폼"}):
            found.add("form")
        if self._contains_any(text, {"create", "register", "등록", "save", "저장"}):
            found.add("create")
        if self._contains_any(text, {"update", "edit", "수정"}):
            found.add("update")
        if self._contains_any(text, {"delete", "remove", "삭제"}):
            found.add("delete")
        if self._contains_any(text, {"login", "로그인"}):
            found.add("login")
        if self._contains_any(text, {"logout", "로그아웃"}):
            found.add("logout")
        return found

    def _extract_domains(self, text: str) -> List[str]:
        candidates: List[str] = []

        for ko in self.KOREAN_DOMAIN_HINTS:
            if ko in text:
                candidates.append(self.DOMAIN_TRANSLATION.get(ko, normalize_token(ko)))

        for match in self.DOMAIN_HINT_PATTERN.findall(text):
            token = normalize_token(match[0])
            if token and token not in {"crud", "api", "rest", "page", "screen"} and token not in ENTRY_DOMAIN_STOPWORDS:
                candidates.append(token)

        deduped = []
        seen = set()
        for candidate in candidates:
            if candidate in ENTRY_DOMAIN_STOPWORDS:
                continue
            if candidate and candidate not in seen:
                seen.add(candidate)
                deduped.append(candidate)
        return deduped

    def _detect_upload_intent(self, text: str) -> bool:
        lowered = (text or "").lower()
        if self._contains_any(text, UPLOAD_KEYWORDS):
            return True

        if UPLOAD_CONTEXT_RE.search(lowered):
            return True

        if ARTIFACT_FILE_CONTEXT_RE.search(lowered):
            return False

        return False

    @staticmethod
    def _contains_any(text: str, terms: set[str]) -> bool:
        lowered = text.lower()
        return any(term.lower() in lowered for term in terms)
