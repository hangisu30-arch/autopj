from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .analysis_result import FieldInfo
from .naming_rules import choose_domain_name, normalize_token, singularize, to_camel_case


def _ensure_tb_table_name(name: str) -> str:
    token = normalize_token(name)
    if not token:
        return 'tb_item'
    if token in {'tb', 'tb_'}:
        return 'tb_item'
    if token.startswith('tb_'):
        return token
    return f'tb_{token}'


@dataclass
class TableSchema:
    table_name: str
    fields: List[FieldInfo] = field(default_factory=list)

    @property
    def primary_key(self) -> Optional[FieldInfo]:
        for field in self.fields:
            if field.pk:
                return field
        return None


class SchemaParser:
    BUSINESS_DOMAIN_TEMPLATES = {
        "member": [("member_id", "bigint"), ("member_name", "varchar(100)"), ("email", "varchar(200)")],
        "user": [("user_id", "bigint"), ("user_name", "varchar(100)"), ("email", "varchar(200)")],
        "board": [("board_id", "bigint"), ("title", "varchar(200)"), ("content", "text"), ("writer_id", "varchar(100)"), ("reg_dt", "datetime")],
        "notice": [("notice_id", "bigint"), ("title", "varchar(200)"), ("content", "text"), ("writer_id", "varchar(100)"), ("reg_dt", "datetime")],
        "schedule": [("schedule_id", "bigint"), ("title", "varchar(200)"), ("content", "text"), ("start_datetime", "datetime"), ("end_datetime", "datetime"), ("all_day_yn", "varchar(1)"), ("status_cd", "varchar(30)"), ("priority_cd", "varchar(30)"), ("location", "varchar(200)"), ("writer_id", "varchar(100)"), ("use_yn", "varchar(1)"), ("reg_dt", "datetime"), ("upd_dt", "datetime")],
        "room": [("room_id", "bigint"), ("name", "varchar(100)")],
        "resource": [("resource_id", "bigint"), ("name", "varchar(100)")],
        "reservation": [("reservation_id", "bigint"), ("room_id", "bigint"), ("start_date", "date"), ("end_date", "date")],
        "booking": [("booking_id", "bigint"), ("resource_id", "bigint"), ("start_date", "date"), ("end_date", "date")],
        "auth": [("user_id", "varchar(100)"), ("password", "varchar(200)")],
        "login": [("user_id", "varchar(100)"), ("password", "varchar(200)")],
    }
    CONTEXTUAL_DOMAIN_TEMPLATES = {
        frozenset({"room", "reservation"}): {
            "room": [
                ("room_id", "bigint"),
                ("room_name", "varchar(100)"),
                ("location", "varchar(200)"),
                ("capacity", "int"),
                ("use_yn", "varchar(1)"),
                ("reg_dt", "datetime"),
                ("upd_dt", "datetime"),
            ],
            "reservation": [
                ("reservation_id", "bigint"),
                ("room_id", "bigint"),
                ("reserver_name", "varchar(100)"),
                ("purpose", "varchar(200)"),
                ("start_datetime", "datetime"),
                ("end_datetime", "datetime"),
                ("status_cd", "varchar(30)"),
                ("remark", "varchar(500)"),
                ("reg_dt", "datetime"),
                ("upd_dt", "datetime"),
            ],
        },
    }

    CREATE_TABLE_RE = re.compile(
        r'create\s+table\s+(?:if\s+not\s+exists\s+)?[`"]?([a-zA-Z_][a-zA-Z0-9_]*)[`"]?\s*\((.*?)\);',
        re.IGNORECASE | re.DOTALL,
    )

    COLUMN_RE = re.compile(
        r'^\s*[`"]?([a-zA-Z_][a-zA-Z0-9_]*)[`"]?\s+([a-zA-Z0-9\(\),]+)(.*)$',
        re.IGNORECASE,
    )

    EXPLICIT_COLUMNS_RE = re.compile(
        r"(?:엔티티\s*)?(?:컬럼정의|필드정의|컬럼|필드|항목)(?:\s*은|\s*는|\s*:)?\s*([a-zA-Z0-9_,\s]+?)(?:이다|입니다|임|\.|$)",
        re.IGNORECASE,
    )
    EXPLICIT_TABLE_NAME_RE = re.compile(
        r"(?:table\s*name|table|테이블명|테이블)\s*(?:은|는|:|=)?\s*([A-Za-z_][A-Za-z0-9_]*)",
        re.IGNORECASE,
    )
    EXPLICIT_PK_RE = re.compile(
        r"([a-zA-Z0-9_]+)\s*(?:는|은)?\s*기본키",
        re.IGNORECASE,
    )
    EXPLICIT_PK_ALT_RE = re.compile(
        r"기본키(?:\s*는|\s*은|\s*:)?\s*([a-zA-Z0-9_]+)",
        re.IGNORECASE,
    )

    def _extract_explicit_column_comments(self, text: str) -> dict[str, str]:
        comments: dict[str, str] = {}
        lines = [line.rstrip() for line in (text or '').splitlines()]
        collecting = False
        for raw in lines:
            line = raw.strip()
            if not line:
                collecting = False
                continue
            if re.search(r"(?:최소\s*)?(?:컬럼정의|필드정의|컬럼|필드|항목).*(?:아래|다음|사용|포함)", line, re.IGNORECASE) or re.search(r"^(?:[-*•]\s*)?(?:fields?|columns?|column\s*definitions?|컬럼정의|필드정의|컬럼\s*명?|필드|항목)(?:\s*(?:목록|리스트))?\s*[:：]?$", line, re.IGNORECASE):
                collecting = True
                continue
            bullet = re.match(r"^(?:[-*•]|\d+[\.)])\s*[`\'\"]?([A-Za-z_][A-Za-z0-9_]*)[`\'\"]?\s*(.*)$", line)
            if not bullet:
                if collecting:
                    collecting = False
                continue
            if not collecting:
                continue
            token = bullet.group(1)
            tail = (bullet.group(2) or '').strip()
            if not tail:
                continue
            comment = ''
            paren = re.search(r"[\(（]\s*([^\)）]+?)\s*[\)）]", tail)
            if paren:
                comment = paren.group(1).strip()
            elif ':' in tail:
                comment = tail.split(':', 1)[1].strip()
            elif '|' in tail:
                comment = tail.split('|', 1)[1].strip()
            if comment:
                comments[normalize_token(token)] = comment
        return comments

    def parse(self, schema_text: str) -> List[TableSchema]:
        text = (schema_text or "").strip()
        if not text:
            return []

        tables = self._parse_create_table(text)
        if tables:
            return tables

        fields = self._parse_simple_columns(text)
        if fields:
            return [TableSchema(table_name=_ensure_tb_table_name('default_table'), fields=fields)]

        return []

    def infer_from_requirements(self, requirements_text: str, domain_candidates: List[str], auth_intent: bool = False) -> List[TableSchema]:
        text = (requirements_text or '').strip()
        if not text:
            return []

        resolved_candidates = [normalize_token(x) for x in (domain_candidates or []) if normalize_token(x)]
        domain_name = choose_domain_name(domain_candidates or ['domain'])
        if 'reservation' in resolved_candidates and 'room' in resolved_candidates and normalize_token(domain_name) == 'room':
            domain_name = 'reservation'
        if 'booking' in resolved_candidates and 'resource' in resolved_candidates and normalize_token(domain_name) == 'resource':
            domain_name = 'booking'
        explicit_table_name = self._extract_explicit_table_name(text) or normalize_token(domain_name)
        explicit_columns = self._extract_explicit_columns(text)
        explicit_pk_columns = self._extract_explicit_pk_columns(text)
        explicit_comments = self._extract_explicit_column_comments(text)

        if explicit_columns:
            fields = [
                self._build_field(
                    col,
                    pk=(col.lower() in explicit_pk_columns),
                    source='requirements_explicit',
                    comment=explicit_comments.get(col.lower(), ''),
                )
                for col in explicit_columns
            ]
            self._ensure_single_pk(fields, explicit_table_name or domain_name)
            return [TableSchema(table_name=_ensure_tb_table_name(explicit_table_name or domain_name), fields=fields)]

        primary_table_name = explicit_table_name or domain_name
        fields = self._heuristic_fields_for_domain(domain_name, auth_intent=auth_intent)
        if fields:
            return [TableSchema(table_name=_ensure_tb_table_name(primary_table_name), fields=fields)]
        return []

    def _parse_create_table(self, text: str) -> List[TableSchema]:
        tables: List[TableSchema] = []

        for table_name, body in self.CREATE_TABLE_RE.findall(text):
            if not self._is_valid_identifier(table_name):
                continue
            fields: List[FieldInfo] = []
            lines = [line.strip().rstrip(",") for line in body.splitlines() if line.strip()]
            pk_columns = self._extract_pk_columns(lines)

            for line in lines:
                lowered = line.lower()
                if lowered.startswith("primary key") or lowered.startswith("constraint"):
                    continue

                match = self.COLUMN_RE.match(line)
                if not match:
                    continue

                col_name = match.group(1)
                db_type = match.group(2)
                tail = match.group(3) or ""
                if not self._should_accept_column_name(col_name, line):
                    continue

                fields.append(
                    FieldInfo(
                        name=to_camel_case(col_name),
                        column=col_name,
                        java_type=self._map_java_type(db_type),
                        db_type=db_type,
                        pk=(col_name.lower() in pk_columns or self._looks_like_pk(col_name)),
                        nullable=("not null" not in tail.lower()),
                        searchable=self._looks_searchable(col_name),
                        display=self._looks_display_field(col_name),
                    )
                )

            if fields:
                tables.append(TableSchema(table_name=_ensure_tb_table_name(table_name), fields=fields))

        return tables

    def _parse_simple_columns(self, text: str) -> List[FieldInfo]:
        fields: List[FieldInfo] = []
        for raw in text.splitlines():
            line = raw.strip().rstrip(",")
            if not line or self._looks_like_css_noise(line):
                continue

            if ":" in line:
                col, db_type = [part.strip() for part in line.split(":", 1)]
            else:
                parts = line.split()
                col = parts[0]
                db_type = parts[1] if len(parts) > 1 else "varchar"

            if not self._should_accept_column_name(col, line):
                continue

            fields.append(
                FieldInfo(
                    name=to_camel_case(col),
                    column=col,
                    java_type=self._map_java_type(db_type),
                    db_type=db_type,
                    pk=self._looks_like_pk(col),
                    nullable=True,
                    searchable=self._looks_searchable(col),
                    display=self._looks_display_field(col),
                )
            )
        return fields

    def _extract_pk_columns(self, lines: List[str]) -> set[str]:
        pk_columns: set[str] = set()
        for line in lines:
            match = re.search(r"primary\s+key\s*\((.*?)\)", line, re.IGNORECASE)
            if not match:
                continue
            cols = [c.strip().strip("`\"") for c in match.group(1).split(",")]
            pk_columns |= {c.lower() for c in cols if c}
        return pk_columns

    def _extract_explicit_columns(self, text: str) -> List[str]:
        columns: List[str] = []
        seen = set()

        def _push(token: str) -> None:
            cleaned = (token or '').strip().strip('.').strip(',').replace('`', '').replace('"', '')
            if not cleaned:
                return
            if not self._should_accept_column_name(cleaned, cleaned):
                return
            lowered = cleaned.lower()
            if lowered in seen:
                return
            seen.add(lowered)
            columns.append(lowered)

        for match in self.EXPLICIT_COLUMNS_RE.findall(text):
            parts = re.split(r"\s*,\s*", match.strip())
            for part in parts:
                _push(part)

        lines = [line.rstrip() for line in (text or '').splitlines()]
        collecting = False
        for raw in lines:
            line = raw.strip()
            if not line:
                if columns:
                    break
                collecting = False
                continue
            if re.search(r'(?:최소\s*)?(?:컬럼정의|필드정의|컬럼|필드|항목).*(?:아래|다음|사용|포함)', line, re.IGNORECASE) or re.search(r'^(?:[-*•]\s*)?(?:fields?|columns?|column\s*definitions?|컬럼정의|필드정의|컬럼\s*명?|필드|항목)(?:\s*(?:목록|리스트))?\s*[:：]?$', line, re.IGNORECASE):
                collecting = True
                continue
            if not collecting:
                continue
            bullet = re.match(r"^(?:[-*•]|\d+[\.)])\s*[`'\"]?([A-Za-z_][A-Za-z0-9_]*)[`'\"]?(?:\s*[|:(].*)?$", line)
            if bullet:
                _push(bullet.group(1))
                continue
            if self._should_accept_column_name(line, line):
                _push(line)
                continue
            collecting = False

        return columns

    def _extract_explicit_pk_columns(self, text: str) -> set[str]:
        pk_columns = {m.lower() for m in self.EXPLICIT_PK_RE.findall(text)}
        pk_columns |= {m.lower() for m in self.EXPLICIT_PK_ALT_RE.findall(text)}
        return pk_columns

    def _extract_explicit_table_name(self, text: str) -> str:
        for match in self.EXPLICIT_TABLE_NAME_RE.findall(text or ''):
            token = normalize_token(match)
            if self._is_valid_identifier(token):
                return token
        return ''

    def _heuristic_fields_for_domain(self, domain_name: str, auth_intent: bool = False) -> List[FieldInfo]:
        template = self.BUSINESS_DOMAIN_TEMPLATES.get(normalize_token(domain_name))
        if auth_intent and not template:
            template = self.BUSINESS_DOMAIN_TEMPLATES.get('auth')
        if template:
            fields = [
                FieldInfo(
                    name=to_camel_case(col),
                    column=col,
                    java_type=self._map_java_type(db_type),
                    db_type=db_type,
                    pk=(idx == 0),
                    nullable=(idx != 0),
                    searchable=self._looks_searchable(col),
                    display=self._looks_display_field(col),
                    source='business_template',
                )
                for idx, (col, db_type) in enumerate(template)
            ]
            self._ensure_single_pk(fields, domain_name)
            return fields

        singular = singularize(domain_name) or 'item'
        if auth_intent:
            defaults = ['user_id', 'password']
        else:
            defaults = [f'{singular}_id', f'{singular}_name']
        fields = [self._build_field(col, pk=(idx == 0)) for idx, col in enumerate(defaults)]
        self._ensure_single_pk(fields, domain_name)
        return fields

    def _infer_business_tables(self, domain_candidates: List[str], auth_intent: bool = False) -> List[TableSchema]:
        candidates = [normalize_token(x) for x in (domain_candidates or []) if normalize_token(x)]
        if auth_intent and 'login' not in candidates and 'auth' not in candidates:
            candidates = ['auth'] + candidates

        contextual_templates = self._contextual_templates(candidates)

        tables: List[TableSchema] = []
        seen = set()
        for candidate in candidates:
            template = contextual_templates.get(candidate) or self.BUSINESS_DOMAIN_TEMPLATES.get(candidate)
            if not template or candidate in seen:
                continue
            seen.add(candidate)
            fields = [
                FieldInfo(
                    name=to_camel_case(col),
                    column=col,
                    java_type=self._map_java_type(db_type),
                    db_type=db_type,
                    pk=(idx == 0),
                    nullable=(idx != 0),
                    searchable=self._looks_searchable(col),
                    display=self._looks_display_field(col),
                    source='business_template',
                )
                for idx, (col, db_type) in enumerate(template)
                if self._should_accept_column_name(col, col)
            ]
            self._ensure_single_pk(fields, candidate)
            tables.append(TableSchema(table_name=candidate, fields=fields))
        return tables


    def _contextual_templates(self, candidates: List[str]) -> dict[str, list[tuple[str, str]]]:
        candidate_set = frozenset(c for c in candidates if c)
        for required, template in self.CONTEXTUAL_DOMAIN_TEMPLATES.items():
            if required.issubset(candidate_set):
                return template
        return {}

    @staticmethod
    def _is_valid_identifier(token: str) -> bool:
        token = (token or '').strip().strip('`"')
        return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token))

    @classmethod
    def _looks_like_css_noise(cls, text: str) -> bool:
        low = (text or '').lower()
        return any(marker in low for marker in (
            'grid-template', 'minmax(', 'repeat(', 'display:', 'padding:', 'margin:',
            'border:', 'font-', 'color:', 'background:', '.autopj-', '#calendar', '.fc-',
        ))

    @classmethod
    def _should_accept_column_name(cls, token: str, context: str = '') -> bool:
        normalized = (token or '').strip().strip('`"')
        if not cls._is_valid_identifier(normalized):
            return False
        low = normalized.lower()
        if re.fullmatch(r"\d+fr(?:_\d+fr)*", low):
            return False
        if low in {'grid', 'columns', 'column', 'repeat', 'minmax', 'auto_fit', 'auto_fill'}:
            return False
        if cls._looks_like_css_noise(context):
            return False
        return True

    def _build_field(self, column_name: str, pk: bool = False, source: str = '', comment: str = '') -> FieldInfo:
        db_type = self._default_db_type_for_column(column_name)
        return FieldInfo(
            name=to_camel_case(column_name),
            column=column_name,
            java_type=self._map_java_type(db_type),
            db_type=db_type,
            pk=pk,
            nullable=not pk,
            searchable=self._looks_searchable(column_name),
            display=self._looks_display_field(column_name),
            source=source,
            comment=comment,
        )

    def _ensure_single_pk(self, fields: List[FieldInfo], domain_name: str) -> None:
        if not fields:
            return
        if any(field.pk for field in fields):
            return
        preferred_pk = f"{singularize(domain_name)}_id".lower()
        for field in fields:
            if field.column.lower() == preferred_pk or self._looks_like_pk(field.column):
                field.pk = True
                field.nullable = False
                return
        fields[0].pk = True
        fields[0].nullable = False

    @staticmethod
    def _default_db_type_for_column(column_name: str) -> str:
        lowered = (column_name or '').lower()
        if lowered.endswith('_id') or lowered in {'id', 'seq', 'no'}:
            return 'varchar(64)'
        if lowered.endswith('_yn'):
            return 'varchar(1)'
        if any(token in lowered for token in ['datetime', 'timestamp']):
            return 'datetime'
        if lowered.endswith('_dt') or lowered.endswith('_date'):
            return 'datetime'
        if any(token in lowered for token in ['content', 'remark', 'memo', 'description']):
            return 'text'
        return 'varchar(200)'

    @staticmethod
    def _map_java_type(db_type: str) -> str:
        normalized = db_type.lower()
        if any(token in normalized for token in ["date", "timestamp", "datetime"]):
            return "String"
        if "bigint" in normalized:
            return "String"
        if any(token in normalized for token in ["int", "number", "integer"]):
            return "Integer"
        if any(token in normalized for token in ["decimal", "numeric"]):
            return "BigDecimal"
        if any(token in normalized for token in ["char", "text", "clob", "varchar"]):
            return "String"
        return "String"

    @staticmethod
    def _looks_like_pk(column_name: str) -> bool:
        lowered = column_name.lower()
        return lowered.endswith("_id") or lowered in {"id", "seq", "no"} or lowered.endswith("_seq")

    @staticmethod
    def _looks_searchable(column_name: str) -> bool:
        lowered = column_name.lower()
        return any(key in lowered for key in ["name", "title", "email", "code"])

    @staticmethod
    def _looks_display_field(column_name: str) -> bool:
        lowered = column_name.lower()
        return any(key in lowered for key in ["name", "title", "content", "email"])
