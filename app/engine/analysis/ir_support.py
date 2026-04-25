from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Dict


def get_domain_ir(domain: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(domain, dict):
        return {}
    ir = domain.get("ir")
    return ir if isinstance(ir, dict) else {}


def get_primary_pattern(domain: Dict[str, Any] | None) -> str:
    ir = get_domain_ir(domain)
    classification = ir.get("classification") if isinstance(ir, dict) else {}
    if isinstance(classification, dict):
        value = (classification.get("primaryPattern") or "").strip().lower()
        if value:
            return value
    return ((domain or {}).get("feature_kind") or "crud").strip().lower()


def get_frontend_artifacts(domain: Dict[str, Any] | None) -> Dict[str, Any]:
    ir = get_domain_ir(domain)
    value = ir.get("frontendArtifacts") if isinstance(ir, dict) else {}
    return value if isinstance(value, dict) else {}


def get_backend_artifacts(domain: Dict[str, Any] | None) -> Dict[str, Any]:
    ir = get_domain_ir(domain)
    value = ir.get("backendArtifacts") if isinstance(ir, dict) else {}
    return value if isinstance(value, dict) else {}


def get_main_entry(domain: Dict[str, Any] | None) -> Dict[str, Any]:
    ir = get_domain_ir(domain)
    value = ir.get("mainEntry") if isinstance(ir, dict) else {}
    return value if isinstance(value, dict) else {}


def jsp_view_name_from_path(path: str) -> str:
    raw = (path or "").strip()
    marker = "src/main/webapp/WEB-INF/views/"
    if raw.startswith(marker):
        raw = raw[len(marker):]
    raw = raw.lstrip("/")
    pure = PurePosixPath(raw)
    if pure.suffix.lower() == ".jsp":
        pure = pure.with_suffix("")
    return str(pure).replace("\\", "/")


def get_contracts(domain: Dict[str, Any] | None) -> Dict[str, Any]:
    ir = get_domain_ir(domain)
    value = ir.get('contracts') if isinstance(ir, dict) else {}
    return value if isinstance(value, dict) else {}


def get_access_policy(domain: Dict[str, Any] | None) -> Dict[str, Any]:
    contracts = get_contracts(domain)
    value = contracts.get('access') if isinstance(contracts, dict) else {}
    return value if isinstance(value, dict) else {}


def get_ui_policy(domain: Dict[str, Any] | None) -> Dict[str, Any]:
    contracts = get_contracts(domain)
    value = contracts.get('uiPolicy') if isinstance(contracts, dict) else {}
    return value if isinstance(value, dict) else {}


def get_auth_sensitive_fields(domain: Dict[str, Any] | None) -> list[str]:
    policy = get_ui_policy(domain)
    value = policy.get('authSensitiveFields') if isinstance(policy, dict) else []
    return [str(item) for item in value or [] if str(item or '').strip()]


def get_domain_meta(domain: Dict[str, Any] | None) -> Dict[str, Any]:
    ir = get_domain_ir(domain)
    value = ir.get('domainMeta') if isinstance(ir, dict) else {}
    return value if isinstance(value, dict) else {}


def get_allowed_ui_fields(domain: Dict[str, Any] | None) -> list[str]:
    policy = get_ui_policy(domain)
    value = policy.get('allowedUiFields') if isinstance(policy, dict) else []
    return [str(item) for item in value or [] if str(item or '').strip()]


def get_forbidden_ui_fields(domain: Dict[str, Any] | None) -> list[str]:
    policy = get_ui_policy(domain)
    value = policy.get('forbiddenUiFields') if isinstance(policy, dict) else []
    return [str(item) for item in value or [] if str(item or '').strip()]


def get_generation_metadata_fields(domain: Dict[str, Any] | None) -> list[str]:
    policy = get_ui_policy(domain)
    value = policy.get('generationMetadataFields') if isinstance(policy, dict) else []
    return [str(item) for item in value or [] if str(item or '').strip()]

