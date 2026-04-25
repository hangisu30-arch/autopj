from __future__ import annotations

from pathlib import Path

from .egov_spring_jsp import EgovSpringJspProfile


class EgovSpringVueProfile(EgovSpringJspProfile):

    def resolve_path_for_base(self, logical_path: str, effective_base_package: str | None = None) -> Path:
        lp = (logical_path or "").replace("\\", "/")
        base = self.context.project_root
        if lp.startswith("frontend/vue/"):
            return base / Path(lp)
        return super().resolve_path_for_base(logical_path, effective_base_package)

    def build_prompt(self, task: dict) -> str:
        path = (task.get("path") or "").replace("\\", "/")
        ext = Path(path).suffix.lower()
        if ext == ".java":
            rules = """- Output ONLY Java code (no markdown, no explanation).
- Backend is eGovFrame(Spring Boot) + Vue frontend.
- Java controllers must be REST API style using @RestController or @ResponseBody.
- Do NOT return JSP view names. Return JSON/body only.
- Package must start with egovframework.<project>.
- Use Service/Mapper/VO structure under semantic feature package.
- AUTH/login features must expose login/process/logout style APIs only; no generic CRUD handlers.
- CRUD features may expose list/detail/save/delete APIs for the selected entity.
"""
        elif ext in (".vue", ".js"):
            rules = """- Output ONLY Vue code.
- Use Vue 3 Single File Components with <template>, <script>, and <style>.
- Views live under frontend/vue/src/views/... and API helpers under frontend/vue/src/api/...
- Use axios or fetch for backend calls.
- Do NOT generate JSP, JSTL, or server-side view code.
- Keep component/file name consistent with the entity in the path.
"""
        else:
            rules = """- Output the file content only.
- Keep backend/frontend naming consistent for the same feature.
"""
        return f"""You are an eGovFrame 4.x Spring Boot + Vue developer.

Purpose:
{task.get('purpose', '')}

STRICT RULES:
{rules}

Output the file content only."""
