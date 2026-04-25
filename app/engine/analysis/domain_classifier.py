from __future__ import annotations

from typing import List, Optional

from .analysis_result import DomainAnalysis
from .naming_rules import choose_domain_name, singularize, to_pascal_case
from .requirement_parser import RequirementHints
from .schema_parser import TableSchema


class DomainClassifier:
    _PRIMARY_PRECEDENCE = [
        'auth', 'dashboard', 'report', 'schedule', 'approval', 'workflow', 'master_detail', 'readonly', 'search', 'upload', 'code', 'crud'
    ]

    def classify(self, hints: RequirementHints, tables: List[TableSchema]) -> List[DomainAnalysis]:
        if not tables and not hints.domain_candidates:
            return [self._build_fallback_domain(hints)]

        domains: List[DomainAnalysis] = []

        if tables:
            for table in tables:
                domain_name = choose_domain_name([table.table_name] + hints.domain_candidates)
                feature_types = self._infer_feature_types(hints, table)
                feature_kind = self._primary_feature_kind(feature_types)
                entity_name = to_pascal_case(singularize(domain_name))
                pk = table.primary_key

                domains.append(
                    DomainAnalysis(
                        name=domain_name,
                        entity_name=entity_name,
                        feature_kind=feature_kind,
                        feature_types=feature_types,
                        auth_required=('auth' in feature_types),
                        source_table=table.table_name,
                        primary_key=pk.name if pk else '',
                        primary_key_column=pk.column if pk else '',
                        fields=table.fields,
                    )
                )
            return domains

        return [self._build_fallback_domain(hints)]

    def _build_fallback_domain(self, hints: RequirementHints) -> DomainAnalysis:
        domain_name = choose_domain_name(hints.domain_candidates or ['domain'])
        feature_types = self._infer_feature_types(hints, None)
        feature_kind = self._primary_feature_kind(feature_types)
        entity_name = to_pascal_case(singularize(domain_name))

        return DomainAnalysis(
            name=domain_name,
            entity_name=entity_name,
            feature_kind=feature_kind,
            feature_types=feature_types,
            auth_required=('auth' in feature_types),
            source_table=domain_name,
        )

    def _infer_feature_types(self, hints: RequirementHints, table: Optional[TableSchema]) -> List[str]:
        has_create_update_delete = any(action in hints.actions for action in {'create', 'update', 'delete'})
        has_crud_actions = any(action in hints.actions for action in {'list', 'detail', 'create', 'update', 'delete', 'form'})
        cols = {field.column.lower() for field in (table.fields if table else [])}

        feature_types: List[str] = []

        if hints.auth_intent and not has_crud_actions:
            feature_types.append('auth')
        if hints.dashboard_intent and not has_crud_actions:
            feature_types.append('dashboard')
        if hints.report_intent or hints.excel_intent:
            feature_types.append('report')
        if hints.calendar_intent or {'start_datetime', 'end_datetime'} <= cols or {'start_date', 'end_date'} <= cols:
            feature_types.append('schedule')
        if hints.approval_intent:
            feature_types.append('approval')
        if hints.workflow_intent:
            feature_types.append('workflow')
        if hints.readonly_intent and not has_create_update_delete:
            feature_types.append('readonly')
        if hints.search_intent:
            feature_types.append('search')
        if hints.upload_intent:
            feature_types.append('upload')
        if hints.master_detail_intent and not has_create_update_delete:
            feature_types.append('master_detail')
        if hints.code_intent and not has_crud_actions:
            feature_types.append('code')
        if has_crud_actions:
            feature_types.append('crud')

        if table and {'user_id', 'password'} <= cols and hints.auth_intent and 'auth' not in feature_types:
            feature_types.insert(0, 'auth')
        if table and not feature_types:
            if {'start_datetime', 'end_datetime'} <= cols or {'start_date', 'end_date'} <= cols:
                feature_types.extend(['schedule', 'crud'])
            else:
                feature_types.append('crud')
        if not table and not feature_types:
            feature_types.append('crud')
        if 'schedule' in feature_types and 'crud' not in feature_types and not hints.readonly_intent:
            feature_types.append('crud')
        if 'auth' in feature_types:
            feature_types = ['auth'] + [ft for ft in feature_types if ft != 'auth']
        # Dedupe while preserving order.
        deduped: List[str] = []
        seen = set()
        for feature_type in feature_types:
            if feature_type and feature_type not in seen:
                seen.add(feature_type)
                deduped.append(feature_type)
        return deduped or ['crud']

    def _primary_feature_kind(self, feature_types: List[str]) -> str:
        normalized = [str(item or '').strip().lower() for item in feature_types if str(item or '').strip()]
        for candidate in self._PRIMARY_PRECEDENCE:
            if candidate in normalized:
                return candidate
        return normalized[0] if normalized else 'crud'
