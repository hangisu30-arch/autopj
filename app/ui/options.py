# path: app/ui/options.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Option:
    key: str
    label: str


BACKENDS: List[Option] = [
    Option("egov_spring", "전자정부프레임워크 (Spring Boot)"),
]

FRONTENDS: List[Option] = [
    Option("jsp", "jsp"),
    Option("react", "react"),
    Option("vue", "vue"),
    Option("nexacro", "넥사크로"),
]

CODE_ENGINES: List[Option] = [
    Option("ollama", "Ollama"),
    Option("opencode", "Opencode AI (준비중)"),
]

DESIGN_STYLES: List[Option] = [
    Option("simple", "심플"),
    Option("modern", "모던"),
    Option("contemporary", "현대"),
    Option("portal", "포털형"),
    Option("enterprise_portal", "업무포털 고급형"),
    Option("rich_cards", "풍부한 카드형"),
    Option("dashboard", "대시보드형"),
    Option("soft_dark", "다크 포인트"),
]

DATABASES: List[Option] = [
    Option("sqlite", "SQLite"),
    Option("oracle", "Oracle"),
    Option("mysql", "MySQL"),
    Option("postgresql", "PostgreSQL"),
]
