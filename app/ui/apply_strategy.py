from __future__ import annotations

from app.ui.state import ProjectConfig


def should_use_execution_core_apply(cfg: ProjectConfig) -> bool:
    backend = (cfg.backend_key or "").strip().lower()
    frontend = (cfg.frontend_key or "").strip().lower()
    return backend == "egov_spring" and frontend in {"jsp", "react", "vue", "nexacro"}
