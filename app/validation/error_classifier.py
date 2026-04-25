from __future__ import annotations

from typing import Any, Dict, List


def _classify_one(message: str) -> Dict[str, Any]:
    msg = (message or '').strip()
    low = msg.lower()
    code = 'unknown'
    severity = 'error'
    repairable = True
    target = 'general'

    if 'egovframework.' in low and 'must start' in low:
        code = 'base_package_rule'
        target = 'analysis'
    elif 'missing backend artifacts' in low:
        code = 'backend_missing_artifact'
        target = 'backend'
    elif 'missing react artifacts' in low or 'missing auth react artifacts' in low:
        code = 'react_missing_artifact'
        target = 'react'
    elif 'missing jsp views' in low:
        code = 'jsp_missing_artifact'
        target = 'jsp'
    elif 'missing vue artifacts' in low or 'missing auth vue artifacts' in low:
        code = 'vue_missing_artifact'
        target = 'vue'
    elif 'missing nexacro artifacts' in low or 'missing auth nexacro artifacts' in low:
        code = 'nexacro_missing_artifact'
        target = 'nexacro'
    elif 'jsp/react/vue path leaked into nexacro plan' in low:
        code = 'frontend_mixing_into_nexacro'
        target = 'nexacro'
    elif 'invalid nexacro artifact root' in low or 'invalid form_dir' in low or 'invalid service_script_path' in low or 'invalid dataset_prefix' in low or 'nexacro app_root must start' in low or 'invalid nexacro root' in low:
        code = 'nexacro_path_root_invalid'
        target = 'nexacro'
    elif 'non-nexacro artifact leaked into nexacro analysis plan' in low:
        code = 'nexacro_analysis_mixing'
        target = 'analysis'
    elif 'jsp path leaked into vue plan' in low:
        code = 'frontend_mixing_jsp_into_vue'
        target = 'vue'
    elif 'invalid vue artifact root' in low or 'invalid view_dir' in low or 'invalid service_path' in low or 'invalid store_path' in low:
        code = 'vue_path_root_invalid'
        target = 'vue'
    elif 'non-vue artifact leaked into vue analysis plan' in low:
        code = 'vue_analysis_mixing'
        target = 'analysis'
    elif 'invalid controller_mode' in low:
        code = 'controller_mode_mismatch'
        target = 'backend'
    elif 'jsp path leaked into react plan' in low:
        code = 'frontend_mixing_jsp_into_react'
        target = 'react'
    elif 'react artifact root' in low or 'invalid react artifact root' in low:
        code = 'react_path_root_invalid'
        target = 'react'
    elif 'invalid jsp path' in low or 'view_root must start' in low:
        code = 'jsp_path_root_invalid'
        target = 'jsp'
    elif 'duplicate' in low and 'path' in low:
        code = 'duplicate_path'
        target = 'general'
    elif 'feature_kind upload conflicts' in low or 'feature_kind schedule conflicts' in low or 'feature_kind calendar conflicts' in low:
        code = 'feature_kind_mismatch'
        target = 'analysis'
    elif 'auth domain' in low and ('crud' in low or 'forbid' in low or 'forbidden' in low):
        code = 'auth_crud_mix'
        target = 'analysis'
    elif 'template' in low and 'planner' in low:
        code = 'template_file_leak'
        target = 'planner'
    elif '코드 형태' in msg or 'code' in low and 'planner content' in low:
        code = 'planner_emitted_code'
        target = 'planner'
    elif 'json parse' in low:
        code = 'json_parse_failure'
        target = 'planner'
    elif 'unsupported package' in low or 'unsupported import' in low:
        code = 'unsupported_import'
        target = 'react'
    elif 'route' in low and 'missing' in low:
        code = 'route_missing'
        target = 'react'
    elif 'mapper.xml namespace' in low:
        code = 'mapper_namespace_mismatch'
        target = 'backend'
    elif 'invalid mybatisconfig' in low or 'missing setmapperlocations' in low or 'wildcard mapper scan is forbidden' in low:
        code = 'mybatis_config_invalid'
        target = 'backend'
    elif 'mapper interface must stay in xml-only mode' in low or 'mapper interface missing @mapper' in low or 'legacy ibatis/sqlmap xml detected' in low or 'mapper xml must declare mybatis mapper doctype' in low:
        code = 'mapper_mixed_mode'
        target = 'backend'
    elif 'service missing java.util.list import' in low or 'service impl missing java.util.list import' in low or 'service missing vo import' in low or 'service impl missing vo import' in low or 'service impl missing mapper import' in low:
        code = 'service_signature_import_mismatch'
        target = 'backend'
    elif 'controller must bind vo types only' in low:
        code = 'controller_binding_mismatch'
        target = 'jsp'
    elif 'boot application package mismatches generated modules' in low:
        code = 'boot_scan_mismatch'
        target = 'backend'
    elif 'controller too long' in low or 'too many handlers' in low or 'contains sql-like text' in low:
        code = 'jsp_controller_too_large'
        target = 'jsp'
    elif 'db column' in low or 'vo field' in low:
        code = 'schema_vo_mismatch'
        target = 'backend'
    else:
        repairable = False if 'must be a dict' in low else True

    return {
        'code': code,
        'message': msg,
        'severity': severity,
        'target': target,
        'repairable': repairable,
    }


def classify_validation_errors(messages: List[str]) -> List[Dict[str, Any]]:
    return [_classify_one(m) for m in (messages or []) if (m or '').strip()]
