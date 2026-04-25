from __future__ import annotations

from typing import Any, Dict, List
import re

from .analysis_result import DomainAnalysis, FieldInfo


_SYSTEM_COLUMNS = {
    'writer_id', 'reg_id', 'upd_id', 'create_id', 'created_by', 'updated_by', 'created_id', 'updated_id',
    'use_yn', 'del_yn', 'delete_yn', 'enabled_yn',
}
_AUDIT_COLUMNS = {
    'reg_dt', 'upd_dt', 'created_at', 'updated_at', 'create_dt', 'update_dt', 'modified_at', 'deleted_at',
}
_CALENDAR_FIELD_MARKERS = {
    'start_date', 'end_date', 'start_dt', 'end_dt', 'start_datetime', 'end_datetime', 'schedule_date', 'event_date'
}
_AUTH_SENSITIVE_MARKERS = {'password', 'passwd', 'pwd', 'passcode', 'login_password', 'user_pw', 'userpwd', 'user_pw'}
_OWNER_FIELD_MARKERS = ('member_', 'user_', 'writer_', 'owner_', 'creator_', 'reserver_', 'employee_', 'author_')
_OWNER_FIELD_EXACT = {'member_no', 'member_id', 'user_no', 'user_id', 'writer_id', 'owner_id', 'creator_id', 'reserver_id', 'author_id', 'created_by', 'updated_by', 'reg_id'}
_ROLE_FIELD_MARKERS = ('role', 'auth', 'grade', 'permission')
_ACCESS_OWNER_TERMS = ('본인', '자신', '내 일정', '내가 입력', 'my ', 'own ', 'owner', 'self')
_ACCESS_ADMIN_TERMS = ('관리자', 'admin', 'administrator', '운영자')
_ACCESS_ALL_TERMS = ('전체 사용자', '모든 사용자', '전체 회원', '모든 회원', 'all users', 'all members', 'all schedules', '전체 일정')
_GENERATION_METADATA_FIELD_MARKERS = {'db', 'dbname', 'database', 'schema', 'schemaname', 'schema_name', 'package', 'packagename', 'table', 'tablename', 'entity', 'entityname', 'project', 'projectname', 'frontend', 'frontendtype', 'backend', 'backendtype'}
_EXPLICIT_CALENDAR_TERMS = ('calendar', 'calendar view', 'monthly calendar', 'month view', '캘린더', '달력', '월간 캘린더', '캘린더 화면', '달력 화면')
_CALENDAR_NEGATION_TERMS = ('캘린더는 요청하지 않았', '캘린더는 필요 없', '달력은 요청하지 않았', '달력은 필요 없', 'calendar is not required', 'no calendar', 'without calendar', 'calendar not requested')


def _has_explicit_calendar_request(requirements_text: str) -> bool:
    lowered = str(requirements_text or '').lower()
    if not lowered.strip():
        return False
    if any(term in lowered for term in _CALENDAR_NEGATION_TERMS):
        return False
    return any(term in lowered for term in _EXPLICIT_CALENDAR_TERMS)


def _canonical_snake(name: str) -> str:
    raw = str(name or '').strip()
    if not raw:
        return 'domain'
    raw = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', raw)
    raw = re.sub(r'[^A-Za-z0-9]+', '_', raw)
    return raw.strip('_').lower() or 'domain'


def _canonical_camel(name: str) -> str:
    snake = _canonical_snake(name)
    parts = [part for part in snake.split('_') if part]
    if not parts:
        return 'domain'
    return parts[0] + ''.join(part[:1].upper() + part[1:] for part in parts[1:])


def _canonical_pascal(name: str) -> str:
    snake = _canonical_snake(name)
    parts = [part for part in snake.split('_') if part]
    if not parts:
        return 'Domain'
    return ''.join(part[:1].upper() + part[1:] for part in parts)


def _is_generation_metadata_field(column_name: str) -> bool:
    lowered = (column_name or '').strip().lower().replace('_', '')
    return lowered in _GENERATION_METADATA_FIELD_MARKERS


class IRBuilder:
    def apply(self, domain: DomainAnalysis, frontend_mode: str, requirements_text: str = '') -> DomainAnalysis:
        primary_pattern = self._primary_pattern(domain, requirements_text)
        classification = self._classification(domain, primary_pattern)
        data_model = self._data_model(domain.fields)
        domain_meta = self._domain_meta(domain)
        contracts = self._contracts(domain, primary_pattern, data_model, requirements_text, domain_meta)
        main_entry = self._main_entry(domain, frontend_mode, primary_pattern, domain_meta)
        frontend_artifacts = self._frontend_artifacts(domain, frontend_mode, primary_pattern, domain_meta)
        backend_artifacts = self._backend_artifacts(domain)
        validation_rules = self._validation_rules(data_model, main_entry, primary_pattern)
        capabilities = self._capabilities(domain, primary_pattern, data_model)

        domain.contracts = contracts
        domain.ir = {
            'domain': {
                'name': domain.name,
                'entityName': domain.entity_name,
                'table': domain.source_table or domain.name,
                'displayName': domain.entity_name,
            },
            'domainMeta': domain_meta,
            'classification': classification,
            'mainEntry': main_entry,
            'capabilities': capabilities,
            'contracts': contracts,
            'dataModel': data_model,
            'queries': self._queries(domain, primary_pattern),
            'actions': self._actions(domain, primary_pattern, data_model),
            'ui': self._ui(domain, frontend_mode, primary_pattern, frontend_artifacts, main_entry),
            'backendArtifacts': backend_artifacts,
            'frontendArtifacts': frontend_artifacts,
            'validationRules': validation_rules,
        }
        return domain

    def _primary_pattern(self, domain: DomainAnalysis, requirements_text: str) -> str:
        feature_kind = (domain.feature_kind or 'crud').strip().lower()
        cols = {f.column.lower() for f in domain.fields}
        explicit_calendar = _has_explicit_calendar_request(requirements_text)

        if feature_kind in {'auth', 'dashboard', 'master_detail', 'upload', 'code'}:
            return {
                'auth': 'auth',
                'dashboard': 'dashboard',
                'master_detail': 'master_detail',
                'upload': 'upload',
                'code': 'crud',
            }[feature_kind]

        if explicit_calendar:
            return 'calendar'
        if feature_kind == 'schedule' or cols & _CALENDAR_FIELD_MARKERS:
            return 'crud'
        return 'crud'

    def _classification(self, domain: DomainAnalysis, primary_pattern: str) -> Dict[str, Any]:
        feature_types = [str(item or '').strip().lower() for item in (domain.feature_types or [domain.feature_kind]) if str(item or '').strip()]
        secondary: List[str]
        if primary_pattern == 'auth':
            secondary = ['session']
        elif primary_pattern == 'calendar':
            secondary = ['search', 'detail', 'form']
        elif primary_pattern == 'dashboard':
            secondary = ['summary', 'search']
        elif primary_pattern == 'master_detail':
            secondary = ['detail', 'search']
        else:
            secondary = ['list', 'detail', 'form']
        return {
            'primaryPattern': primary_pattern,
            'featureTypes': feature_types,
            'secondaryPatterns': secondary,
            'boardLike': primary_pattern == 'crud',
            'authRelated': 'auth' in feature_types,
        }

    def _data_model(self, fields: List[FieldInfo]) -> Dict[str, Any]:
        result_fields: List[Dict[str, Any]] = []
        hidden: List[str] = []
        required_imports: set[str] = set()
        auth_sensitive_fields: List[str] = []
        principal_candidates: List[str] = []
        role_candidates: List[str] = []
        for field in fields:
            lowered = field.column.lower()
            role = 'business'
            auth_sensitive = self._is_auth_sensitive_field(lowered)
            if auth_sensitive:
                role = 'secret'
            elif lowered in _SYSTEM_COLUMNS:
                role = 'system'
            elif lowered in _AUDIT_COLUMNS:
                role = 'audit'
            elif _is_generation_metadata_field(lowered):
                role = 'metadata'
            elif field.pk:
                role = 'identifier'

            java_import = 'java.util.Date' if field.java_type in {'LocalDateTime', 'Date'} else ''
            if java_import:
                required_imports.add(java_import)

            editable = role == 'business' and not field.pk
            visible_in_form = editable
            visible_in_detail = role in {'business', 'identifier', 'audit'} and not auth_sensitive
            visible_in_list = bool(field.display) and role in {'business', 'identifier'} and not auth_sensitive
            searchable = role in {'business', 'identifier', 'audit'} and not auth_sensitive

            if auth_sensitive:
                auth_sensitive_fields.append(field.name)
            if self._looks_like_owner_field(lowered):
                principal_candidates.append(field.name)
            if self._looks_like_role_field(lowered):
                role_candidates.append(field.name)

            item = {
                'name': field.name,
                'column': field.column,
                'type': field.java_type,
                'dbType': field.db_type,
                'pk': field.pk,
                'nullable': field.nullable,
                'role': role,
                'editable': editable,
                'visibleInForm': visible_in_form,
                'visibleInDetail': visible_in_detail,
                'visibleInList': visible_in_list,
                'searchable': searchable,
                'authSensitive': auth_sensitive,
            }
            if java_import:
                item['javaImport'] = java_import
            if not visible_in_form:
                hidden.append(field.name)
            result_fields.append(item)

        return {
            'fields': result_fields,
            'formHiddenFields': hidden,
            'requiredJavaImports': sorted(required_imports),
            'authSensitiveFields': auth_sensitive_fields,
            'principalCandidateFields': principal_candidates,
            'roleFieldCandidates': role_candidates,
        }


    def _contracts(self, domain: DomainAnalysis, primary_pattern: str, data_model: Dict[str, Any], requirements_text: str = '', domain_meta: Dict[str, str] | None = None) -> Dict[str, Any]:
        fields = data_model.get('fields') or []
        columns = {str(field.get('column') or '').lower() for field in fields}
        searchable_fields = [str(field.get('name') or '') for field in fields if field.get('searchable')]
        status_fields = [str(field.get('name') or '') for field in fields if 'status' in str(field.get('column') or '').lower()]
        temporal_fields = [str(field.get('name') or '') for field in fields if any(token in str(field.get('column') or '').lower() for token in ('date', 'time', 'dt'))]
        attachment_fields = [str(field.get('name') or '') for field in fields if any(token in str(field.get('column') or '').lower() for token in ('file', 'attach'))]
        auth_sensitive_fields = [str(field.get('name') or '') for field in fields if field.get('authSensitive')] or list(data_model.get('authSensitiveFields') or [])
        owner_fields = [str(field.get('name') or '') for field in fields if self._looks_like_owner_field(str(field.get('column') or '').lower())] or list(data_model.get('principalCandidateFields') or [])
        role_fields = [str(field.get('name') or '') for field in fields if self._looks_like_role_field(str(field.get('column') or '').lower())] or list(data_model.get('roleFieldCandidates') or [])
        access_policy = self._access_policy(domain, requirements_text, owner_fields, role_fields)
        return {
            'featureTypes': [str(item or '').strip().lower() for item in (domain.feature_types or [domain.feature_kind]) if str(item or '').strip()],
            'search': {
                'enabled': bool(searchable_fields),
                'fields': searchable_fields,
            },
            'temporal': {
                'enabled': bool(temporal_fields) or primary_pattern == 'calendar',
                'fields': temporal_fields,
                'calendarMode': primary_pattern == 'calendar',
            },
            'status': {
                'enabled': bool(status_fields),
                'fields': status_fields,
            },
            'attachment': {
                'enabled': bool(attachment_fields) or 'upload' in (domain.feature_types or []),
                'fields': attachment_fields,
            },
            'auth': {
                'enabled': 'auth' in (domain.feature_types or []),
                'sessionRequired': 'auth' in (domain.feature_types or []),
            },
            'approval': {
                'enabled': 'approval' in (domain.feature_types or []),
                'statusFieldPresent': bool(status_fields),
            },
            'access': access_policy,
            'uiPolicy': {
                'authSensitiveFields': auth_sensitive_fields,
                'ownerFieldCandidates': owner_fields,
                'roleFieldCandidates': role_fields,
                'allowedUiFields': [str(field.get('name') or '') for field in fields if str(field.get('name') or '') and (field.get('visibleInList') or field.get('visibleInDetail') or field.get('visibleInForm'))],
                'forbiddenUiFields': sorted(set(auth_sensitive_fields + [str(field.get('name') or '') for field in fields if field.get('role') == 'metadata' and str(field.get('name') or '')])),
                'generationMetadataFields': sorted(set([str(field.get('name') or '') for field in fields if field.get('role') == 'metadata' and str(field.get('name') or '')] + ['db', 'schemaName', 'schema_name', 'database', 'tableName', 'packageName'])),
                'calendarContract': {
                    'enabled': primary_pattern == 'calendar',
                    'mainRoute': f"{(domain_meta or self._domain_meta(domain)).get('routeBase')}/calendar" if primary_pattern == 'calendar' else '',
                    'mainView': f"{(domain_meta or self._domain_meta(domain)).get('viewDir')}/{(domain_meta or self._domain_meta(domain)).get('viewDir')}Calendar" if primary_pattern == 'calendar' else '',
                },
                'separateAdminSurface': access_policy.get('separateAdminSurface') or False,
            },
            'readonly': {
                'enabled': 'readonly' in (domain.feature_types or []),
            },
            'pkField': domain.primary_key or '',
            'sourceTable': domain.source_table or domain.name,
            'columns': sorted(c for c in columns if c),
        }

    def _main_entry(self, domain: DomainAnalysis, frontend_mode: str, primary_pattern: str, domain_meta: Dict[str, str] | None = None) -> Dict[str, str]:
        meta = domain_meta or self._domain_meta(domain)
        domain_name = meta.get('canonicalCamel') or domain.name
        entity_name = meta.get('canonicalPascal') or domain.entity_name
        fm = (frontend_mode or '').strip().lower()
        if fm == 'jsp':
            if primary_pattern == 'calendar':
                return {
                    'viewType': 'calendar_month',
                    'route': f'/{domain_name}/calendar.do',
                    'jsp': f'/WEB-INF/views/{domain_name}/{domain_name}Calendar.jsp',
                }
            if primary_pattern == 'auth':
                return {
                    'viewType': 'login',
                    'route': f'/{domain_name}/login.do',
                    'jsp': f'/WEB-INF/views/{domain_name}/login.jsp',
                }
            return {
                'viewType': 'list',
                'route': f'/{domain_name}/list.do',
                'jsp': f'/WEB-INF/views/{domain_name}/{domain_name}List.jsp',
            }
        if fm == 'react':
            if primary_pattern == 'calendar':
                return {'viewType': 'calendar_month', 'route': f'/{domain_name}/calendar', 'page': f'frontend/react/src/pages/{domain_name}/{entity_name}CalendarPage.jsx'}
            if primary_pattern == 'auth':
                return {'viewType': 'login', 'route': '/login', 'page': f'frontend/react/src/pages/{domain_name}/LoginPage.jsx'}
            return {'viewType': 'list', 'route': f'/{domain_name}', 'page': f'frontend/react/src/pages/{domain_name}/{entity_name}ListPage.jsx'}
        if fm == 'vue':
            if primary_pattern == 'calendar':
                return {'viewType': 'calendar_month', 'route': f'/{domain_name}/calendar', 'page': f'frontend/vue/src/views/{domain_name}/{entity_name}Calendar.vue'}
            if primary_pattern == 'auth':
                return {'viewType': 'login', 'route': '/login', 'page': f'frontend/vue/src/views/{domain_name}/LoginView.vue'}
            return {'viewType': 'list', 'route': f'/{domain_name}/list', 'page': f'frontend/vue/src/views/{domain_name}/{entity_name}List.vue'}
        if fm == 'nexacro':
            if primary_pattern == 'calendar':
                return {'viewType': 'calendar_month', 'route': f'/{domain_name}/calendar', 'form': f'frontend/nexacro/{domain_name}/{entity_name}Calendar.xfdl'}
            if primary_pattern == 'auth':
                return {'viewType': 'login', 'route': '/login', 'form': f'frontend/nexacro/{domain_name}/LoginForm.xfdl'}
            return {'viewType': 'list', 'route': f'/{domain_name}/list', 'form': f'frontend/nexacro/{domain_name}/{entity_name}List.xfdl'}
        return {'viewType': primary_pattern, 'route': f'/{domain_name}'}

    def _domain_meta(self, domain: DomainAnalysis) -> Dict[str, str]:
        raw_name = (domain.name or 'domain').strip() or 'domain'
        raw_entity = (domain.entity_name or raw_name).strip() or raw_name
        canonical_snake = _canonical_snake(raw_name)
        canonical_camel = _canonical_camel(raw_name)
        canonical_pascal = _canonical_pascal(raw_entity)
        return {
            'rawName': raw_name,
            'canonicalSnake': canonical_snake,
            'canonicalCamel': canonical_camel,
            'canonicalPascal': canonical_pascal,
            'viewDir': canonical_camel,
            'routeBase': f'/{canonical_camel}',
        }

    def _frontend_artifacts(self, domain: DomainAnalysis, frontend_mode: str, primary_pattern: str, domain_meta: Dict[str, str] | None = None) -> Dict[str, str]:
        meta = domain_meta or self._domain_meta(domain)
        domain_name = meta.get('canonicalCamel') or domain.name
        entity_name = meta.get('canonicalPascal') or domain.entity_name
        fm = (frontend_mode or '').strip().lower()
        if fm == 'jsp':
            return {
                'mainJsp': f'src/main/webapp/WEB-INF/views/{domain_name}/{domain_name}Calendar.jsp' if primary_pattern == 'calendar' else f'src/main/webapp/WEB-INF/views/{domain_name}/{domain_name}List.jsp',
                'detailJsp': f'src/main/webapp/WEB-INF/views/{domain_name}/{domain_name}Detail.jsp',
                'formJsp': f'src/main/webapp/WEB-INF/views/{domain_name}/{domain_name}Form.jsp',
            }
        if fm == 'react':
            return {
                'mainPage': f'frontend/react/src/pages/{domain_name}/{entity_name}CalendarPage.jsx' if primary_pattern == 'calendar' else f'frontend/react/src/pages/{domain_name}/{entity_name}ListPage.jsx',
                'detailPage': f'frontend/react/src/pages/{domain_name}/{entity_name}DetailPage.jsx',
                'formPage': f'frontend/react/src/pages/{domain_name}/{entity_name}FormPage.jsx',
                'apiService': f'frontend/react/src/api/services/{domain_name}.js',
            }
        if fm == 'vue':
            return {
                'mainPage': f'frontend/vue/src/views/{domain_name}/{entity_name}Calendar.vue' if primary_pattern == 'calendar' else f'frontend/vue/src/views/{domain_name}/{entity_name}List.vue',
                'detailPage': f'frontend/vue/src/views/{domain_name}/{entity_name}Detail.vue',
                'formPage': f'frontend/vue/src/views/{domain_name}/{entity_name}Form.vue',
                'apiService': f'frontend/vue/src/api/{domain_name}Api.js',
            }
        if fm == 'nexacro':
            return {
                'mainForm': f'frontend/nexacro/{domain_name}/{entity_name}Calendar.xfdl' if primary_pattern == 'calendar' else f'frontend/nexacro/{domain_name}/{entity_name}List.xfdl',
                'detailForm': f'frontend/nexacro/{domain_name}/{entity_name}Detail.xfdl',
                'editForm': f'frontend/nexacro/{domain_name}/{entity_name}Form.xfdl',
                'serviceScript': f'frontend/nexacro/{domain_name}/{entity_name}Service.xjs',
            }
        return {}

    def _backend_artifacts(self, domain: DomainAnalysis) -> Dict[str, str]:
        naming = domain.naming
        if not naming:
            return {}
        mapper_xml_path = f'src/main/resources/egovframework/mapper/{domain.name}/{naming.mapper_class_name}.xml'
        return {
            'controller': naming.controller_class_name,
            'service': naming.service_class_name,
            'serviceImpl': naming.service_impl_class_name,
            'mapperInterface': naming.mapper_class_name,
            'vo': naming.vo_class_name,
            'mapperXml': naming.mapper_class_name + '.xml',
            'controllerPath': f"src/main/java/{naming.web_package.replace('.', '/')}/{naming.controller_class_name}.java",
            'servicePath': f"src/main/java/{naming.service_package.replace('.', '/')}/{naming.service_class_name}.java",
            'serviceImplPath': f"src/main/java/{naming.service_impl_package.replace('.', '/')}/{naming.service_impl_class_name}.java",
            'mapperPath': f"src/main/java/{naming.mapper_package.replace('.', '/')}/{naming.mapper_class_name}.java",
            'voPath': f"src/main/java/{naming.vo_package.replace('.', '/')}/{naming.vo_class_name}.java",
            'mapperXmlPath': mapper_xml_path,
        }

    def _validation_rules(self, data_model: Dict[str, Any], main_entry: Dict[str, Any], primary_pattern: str) -> Dict[str, Any]:
        return {
            'primaryPattern': primary_pattern,
            'formHiddenFields': list(data_model.get('formHiddenFields') or []),
            'requiredJavaImports': list(data_model.get('requiredJavaImports') or []),
            'mainEntryMustBe': main_entry.get('route') or '',
        }

    def _capabilities(self, domain: DomainAnalysis, primary_pattern: str, data_model: Dict[str, Any]) -> List[str]:
        caps: List[str] = []
        searchable = any(bool(f.get('searchable')) for f in data_model.get('fields') or [])
        if primary_pattern == 'auth':
            caps.extend(['login_form', 'login_submit', 'logout'])
        elif primary_pattern == 'calendar':
            caps.extend(['calendar_month_view', 'date_click_panel', 'detail_view', 'create', 'update', 'delete'])
            if searchable:
                caps.append('search_filter')
        elif primary_pattern == 'dashboard':
            caps.extend(['summary_view', 'search_filter'])
        else:
            caps.extend(['list_view', 'detail_view', 'create', 'update', 'delete'])
            if searchable:
                caps.append('search_filter')
        return caps

    def _queries(self, domain: DomainAnalysis, primary_pattern: str) -> List[Dict[str, Any]]:
        entity_name = domain.entity_name
        domain_name = domain.name
        pk_name = domain.primary_key or 'id'
        if primary_pattern == 'auth':
            return [
                {'id': f'authenticate{entity_name}', 'type': 'auth', 'params': ['userId', 'password'], 'returns': f'{entity_name}VO'},
            ]
        if primary_pattern == 'calendar':
            return [
                {'id': f'select{entity_name}Calendar', 'type': 'list', 'purpose': 'calendar_month_data', 'params': ['year', 'month'], 'returns': f'{entity_name}VO[]'},
                {'id': f'select{entity_name}ByDate', 'type': 'list', 'purpose': 'date_click_panel', 'params': ['targetDate'], 'returns': f'{entity_name}VO[]'},
                {'id': f'select{entity_name}Detail', 'type': 'detail', 'params': [pk_name], 'returns': f'{entity_name}VO'},
                {'id': f'search{entity_name}', 'type': 'search', 'params': ['keyword', 'startDate', 'endDate'], 'returns': f'{entity_name}VO[]'},
            ]
        return [
            {'id': f'select{entity_name}List', 'type': 'list', 'params': [], 'returns': f'{entity_name}VO[]'},
            {'id': f'select{entity_name}', 'type': 'detail', 'params': [pk_name], 'returns': f'{entity_name}VO'},
        ]

    def _actions(self, domain: DomainAnalysis, primary_pattern: str, data_model: Dict[str, Any]) -> List[Dict[str, Any]]:
        fields = data_model.get('fields') or []
        input_fields = [f['name'] for f in fields if f.get('visibleInForm')]
        system_fields = [f['name'] for f in fields if not f.get('visibleInForm')]
        pk_name = domain.primary_key or 'id'
        if primary_pattern == 'auth':
            return [{'id': 'login', 'type': 'auth', 'inputFields': ['userId', 'password']}]
        return [
            {'id': f'create{domain.entity_name}', 'type': 'create', 'inputFields': input_fields, 'systemAssignedFields': system_fields},
            {'id': f'update{domain.entity_name}', 'type': 'update', 'inputFields': ([pk_name] if pk_name else []) + input_fields, 'systemAssignedFields': system_fields},
            {'id': f'delete{domain.entity_name}', 'type': 'delete', 'inputFields': [pk_name] if pk_name else []},
        ]

    @staticmethod
    def _is_auth_sensitive_field(column_name: str) -> bool:
        lowered = (column_name or '').lower()
        return any(marker in lowered for marker in _AUTH_SENSITIVE_MARKERS)

    @staticmethod
    def _looks_like_owner_field(column_name: str) -> bool:
        lowered = (column_name or '').lower()
        if lowered in _OWNER_FIELD_EXACT:
            return True
        return any(lowered.startswith(marker) or marker in lowered for marker in _OWNER_FIELD_MARKERS)

    @staticmethod
    def _looks_like_role_field(column_name: str) -> bool:
        lowered = (column_name or '').lower()
        return any(marker in lowered for marker in _ROLE_FIELD_MARKERS)

    def _access_policy(self, domain: DomainAnalysis, requirements_text: str, owner_fields: List[str], role_fields: List[str]) -> Dict[str, Any]:
        req = (requirements_text or '').lower()
        owner_requested = any(term.lower() in req for term in _ACCESS_OWNER_TERMS)
        admin_requested = any(term.lower() in req for term in _ACCESS_ADMIN_TERMS)
        all_requested = any(term.lower() in req for term in _ACCESS_ALL_TERMS)
        if domain.feature_kind == 'auth':
            mode = 'auth_only'
        elif owner_fields and role_fields and admin_requested and (owner_requested or all_requested):
            mode = 'owner_admin_split'
        elif owner_fields and owner_requested:
            mode = 'owner_only'
        elif role_fields and admin_requested and all_requested:
            mode = 'admin_all'
        else:
            mode = 'shared'
        return {
            'mode': mode,
            'ownerFieldCandidates': list(owner_fields),
            'roleFieldCandidates': list(role_fields),
            'sessionScoped': mode in {'owner_admin_split', 'owner_only', 'admin_all', 'auth_only'} or domain.auth_required,
            'separateAdminSurface': mode == 'owner_admin_split',
        }

    def _ui(self, domain: DomainAnalysis, frontend_mode: str, primary_pattern: str, frontend_artifacts: Dict[str, str], main_entry: Dict[str, Any]) -> Dict[str, Any]:
        if primary_pattern == 'calendar':
            return {
                'mainScreen': {
                    'name': domain.entity_name + 'Calendar',
                    'type': 'calendar_month_screen',
                    'layout': 'calendar_with_side_panel',
                    'responsive': True,
                },
                'search': {'enabled': True, 'dateInputMode': 'calendar_picker'},
                'detailScreen': {'name': domain.entity_name + 'Detail'},
                'formScreen': {'name': domain.entity_name + 'Form'},
                'mainArtifact': frontend_artifacts.get('mainJsp') or frontend_artifacts.get('mainPage') or frontend_artifacts.get('mainForm') or main_entry.get('jsp') or main_entry.get('page') or main_entry.get('form') or '',
            }
        if primary_pattern == 'auth':
            return {
                'mainScreen': {'name': domain.entity_name + 'Login', 'type': 'login_screen', 'layout': 'single_card', 'responsive': True},
                'mainArtifact': frontend_artifacts.get('mainJsp') or frontend_artifacts.get('mainPage') or frontend_artifacts.get('mainForm') or main_entry.get('jsp') or main_entry.get('page') or main_entry.get('form') or '',
            }
        return {
            'mainScreen': {'name': domain.entity_name + 'Main', 'type': 'list_screen', 'layout': 'list_with_detail_actions', 'responsive': True},
            'mainArtifact': frontend_artifacts.get('mainJsp') or frontend_artifacts.get('mainPage') or frontend_artifacts.get('mainForm') or main_entry.get('jsp') or main_entry.get('page') or main_entry.get('form') or '',
        }
