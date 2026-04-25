from __future__ import annotations

from pathlib import Path

from .egov_spring_jsp import EgovSpringJspProfile


class EgovSpringNexacroProfile(EgovSpringJspProfile):

    def resolve_path_for_base(self, logical_path: str, effective_base_package: str | None = None) -> Path:
        lp = (logical_path or "").replace("\\", "/")
        base = self.context.project_root
        if lp.startswith("frontend/nexacro/"):
            return base / Path(lp)
        return super().resolve_path_for_base(logical_path, effective_base_package)

    def build_prompt(self, task: dict) -> str:
        path = (task.get("path") or "").replace("\\", "/")
        ext = Path(path).suffix.lower()
        if ext == ".java":
            rules = """- Output ONLY Java code (no markdown, no explanation).
- Backend is eGovFrame(Spring Boot) + Nexacro frontend.
- Use eGovFrame Spring controller/service/mapper structure.
- Controller methods should be suitable for Nexacro transaction/data exchange, not JSP view rendering.
- Do NOT return JSP view names.
- Package must start with egovframework.<project>.
- AUTH/login features must expose login/process/logout style endpoints only; no generic CRUD handlers.
"""
        elif ext in (".xfdl", ".xjs"):
            rules = """- Output ONLY Nexacro artifact content.
- .xfdl files define Nexacro forms/screens.
- .xjs files define Nexacro script/service helpers.
- Use dataset/transaction naming consistent with the entity in the path.
- Do NOT generate JSP or React/Vue syntax.
"""
        else:
            rules = """- Output the file content only.
- Keep backend/frontend naming consistent for the same feature.
"""
        return f"""You are an eGovFrame 4.x Spring Boot + Nexacro developer.

Purpose:
{task.get('purpose', '')}

STRICT RULES:
{rules}

Output the file content only."""
