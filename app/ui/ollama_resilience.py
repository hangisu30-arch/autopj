# path: app/ui/ollama_resilience.py
from __future__ import annotations

from pathlib import Path

from app.ui.ollama_client import is_transient_ollama_error_message


def _normalize_path(path: str) -> str:
    return str(path or '').replace('\\', '/').strip().lower()


def is_execution_core_managed_schema_sql(path: str) -> bool:
    norm = _normalize_path(path)
    if not norm:
        return False
    name = Path(norm).name
    if name in {'schema.sql', 'login-schema.sql'}:
        return True
    if name.startswith('schema-') and name.endswith('.sql'):
        return True
    return norm.endswith('/db/schema.sql') or norm.endswith('/resources/schema.sql')


def should_defer_ollama_file_generation(path: str, *, use_execution_core: bool, error: str) -> bool:
    return bool(use_execution_core and is_execution_core_managed_schema_sql(path) and is_transient_ollama_error_message(error))
