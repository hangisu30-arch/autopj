from __future__ import annotations

from pathlib import Path

from .egov_spring_jsp import EgovSpringJspProfile


class EgovSpringReactProfile(EgovSpringJspProfile):

    _REACT_ROOT_FILES = {
        "index.html",
        "package.json",
        "vite.config.js",
        "jsconfig.json",
        ".env.development",
        ".env.production",
    }
    _REACT_DIR_PREFIXES = (
        "src/api/",
        "src/components/",
        "src/config/",
        "src/constants/",
        "src/css/",
        "src/hooks/",
        "src/pages/",
        "src/routes/",
        "src/utils/",
        "public/",
    )

    def _is_react_app_path(self, logical_path: str) -> bool:
        lp = (logical_path or "").replace("\\", "/").strip()
        if lp.startswith("frontend/react/"):
            lp = lp[len("frontend/react/"):]
        if not lp:
            return False
        if lp in self._REACT_ROOT_FILES:
            return True
        if lp.startswith(("src/main/java/", "src/main/resources/", "src/main/webapp/")):
            return False
        return lp.startswith(self._REACT_DIR_PREFIXES)

    def resolve_path_for_base(self, logical_path: str, effective_base_package: str | None = None) -> Path:
        lp = (logical_path or "").replace("\\", "/").strip()
        base = self.context.project_root
        react_root = base / "frontend" / "react"

        if lp.startswith("frontend/react/"):
            lp = lp[len("frontend/react/"):]

        if self._is_react_app_path(lp):
            return react_root / Path(lp)

        return super().resolve_path_for_base(logical_path, effective_base_package)

    def build_prompt(self, task: dict) -> str:
        path = (task.get("path") or "").replace("\\", "/")
        ext = Path(path).suffix.lower()
        if ext == ".java":
            rules = """- Output ONLY Java code (no markdown, no explanation).
- Backend is eGovFrame(Spring Boot) + React frontend.
- Java controllers must be REST API style using @RestController or @ResponseBody.
- Do NOT return JSP view names. Return JSON/body only.
- Package must start with egovframework.<project>.
- Use Service/Mapper/VO structure under semantic feature package.
- AUTH/login features must expose login/process/logout style APIs only; no generic CRUD handlers.
- CRUD features may expose list/detail/save/delete APIs for the selected entity.
"""
        elif path == "package.json":
            rules = """- Output ONLY valid JSON.
- Create a Vite + React package manifest.
- Include scripts for dev, build, and preview.
- Keep the dependency list minimal.
"""
        elif path == "vite.config.js":
            rules = """- Output ONLY JavaScript code.
- Configure Vite for React.
- Keep configuration minimal and runnable.
"""
        elif path == "index.html":
            rules = """- Output ONLY HTML.
- Provide a #root element and load /src/main.jsx as the entry script.
"""
        elif path == "src/main.jsx":
            rules = """- Output ONLY React bootstrap code.
- Mount App using ReactDOM.createRoot.
- Import the standard CSS files.
"""
        elif path == "src/App.jsx":
            rules = """- Output ONLY React code.
- Render the route registry for the app.
- Keep App minimal.
"""
        elif path == "src/routes/index.jsx":
            rules = """- Output ONLY React Router code.
- Use react-router-dom v6 style route registration.
- Import only pages that actually exist in the generated structure.
- Use route constants from src/constants/routes.js when possible.
- Do NOT import JSP/JSTL/server-side artifacts.
"""
        elif path == "src/constants/routes.js":
            rules = """- Output ONLY JavaScript code.
- Export route path constants used by React pages and route registry.
- Keep names explicit, stable, and domain-based.
- Do NOT add unrelated sample routes.
"""
        elif path == "src/api/client.js":
            rules = """- Output ONLY JavaScript code.
- Build a reusable HTTP/fetch client wrapper for the React app.
- Centralize base URL, JSON handling, and common headers.
- Do NOT mix page rendering code into this file.
"""
        elif path.startswith("src/api/services/"):
            rules = """- Output ONLY JavaScript code.
- Use the shared client from src/api/client.js.
- Export domain-specific API functions only.
- Do NOT generate JSX in service files.
- Do NOT use Egov-prefixed names.
"""
        elif ext == ".jsx":
            rules = """- Output ONLY React code.
- Use React Functional Components.
- Pages live under src/pages/... and reusable components follow the standard React structure.
- Prefer standard names like MemberListPage, MemberDetailPage, MemberFormPage, LoginPage.
- Do NOT force Egov-prefixed component names.
- Do NOT generate JSP, JSTL, or server-side view code.
- Avoid importing custom components that are not part of the generated file set.
- Keep imports consistent with the actual path.
"""
        elif ext == ".js":
            rules = """- Output ONLY JavaScript code.
- Use plain JS modules for config/constants/utils/hooks/api.
- Do NOT output JSX in .js files.
- Do NOT create duplicate .js/.jsx variants for the same role.
"""
        else:
            rules = """- Output the file content only.
- Keep backend/frontend naming consistent for the same feature.
"""
        return f"""You are an eGovFrame 4.x Spring Boot + React developer.

Purpose:
{task.get('purpose', '')}

STRICT RULES:
{rules}

Output the file content only."""
