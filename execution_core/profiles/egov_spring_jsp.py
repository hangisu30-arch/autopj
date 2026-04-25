from pathlib import Path
import re
from .base import BaseProfile


class EgovSpringJspProfile(BaseProfile):

    _JAVA_KEYWORDS = {
        'abstract','assert','boolean','break','byte','case','catch','char','class','const','continue','default','do','double','else','enum','extends','final','finally','float','for','goto','if','implements','import','instanceof','int','interface','long','native','new','package','private','protected','public','return','short','static','strictfp','super','switch','synchronized','this','throw','throws','transient','try','void','volatile','while','true','false','null','record','sealed','permits','var','yield'
    }

    @staticmethod
    def _append_segment_once(base: str, segment: str, sep: str = "/") -> str:
        base = (base or "").strip(sep)
        segment = (segment or "").strip(sep)
        if not segment:
            return base
        if not base:
            return segment
        base_parts = [part for part in base.split(sep) if part]
        seg_parts = [part for part in segment.split(sep) if part]
        if not seg_parts:
            return base
        if base_parts and base_parts[-1] == seg_parts[0]:
            return sep.join(base_parts + seg_parts[1:])
        return sep.join(base_parts + seg_parts)

    @staticmethod
    def _infer_entity(filename: str) -> str:
        name = filename or ""
        for suf in ("Controller.java", "ServiceImpl.java", "Service.java", "Mapper.java", "VO.java"):
            if name.endswith(suf) and len(name) > len(suf):
                return name[:-len(suf)].lower()
        return ""

    @staticmethod
    def _project_segment(base_package: str) -> str:
        parts = [p for p in (base_package or '').split('.') if p]
        if len(parts) >= 2 and parts[0] == 'egovframework':
            return parts[1]
        return parts[-1] if parts else 'app'


    @staticmethod
    def _sanitize_package_segment(token: str) -> str:
        raw = re.sub(r"[^A-Za-z0-9_]+", "", (token or "").strip())
        if not raw:
            return "app"
        seg = raw[:1].lower() + raw[1:]
        seg = re.sub(r"^[^A-Za-z_]+", "", seg)
        if not seg:
            return "app"
        if seg in EgovSpringJspProfile._JAVA_KEYWORDS:
            return f"{seg}_"
        return seg

    @staticmethod
    def _is_generic_entity_var(ev: str) -> bool:
        return (ev or '').lower() in {"ui", "screen", "page", "view", "app", "main", "home", "form"}

    @staticmethod
    def _semantic_module(task_hint: str, entity_hint: str, base_package: str) -> str:
        ignored = {
            'java', 'jsp', 'xml', 'controller', 'service', 'impl', 'mapper', 'vo', 'config', 'web', 'package', 'import',
            'list', 'detail', 'form', 'save', 'delete', 'update', 'insert', 'select', 'index',
            'sample', 'example', 'default', 'common', 'screen', 'page', 'view', 'views', 'ui', 'app',
            'main', 'home', 'crud', 'feature', 'module', 'mybatis', 'schema', 'sql', 'resources', 'create', 'define', 'implement', 'build', 'make', 'write', 'generate'
        }
        project_seg = EgovSpringJspProfile._project_segment(base_package).lower()
        entity_hint = (entity_hint or '').lower()
        for token in re.findall(r'[A-Za-z][A-Za-z0-9_]*', task_hint or ''):
            low = token.lower()
            if low in ignored or low == project_seg or low == entity_hint:
                continue
            if low.endswith(("controller", "service", "mapper", "vo", "impl", "config")):
                continue
            return low
        return entity_hint

    def resolve_path_for_base(self, logical_path: str, effective_base_package: str | None = None) -> Path:
        base = self.context.project_root
        effective_base = effective_base_package or self.context.base_package or ""
        pkg_path = effective_base.replace(".", "/")
        lp = (logical_path or "").replace("\\", "/")

        if lp.startswith("jsp/"):
            return base / "src/main/webapp/WEB-INF/views" / lp.replace("jsp/", "")

        if lp == "index.jsp":
            return base / "src/main/webapp/index.jsp"

        if lp.startswith("mapper/"):
            base_suffix = (effective_base or "").split("egovframework.", 1)[-1].replace(".", "/")
            tail = lp.replace("mapper/", "", 1)
            entity_seg = tail.split("/", 1)[0]
            if base_suffix.endswith("/" + entity_seg) or base_suffix == entity_seg or self._is_generic_entity_var(entity_seg):
                tail = Path(tail).name
            return base / "src/main/resources/egovframework/mapper" / base_suffix / tail

        if lp.startswith("resources/"):
            return base / "src/main/resources" / lp.replace("resources/", "")

        entity_hint = self._infer_entity(Path(lp).name)
        entity_pkg_seg = self._sanitize_package_segment(entity_hint)
        entity_pkg = pkg_path if self._is_generic_entity_var(entity_hint) else self._append_segment_once(pkg_path, entity_pkg_seg, sep="/")

        if lp.startswith("java/controller/"):
            return base / f"src/main/java/{entity_pkg}/web" / Path(lp).name
        if lp.startswith("java/service/impl/") or lp.startswith("java/serviceImpl/"):
            return base / f"src/main/java/{entity_pkg}/service/impl" / Path(lp).name
        if lp.startswith("java/service/mapper/"):
            return base / f"src/main/java/{entity_pkg}/service/mapper" / Path(lp).name
        if lp.startswith("java/service/vo/"):
            return base / f"src/main/java/{entity_pkg}/service/vo" / Path(lp).name
        if lp.startswith("java/service/"):
            return base / f"src/main/java/{entity_pkg}/service" / Path(lp).name
        if lp.startswith("java/mapper/"):
            return base / f"src/main/java/{pkg_path}/mapper" / Path(lp).name
        if lp.startswith("java/config/"):
            return base / f"src/main/java/{pkg_path}/config" / Path(lp).name
        if lp.startswith("java/vo/"):
            return base / f"src/main/java/{pkg_path}/vo" / Path(lp).name
        return base / lp

    def resolve_path(self, logical_path: str) -> Path:
        return self.resolve_path_for_base(logical_path, self.context.base_package)

    def build_prompt(self, task: dict) -> str:
        path = (task.get("path") or "").replace("\\", "/")
        ext = Path(path).suffix.lower()
        rules = ""
        if ext == ".java":
            rules = """- Output ONLY code (no markdown, no explanation).
- Must include correct package declaration at top.
- Public type name must match filename.
- Never output com.example.* packages.
- Every package must start with egovframework.<project>.
- Choose a semantic feature package segment from the requirement (for example login, member, board) instead of generic names like ui, screen, page, app.
- Package examples: egovframework.<project>.login.web, egovframework.<project>.member.service, egovframework.<project>.member.service.mapper.
- Do NOT extend/use EgovAbstractServiceImpl.
- Do NOT reference legacy bean names like leaveaTrace.
- Use Spring @Service/@Controller and MyBatis @Mapper patterns only.
- Classify the feature first. AUTH/login features must not include generic CRUD handlers such as list/detail/save/delete.
- Read-only features must not include insert/update/delete methods.
"""
        elif ext == ".jsp":
            rules = """- Output ONLY JSP code.
- Do NOT use <table> tags anywhere.
- Use <ul>/<li> for list pages.
- Must include <%@ page ... %> at the top.
- Never link or submit directly to *.jsp files.
- All navigation and form actions must use controller routes such as *.do or <c:url .../> values.
"""
        elif ext == ".xml":
            rules = """- Output ONLY XML.
- If mapper xml: must include <mapper namespace="..."> and CRUD tags (MyBatis Mapper 3.0).
- NEVER output <beans>, <sqlMap>, SqlMapClientTemplate, or any iBATIS/sqlMap config.
"""

        return f"""You are an eGovFrame 4.x Spring Boot developer.

Purpose:
{task.get('purpose', '')}

STRICT RULES:
{rules}

Output the file content only."""
