# path: app/ui/main_window.py
from __future__ import annotations

from typing import Dict, Tuple
import html
import json
import os
import base64
import re
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QPlainTextEdit,
    QPushButton,
    QMessageBox,
    QFileDialog,
    QTextEdit,
    QSizePolicy,
    QProgressBar,
    QTabWidget,
    QScrollArea,
    QSplitter,
)

from app.ui.options import BACKENDS, FRONTENDS, CODE_ENGINES, DESIGN_STYLES, DATABASES, Option
from app.io.design_style_rules import build_design_style_hint, normalize_style_key
from app.ui.state import ProjectConfig
from app.ui.widgets.section_box import make_section
from app.ui.widgets.path_picker import FolderPicker
from app.ui.file_loader import read_text_file_best_effort
from app.ui.gemini_client import call_gemini, GeminiCallResult
from app.ui.ollama_client import call_ollama, OllamaCallResult
from app.ui.json_extract import extract_json_array_text, extract_json_object_or_array_text
from app.io.file_writer import apply_file_ops
from app.io.execution_core_apply import apply_file_ops_with_execution_core, _REACT_RUNTIME_BASELINE, _VUE_RUNTIME_BASELINE
from app.ui.prompt_templates import build_gemini_json_fileops_prompt
from app.ui.project_snapshot import build_project_snapshot_text, parse_target_files_text
from app.io.egov_reference_contract import normalize_project_rel_path, normalize_auth_frontend_alias, candidate_existing_paths, expand_auth_bundle_target_paths, infer_auth_bundle_paths, is_auth_related_path, parse_reference_paths
from app.ui.analysis_bridge import build_analysis_from_config, save_analysis_result
from app.ui.backend_bridge import build_backend_plan, save_backend_plan
from app.ui.jsp_bridge import build_jsp_plan, save_jsp_plan
from app.ui.react_bridge import build_react_plan, save_react_plan
from app.ui.vue_bridge import build_vue_plan, save_vue_plan
from app.ui.nexacro_bridge import build_nexacro_plan, save_nexacro_plan
from app.ui.validation_bridge import build_validation_report, save_validation_report, build_auto_repair_plan, save_auto_repair_plan
from app.ui.debug_artifacts import load_debug_bundle, render_debug_summary_text, render_analysis_text, render_plan_text, render_validation_text, render_apply_report_text
from app.validation import build_targeted_regen_prompt
from app.ui.template_generator import template_file_ops
from app.ui.apply_strategy import should_use_execution_core_apply
from app.ui.builtin_shortcuts import builtin_shortcut_content
from app.ui.json_validator import validate_file_ops_json, validate_plan_json
from app.ui.generated_content_validator import validate_generated_content
from app.ui.fallback_builder import build_builtin_fallback_content
from app.ui.runtime_fallbacks import build_frontend_runtime_fallback
from app.io.css_merge import merge_css
from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH, classify_feature_kind


# Extract fenced code blocks like:
# ```
# ...
# ```
# or ```java ... ``` / ```json ... ```
_CODE_FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_\-]+)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


# Ollama per-file output schema (best-effort). If the running Ollama version
# doesn't support JSON schema, the client will automatically fall back to format="json".
SINGLE_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "purpose": {"type": "string"},
        "content_b64": {"type": "string"},
        "content": {"type": "string"},
    },
    "required": ["path", "purpose"],
    "additionalProperties": True,
}


def _fill_combo(combo: QComboBox, options: list[Option]) -> Dict[str, int]:
    idx_map: Dict[str, int] = {}
    combo.clear()
    for i, opt in enumerate(options):
        combo.addItem(opt.label, opt.key)
        if getattr(opt, "description", ""):
            combo.setItemData(i, opt.description, Qt.ItemDataRole.ToolTipRole)
        idx_map[opt.key] = i
    return idx_map


class GeminiWorker(QThread):
    done_sig = pyqtSignal(object)  # GeminiCallResult
    log_sig = pyqtSignal(str)

    def __init__(self, prompt: str):
        super().__init__()
        self.prompt = prompt

    def run(self):
        self.log_sig.emit("Gemini 요청 시작")
        res = call_gemini(self.prompt)
        self.log_sig.emit("Gemini 완료" if getattr(res, "ok", False) else "Gemini 실패")
        self.done_sig.emit(res)
class OllamaWorker(QThread):
    done_sig = pyqtSignal(object)  # OllamaCallResult
    log_sig = pyqtSignal(str)
    chunk_sig = pyqtSignal(str)

    def __init__(self, prompt: str):
        super().__init__()
        self.prompt = prompt

    def run(self):
        self.log_sig.emit("Ollama 요청 시작")
        res = call_ollama(self.prompt, on_chunk=self.chunk_sig.emit)
        self.log_sig.emit("Ollama 완료" if getattr(res, "ok", False) else "Ollama 실패")
        self.done_sig.emit(res)



def _should_use_execution_core_apply(cfg: ProjectConfig) -> bool:
    return should_use_execution_core_apply(cfg)


class OllamaBatchWorker(QThread):
    done_sig = pyqtSignal(object)   # dict result
    log_sig = pyqtSignal(str)
    progress_sig = pyqtSignal(int, str)  # percent, status
    failed_sig = pyqtSignal(str)

    def __init__(self, cfg: ProjectConfig, gemini_text: str, out_dir: str, overwrite: bool):
        super().__init__()
        self.cfg = cfg
        self.gemini_text = gemini_text
        self.out_dir = out_dir
        self.overwrite = overwrite

    def _log(self, msg: str) -> None:
        try:
            self.log_sig.emit(msg)
        except Exception:
            pass

    def _progress(self, pct: int, status: str) -> None:
        try:
            self.progress_sig.emit(int(pct), status)
        except Exception:
            pass

    def _ext_of(self, path: str) -> str:
        p = (path or "").strip().lower().replace("\\", "/")
        name = p.rsplit("/", 1)[-1]
        if name == "pom.xml":
            return ".xml"
        if name == ".env" or name.startswith(".env.") or name == "env" or name.startswith("env."):
            return ".env"
        dot = name.rfind(".")
        return name[dot:] if dot != -1 else ""

    def _normalize_target_path(self, path: str) -> str:
        p = (path or "").strip().replace("\\", "/").lstrip("./")
        if not p:
            return ""

        if p.startswith("src/main/java/"):
            rest = p.split("src/main/java/", 1)[1]
            if "/" in rest:
                pkg_part, name = rest.rsplit("/", 1)
            else:
                pkg_part, name = "", rest
            if name.endswith(".java"):
                if pkg_part and "/" not in pkg_part and "." in pkg_part:
                    pkg_part = pkg_part.replace(".", "/")
                pkg = pkg_part
                base = pkg
                for suffix in ("/service/impl", "/service/mapper", "/service/vo", "/service", "/web", "/config"):
                    if base.endswith(suffix):
                        base = base[: -len(suffix)]
                        break
                if name.endswith("Controller.java"):
                    pkg = (base + "/web").strip("/")
                elif name.endswith("ServiceImpl.java"):
                    pkg = (base + "/service/impl").strip("/")
                elif name.endswith("Service.java"):
                    pkg = (base + "/service").strip("/")
                elif name.endswith("Mapper.java"):
                    pkg = (base + "/service/mapper").strip("/")
                elif name.endswith("VO.java"):
                    pkg = (base + "/service/vo").strip("/")
                elif name == "MyBatisConfig.java":
                    pkg = (base + "/config").strip("/")
                return f"src/main/java/{pkg}/{name}"

        if p.startswith("src/main/resources/") and p.endswith("Mapper.xml"):
            name = p.split("/")[-1]
            entity = name[:-10].lower() if name.endswith("Mapper.xml") and len(name) > 10 else "item"
            return f"src/main/resources/egovframework/mapper/{entity}/{name}"

        if p.endswith("Mapper.xml") and not p.startswith("src/main/resources/"):
            name = p.split("/")[-1]
            entity = name[:-10].lower() if name.endswith("Mapper.xml") and len(name) > 10 else "item"
            return f"src/main/resources/egovframework/mapper/{entity}/{name}"

        fk = (getattr(self.cfg, "frontend_key", "") or "").strip().lower()
        return normalize_auth_frontend_alias(normalize_project_rel_path(p), frontend_key=fk)

    def _expected_prefix(self, path: str) -> str:
        return ""

    def _ensure_path_comment(self, path: str, content: str) -> str:
        return content or ""

    def _debug_dir(self) -> Path:
        d = Path((self.out_dir or "").strip()) / ".autopj_debug"
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return d

    def _save_debug_text(self, filename: str, text: str) -> None:
        try:
            (self._debug_dir() / filename).write_text(text or "", encoding="utf-8", errors="ignore")
        except Exception:
            pass

    def _expected_java_package(self, path: str) -> str:
        p = self._normalize_target_path(path)
        anchor = "src/main/java/"
        if anchor not in p:
            return ""
        rest = p.split(anchor, 1)[1]
        if "/" not in rest:
            return ""
        pkg_path = rest.rsplit("/", 1)[0]
        return pkg_path.replace("/", ".").strip(".")

    def _entity_from_target_path(self, path: str) -> str:
        name = Path(self._normalize_target_path(path)).stem
        for suffix in ("ServiceImpl", "Service", "Mapper", "RestController", "Controller", "VO"):
            if name.endswith(suffix) and len(name) > len(suffix):
                return name[:-len(suffix)]
        return name or "Item"

    def _module_base_from_target_path(self, path: str) -> str:
        pkg = self._expected_java_package(path)
        for suffix in (".service.impl", ".service.mapper", ".service.vo", ".service", ".web", ".config"):
            if pkg.endswith(suffix):
                return pkg[: -len(suffix)]
        if pkg:
            return pkg
        p = self._normalize_target_path(path).replace("\\", "/")
        if p.startswith("src/main/resources/egovframework/mapper/"):
            entity = self._entity_from_target_path(path)
            entity_seg = entity[:1].lower() + entity[1:] if entity else "item"
            project_name = re.sub(r"[^A-Za-z0-9_]+", "", (self.cfg.project_name or "").strip()) or "app"
            project_seg = project_name[:1].lower() + project_name[1:]
            return f"egovframework.{project_seg}.{entity_seg}"
        return ""

    def _logical_builtin_path(self, path: str) -> str:
        name = Path(self._normalize_target_path(path)).name
        p = self._normalize_target_path(path).replace("\\", "/")
        if name.endswith("ServiceImpl.java"):
            return f"java/service/impl/{name}"
        if name.endswith("Service.java") and "/service/impl/" not in p and "/service/mapper/" not in p and "/service/vo/" not in p:
            return f"java/service/{name}"
        if name.endswith("Mapper.java"):
            return f"java/service/mapper/{name}"
        if name.endswith("Controller.java"):
            return f"java/controller/{name}"
        if name.endswith("VO.java"):
            return f"java/service/vo/{name}"
        if name.endswith("Mapper.xml"):
            return f"mapper/{name}"
        return ""

    def _repair_auth_generated_content(self, path: str, content: str) -> str:
        p = self._normalize_target_path(path)
        body = content or ""
        entity = self._entity_from_target_path(p)
        if classify_feature_kind(entity) != FEATURE_KIND_AUTH:
            return body

        logical = self._logical_builtin_path(p)
        if not logical:
            return body

        module_base = self._module_base_from_target_path(p)
        if not module_base:
            return body

        name = Path(p).name
        lower = body.lower()
        needs_rebuild = False

        if name.endswith("ServiceImpl.java"):
            needs_rebuild = (
                bool(re.search(r"public\s+void\s+(authenticate|login)\s*\(", body))
                or " ma.glasnost.orika" in lower
                or "map<string" in lower
            )
        elif name.endswith("Service.java"):
            needs_rebuild = (
                " map<" in lower
                or bool(re.search(r"\bvoid\s+(authenticate|login)\s*\(", body))
                or "authenticate(" not in body
            )
        elif name.endswith("Mapper.java"):
            needs_rebuild = (
                "ma.glasnost.orika" in lower
                or "interface" not in body
                or "org.apache.ibatis.annotations.mapper" not in lower
            )
        elif name.endswith("Controller.java"):
            frontend_key = (getattr(self.cfg, "frontend_key", "") or "jsp").strip().lower()
            if frontend_key in ("react", "vue", "nexacro"):
                needs_rebuild = (
                    "authenticate(" not in body
                    or ("@restcontroller" not in lower and "responseentity" not in lower)
                    or "/api/" not in lower
                )
            else:
                needs_rebuild = (
                    "httpsession" not in lower
                    or "@postmapping(\"/process.do\")" not in lower
                    or "authenticate(" not in body
                    or "/login.do" not in lower
                )
        elif name.endswith("Mapper.xml"):
            needs_rebuild = (
                "<beans" in lower
                or "<sqlmap" in lower
                or "<mapper" not in lower
                or "id=\"authenticate\"" not in lower
                or "from member" not in lower
                or "password_hash" not in lower
                or "from login" in lower
                or "and password = #{password}" in lower
            )
        elif name.endswith("VO.java"):
            needs_rebuild = (
                "private string passwordhash;" not in lower
                or "private string useyn;" not in lower
                or "private boolean useyn;" in lower
                or "private java.util.date" in lower
                or "private date" in lower
            )

        if not needs_rebuild:
            return body

        schema = schema_for(entity, feature_kind=FEATURE_KIND_AUTH)
        rebuilt = builtin_file(logical, module_base, schema)
        return rebuilt or body

    def _infer_auth_bundle_seed_text(self, tasks: list[dict]) -> str:
        parts: list[str] = []
        sources = [getattr(self.cfg, "extra_requirements", "") or ""]
        sources.extend(((it.get("purpose") or "") + "\n" + (it.get("content") or "")) for it in (tasks or []))
        for src in sources:
            text = (src or "").strip()
            if text:
                parts.append(text)
        return "\n".join(parts)

    def _build_auth_bundle_spec(self, path: str, seed_text: str = "") -> str:
        norm = self._normalize_target_path(path)
        low = norm.lower()
        hints: list[str] = []
        hint_source = (seed_text or "") + "\n" + (getattr(self.cfg, "extra_requirements", "") or "")
        for token in ("memberId", "userId", "loginId", "email", "password", "passwd", "pwd"):
            if token.lower() in hint_source.lower() and token not in hints:
                hints.append(token)
        field_hint = (
            f"- Align credential fields with project/schema hints: {', '.join(hints)}.\n"
            if hints else
            "- Align credential fields with the existing DB schema and current project conventions.\n"
        )
        if low.endswith('vo.java'):
            return (
                '- Define auth/login VO only for credential and authenticated user data.\n'
                + field_hint
                + '- Provide getters/setters for all fields and keep package path aligned with service.vo.\n'
                + '- Do not generate generic CRUD-only fields or comments.\n'
            )
        if low.endswith('service.java') and '/service/impl/' not in low:
            return (
                '- Define auth service interface only for authenticate(...) used by login flow.\n'
                + field_hint
                + '- No list/detail/save/delete methods.\n'
            )
        if low.endswith('serviceimpl.java'):
            return (
                '- Implement auth service with authenticate(...) only.\n'
                + field_hint
                + '- Delegate login lookup to Mapper and do not add CRUD logic.\n'
            )
        if low.endswith('mapper.java'):
            return (
                '- Define MyBatis mapper interface for authenticate(...) only.\n'
                + field_hint
                + '- Keep XML-only SQL mode and match Mapper XML namespace exactly.\n'
            )
        if low.endswith('mapper.xml'):
            return (
                '- Create MyBatis mapper XML for authenticate query only.\n'
                + field_hint
                + '- Use DB schema credential columns and return the auth VO.\n'
                + '- Do not generate generic CRUD statements.\n'
            )
        if low.endswith('/loginpage.jsx'):
            return (
                '- Create responsive React login page for auth flow only.\n'
                + field_hint
                + '- Include member/login ID input and password input, login error feedback, and a submit button.\n'
                + '- Use the shared auth API service and navigate after successful login. No CRUD list/detail/form UI.\n'
            )
        if low.endswith('/auth.js'):
            return (
                '- Create React auth API helpers only for login, logout, and session check.\n'
                + field_hint
                + '- Use /api/login/login, /api/login/logout, and /api/login/session endpoints only.\n'
            )
        if low.endswith('/routeguard.jsx'):
            return (
                '- Create React route guard component that checks session state and redirects unauthenticated users to /login.\n'
                + field_hint
                + '- Keep it reusable for protected routes.\n'
            )
        if low.endswith('/login.jsp'):
            return (
                '- Create responsive login JSP only for auth flow.\n'
                + field_hint
                + '- Include member/login ID input and password input, error message, submit button, and common layout rules.\n'
                + '- No list/detail/form CRUD markup. Use common.css, no inline style tag.\n'
            )
        if low.endswith('controller.java'):
            return (
                '- Create auth controller only for loginForm, process(authenticate), and logout.\n'
                + field_hint
                + '- Use VO binding, HttpSession loginUser/loginId handling, and no generic CRUD mappings.\n'
            )
        return '- Create the missing auth bundle file and align it with the same login/auth module.\n' + field_hint

    def _augment_auth_bundle_tasks(self, tasks: list[dict]) -> list[dict]:
        normalized_existing: dict[str, dict] = {}
        seed_paths: list[str] = []
        for it in tasks or []:
            norm = self._normalize_target_path((it.get('path') or '').strip())
            if not norm:
                continue
            item = dict(it)
            item['path'] = norm
            normalized_existing[norm] = item
            seed_paths.append(norm)
        for rel in parse_target_files_text(
            getattr(self.cfg, 'target_files_text', '') or '',
            frontend_key=getattr(self.cfg, 'frontend_key', '') or 'jsp',
        ):
            if rel:
                seed_paths.append(self._normalize_target_path(rel))
        required_paths = expand_auth_bundle_target_paths(
            seed_paths,
            frontend_key=getattr(self.cfg, 'frontend_key', '') or 'jsp',
        )
        if not required_paths or not any(is_auth_related_path(p) for p in required_paths):
            return list(normalized_existing.values())
        seed_text = self._infer_auth_bundle_seed_text(list(normalized_existing.values()))
        added = 0
        for req_path in required_paths:
            if req_path in normalized_existing:
                continue
            if not is_auth_related_path(req_path):
                continue
            normalized_existing[req_path] = {
                'path': req_path,
                'purpose': f'missing auth bundle file for {Path(req_path).name}',
                'content': self._build_auth_bundle_spec(req_path, seed_text),
            }
            added += 1
        if added:
            self._log(f'[BATCH] auth bundle auto-complete added={added}')
        return list(normalized_existing.values())

    def _react_runtime_fallback_content(self, path: str) -> str:
        norm = self._normalize_target_path(path).replace('\\', '/')
        if norm.startswith("frontend/react/"):
            norm = norm[len("frontend/react/"):]
        return _REACT_RUNTIME_BASELINE.get(norm, "")

    def _vue_runtime_fallback_content(self, path: str) -> str:
        norm = self._normalize_target_path(path).replace('\\', '/')
        if norm.startswith("frontend/vue/"):
            norm = norm[len("frontend/vue/"):]
        return _VUE_RUNTIME_BASELINE.get(norm, "")

    def _frontend_runtime_fallback_content(self, path: str) -> str:
        frontend_key = (getattr(self.cfg, "frontend_key", "") or "").strip().lower()
        if frontend_key == "vue":
            content = self._vue_runtime_fallback_content(path)
            if content:
                return content
        if frontend_key == "react":
            content = self._react_runtime_fallback_content(path)
            if content:
                return content
        content = self._vue_runtime_fallback_content(path)
        if content:
            return content
        return self._react_runtime_fallback_content(path)

    def _is_modify_existing_mode(self) -> bool:
        return bool(getattr(self.cfg, "modify_existing_mode", False))

    def _existing_file_path(self, path: str) -> Path | None:
        if not self._is_modify_existing_mode():
            return None
        root = Path((self.out_dir or '').strip())
        if not root.exists():
            return None
        rel = self._normalize_target_path(path)
        for candidate in candidate_existing_paths(rel):
            target = root / candidate
            if target.exists() and target.is_file():
                return target
        return None

    def _read_existing_file_content(self, path: str) -> str:
        target = self._existing_file_path(path)
        if target is None:
            return ''
        try:
            return target.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return ''

    def _compact_existing_file_content(self, path: str, content: str, limit: int = 4200) -> str:
        raw = (content or '').strip()
        if len(raw) <= limit:
            return raw
        lower_path = (path or '').replace('\\', '/').lower()
        lines = [ln.rstrip() for ln in raw.splitlines()]
        if lower_path.endswith('.jsp'):
            keys = (
                '<%@', 'common.jsp', 'leftNav.jsp', 'app-layout', 'app-main',
                'page-card', 'table-wrap', 'data-table', 'search-form', 'form-grid', 'action-row',
                'search_box', 'board_list', 'btn_area', '<main', '</main>',
                '<table', '<thead', '<tbody', '<c:forEach', 'empty-state', '조회된 데이터가 없습니다.',
                '/css/common.css',
            )
            picked = [ln for ln in lines if any(k in ln for k in keys)]
            if picked:
                snap = '\n'.join(picked).strip()
                if snap and len(snap) <= limit:
                    return snap
        head = raw[: int(limit * 0.72)].rstrip()
        tail = raw[-int(limit * 0.22):].lstrip()
        return head + '\n\n[TRIMMED EXISTING FILE]\n\n' + tail

    def _strip_jsp_directives(self, text: str) -> str:
        body = re.sub(r'(?m)^\s*<%@[^%]*%>\s*', '', text or '')
        return body.strip()

    def _extract_preferred_jsp_inner(self, text: str) -> str:
        body = self._strip_jsp_directives(text)
        for pattern in (r'<main\b[^>]*>(.*?)</main>', r'<body\b[^>]*>(.*?)</body>'):
            m = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
            if m:
                inner = (m.group(1) or '').strip()
                if inner:
                    return inner
        return body.strip()

    def _reference_file_entries(self, path: str) -> list[tuple[str, str]]:
        if not self._is_modify_existing_mode():
            return []
        refs: list[tuple[str, str]] = []
        seen: set[str] = set()
        for rel in parse_reference_paths(getattr(self.cfg, 'extra_requirements', '') or ''):
            norm_rel = self._normalize_target_path(rel)
            if not norm_rel or norm_rel == self._normalize_target_path(path) or norm_rel in seen:
                continue
            seen.add(norm_rel)
            target = self._existing_file_path(norm_rel)
            if target is None:
                continue
            try:
                refs.append((norm_rel, target.read_text(encoding='utf-8', errors='ignore')))
            except Exception:
                continue
        return refs

    def _jsp_has_shared_shell(self, text: str) -> bool:
        body = text or ''
        return any(token in body for token in ('common.jsp', 'leftNav.jsp', '/css/common.css', 'app-layout', 'app-main'))

    def _jsp_has_list_structure(self, text: str) -> bool:
        low = (text or '').lower()
        body = text or ''
        return '<table' in low and '<c:foreach' in low and '${list}' in body

    def _extract_jsp_block_by_class(self, text: str, class_token: str) -> str:
        body = text or ''
        token = re.escape(class_token)
        patterns = [
            rf'(<section\b[^>]*class="[^"]*{token}[^"]*"[^>]*>.*?</section>)',
            rf'(<div\b[^>]*class="[^"]*{token}[^"]*"[^>]*>.*?</div>)',
            rf'(<form\b[^>]*class="[^"]*{token}[^"]*"[^>]*>.*?</form>)',
            rf'(<table\b[^>]*class="[^"]*{token}[^"]*"[^>]*>.*?</table>)',
        ]
        for pattern in patterns:
            m = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
            if m:
                return (m.group(1) or '').strip()
        return ''

    def _extract_jsp_search_block(self, text: str) -> str:
        for token in ('search_box', 'search-form'):
            block = self._extract_jsp_block_by_class(text, token)
            if block:
                return block
        return ''

    def _extract_jsp_table_block(self, text: str) -> str:
        for token in ('table-wrap', 'board_list', 'data-table'):
            block = self._extract_jsp_block_by_class(text, token)
            if block:
                return block
        m = re.search(r'(<table\b[^>]*>.*?</table>)', text or '', re.IGNORECASE | re.DOTALL)
        if m:
            return (m.group(1) or '').strip()
        return ''

    def _merge_jsp_with_existing_layout(self, existing: str, generated: str, *, path: str = '', reference_entries: list[tuple[str, str]] | None = None) -> str:
        base = (existing or '').replace('\r\n', '\n')
        new_text = (generated or '').replace('\r\n', '\n')
        refs = reference_entries or []
        ref_texts = [(body or '').replace('\r\n', '\n') for _, body in refs]
        if not new_text.strip():
            return generated

        shell_source = base if self._jsp_has_shared_shell(base) else ''
        if not shell_source:
            for ref_text in ref_texts:
                if self._jsp_has_shared_shell(ref_text):
                    shell_source = ref_text
                    break
        if not shell_source:
            shell_source = base

        list_source = base if self._jsp_has_list_structure(base) else ''
        if not list_source:
            for ref_text in ref_texts:
                if self._jsp_has_list_structure(ref_text):
                    list_source = ref_text
                    break
        if not list_source:
            list_source = shell_source

        directives: list[str] = []
        seen: set[str] = set()
        for src in [shell_source, list_source, new_text]:
            for line in re.findall(r'(?m)^\s*<%@[^%]*%>\s*$', src):
                key = line.strip()
                if key and key not in seen:
                    seen.add(key)
                    directives.append(key)

        if path.lower().endswith('list.jsp'):
            new_inner = self._extract_preferred_jsp_inner(new_text)
            search_block = self._extract_jsp_search_block(new_inner)
            table_block = self._extract_jsp_table_block(new_inner)
            if not search_block:
                search_block = self._extract_jsp_search_block(list_source)
            if not table_block or '<c:foreach' not in (table_block or '').lower() or '${list}' not in (table_block or ''):
                fallback_table = self._extract_jsp_table_block(list_source)
                if fallback_table:
                    table_block = fallback_table
            if search_block or table_block:
                non_sections = new_inner
                for block in (self._extract_jsp_search_block(new_inner), self._extract_jsp_table_block(new_inner)):
                    if block:
                        non_sections = non_sections.replace(block, '').strip()
                parts = [part.strip() for part in (non_sections, search_block, table_block) if (part or '').strip()]
                new_text = '\n\n'.join(parts).strip()

        existing_main = re.search(r'(<main\b[^>]*>)(.*?)(</main>)', shell_source, re.IGNORECASE | re.DOTALL)
        if existing_main:
            new_inner = self._extract_preferred_jsp_inner(new_text)
            new_inner = re.sub(r'(?is)<jsp:include\b[^>]*leftnav\.jsp[^>]*/>\s*', '', new_inner)
            new_inner = re.sub(r'(?is)<link\b[^>]*?/css/common\.css[^>]*>\s*', '', new_inner)
            merged_shell = shell_source[:existing_main.start(2)] + '\n' + new_inner.strip() + '\n' + shell_source[existing_main.end(2):]
            merged_shell = self._strip_jsp_directives(merged_shell)
            if directives:
                return '\n'.join(directives) + '\n\n' + merged_shell.strip() + ('\n' if merged_shell.strip() else '')
            return merged_shell

        merged = new_text
        for token in ('common.jsp', 'leftNav.jsp', '/css/common.css', 'app-layout', 'app-main'):
            if token in shell_source and token not in merged:
                if token in ('common.jsp', 'leftNav.jsp'):
                    lines = [ln for ln in shell_source.splitlines() if token in ln]
                    if lines:
                        prefix = '\n'.join(lines).strip()
                        merged = prefix + '\n' + self._strip_jsp_directives(merged)
                elif token == '/css/common.css':
                    lines = [ln for ln in shell_source.splitlines() if token in ln]
                    if lines:
                        merged = '\n'.join(lines).strip() + '\n' + self._strip_jsp_directives(merged)
        if directives:
            merged = self._strip_jsp_directives(merged)
            merged = '\n'.join(directives) + '\n\n' + merged.strip()
        return merged.strip() + ('\n' if merged.strip() else '')

    def _postprocess_generated_content(self, path: str, content: str, existing_content: str = '') -> str:
        result = content or ''
        refs = self._reference_file_entries(path) if self._is_modify_existing_mode() else []
        if not existing_content and not refs:
            return result
        ext = self._ext_of(path)
        if ext == '.jsp':
            return self._merge_jsp_with_existing_layout(existing_content, result, path=path, reference_entries=refs)
        if ext == '.css':
            return merge_css(existing_content, result)
        return result

    def _validate_generated_content(self, path: str, content: str) -> Tuple[bool, str]:
        existing_content = self._read_existing_file_content(path) if self._is_modify_existing_mode() else ''
        reference_content = '\n\n'.join(body for _, body in self._reference_file_entries(path)) if self._is_modify_existing_mode() else ''
        return validate_generated_content(
            path,
            content,
            frontend_key=getattr(self.cfg, "frontend_key", ""),
            existing_content=existing_content,
            reference_content=reference_content,
            modify_existing=self._is_modify_existing_mode(),
        )

    def _clean_model_text(self, s: str) -> str:
        s = (s or "").strip()
        if not s:
            return ""
        m = _CODE_FENCE_RE.search(s)
        if m:
            inner = (m.group(1) or "").strip()
            if inner:
                return inner
        return s

    def _parse_single_file_json(self, raw: str, expected_path: str, purpose_fallback: str) -> Dict[str, str]:
        extracted = extract_json_object_or_array_text(raw)
        obj = json.loads(extracted)
        if isinstance(obj, list):
            if not obj:
                raise ValueError("empty JSON array")
            obj = obj[0]
        if not isinstance(obj, dict):
            raise ValueError("JSON must be an object or 1-item array")

        expected_path = self._normalize_target_path(expected_path)
        path = self._normalize_target_path((obj.get("path") or "").strip() or expected_path)
        if path != expected_path:
            path = expected_path

        purpose = (obj.get("purpose") or "").strip() or (purpose_fallback or "generated")
        content = obj.get("content")
        content_b64 = obj.get("content_b64")

        if isinstance(content_b64, str) and content_b64.strip():
            decoded = base64.b64decode(content_b64).decode("utf-8")
            content = decoded

        if not isinstance(content, str):
            content = ""

        content = self._ensure_path_comment(expected_path, content)
        content = self._repair_auth_generated_content(expected_path, content)

        if content.strip() == "..." or any(line.strip() == "..." for line in content.splitlines()[:10]):
            raise ValueError("content contains placeholder '...'")

        return {"path": expected_path, "purpose": purpose, "content": content}

    def _one_from_model_text(self, raw: str, expected_path: str, purpose: str) -> Dict[str, str]:
        cleaned = self._clean_model_text(raw)

        if cleaned[:1] in ("{", "["):
            try:
                return self._parse_single_file_json(cleaned, expected_path, purpose)
            except Exception:
                pass

        expected_path = self._normalize_target_path(expected_path)
        content = self._ensure_path_comment(expected_path, cleaned)
        content = self._repair_auth_generated_content(expected_path, content)
        if content.strip() == "..." or any(line.strip() == "..." for line in content.splitlines()[:10]):
            raise ValueError("content contains placeholder '...'")

        return {"path": expected_path, "purpose": purpose or "generated", "content": content}

    def _estimate_duplicate_ratio(self, text: str) -> float:
        raw = (text or "").replace("\r\n", "\n")
        lines = [re.sub(r"\s+", " ", ln.strip()) for ln in raw.splitlines() if ln.strip()]
        if len(lines) < 8:
            return 0.0
        unique = len(set(lines))
        ratio = 1.0 - (unique / max(1, len(lines)))
        return max(0.0, min(1.0, ratio))

    def _prompt_risk_report(self, path: str, spec: str, prompt: str) -> Dict[str, object]:
        p = (path or "").replace("\\", "/").lower()
        ext = self._ext_of(path)
        spec_chars = len(spec or "")
        prompt_chars = len(prompt or "")
        duplicate_ratio = self._estimate_duplicate_ratio(prompt)
        is_controller = ext == ".java" and p.endswith("controller.java")
        is_mapper_xml = ext == ".xml" and "/mapper/" in p

        warn_prompt = 4200
        high_prompt = 5600
        warn_spec = 2200
        high_spec = 3200
        if is_controller:
            warn_prompt = 3200
            high_prompt = 4200
            warn_spec = 1600
            high_spec = 2400
        elif is_mapper_xml:
            warn_prompt = 2600
            high_prompt = 3400
            warn_spec = 1700
            high_spec = 2400
        elif ext == ".jsp":
            warn_prompt = 3600
            high_prompt = 4800
            warn_spec = 2200
            high_spec = 3000

        reasons: list[str] = []
        level = "SAFE"
        if spec_chars >= high_spec:
            reasons.append(f"spec_chars>{high_spec}")
            level = "HIGH"
        elif spec_chars >= warn_spec:
            reasons.append(f"spec_chars>{warn_spec}")
            level = "WARN"

        if prompt_chars >= high_prompt:
            reasons.append(f"prompt_chars>{high_prompt}")
            level = "HIGH"
        elif prompt_chars >= warn_prompt and level != "HIGH":
            reasons.append(f"prompt_chars>{warn_prompt}")
            level = "WARN"

        if duplicate_ratio >= 0.22:
            reasons.append("duplicate_ratio>0.22")
            level = "HIGH"
        elif duplicate_ratio >= 0.12 and level != "HIGH":
            reasons.append("duplicate_ratio>0.12")
            level = "WARN"

        action = "proceed"
        if level == "WARN":
            action = "warn"
        elif level == "HIGH":
            action = "reset_and_retry"

        return {
            "level": level,
            "action": action,
            "spec_chars": spec_chars,
            "prompt_chars": prompt_chars,
            "duplicate_ratio": round(duplicate_ratio, 3),
            "reasons": reasons,
            "is_controller": is_controller,
            "is_mapper_xml": is_mapper_xml,
        }

    def _compact_file_spec(self, path: str, spec: str, aggressive: bool = False) -> str:
        raw = (spec or "").replace("\r\n", "\n").strip()
        if not raw:
            return ""
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        ext = self._ext_of(path)
        lower_path = (path or "").replace("\\", "/").lower()
        is_controller = ext == ".java" and lower_path.endswith("controller.java")
        limit = 9000
        if ext == ".xml":
            limit = 4200
        elif ext == ".jsp":
            limit = 5200
        elif ext == ".java":
            limit = 7000
        elif ext == ".sql":
            limit = 5000
        if is_controller:
            limit = min(limit, 2600 if aggressive else 3800)
        if aggressive:
            limit = max(1200, int(limit * 0.68))
        if len(raw) <= limit:
            compacted = raw
        else:
            head = raw[: int(limit * 0.72)].rstrip()
            tail = raw[-int(limit * 0.22):].lstrip()
            compacted = head + "\n\n[TRIMMED FOR PER-FILE GENERATION]\n\n" + tail
        if ext == ".xml" and "/mapper/" in lower_path:
            lines = [ln.rstrip() for ln in raw.splitlines()]
            keep = []
            keywords = ("doctype mapper", "namespace", "resultmap", "insert", "update", "delete", "select", "table", "column", "where", "from", "values", "<mapper", "</mapper>")
            for ln in lines:
                s = ln.strip().lower()
                if not s:
                    if keep and keep[-1] != "":
                        keep.append("")
                    continue
                if any(k in s for k in keywords):
                    keep.append(ln)
            if keep:
                xml_limit = min(limit, 2400 if aggressive else 3200)
                xml_compact = "\n".join(keep).strip()
                if xml_compact:
                    compacted = xml_compact[:xml_limit]
        if is_controller:
            lines = [ln.rstrip() for ln in compacted.splitlines()]
            prioritized = []
            for ln in lines:
                s = ln.strip().lower()
                if not s:
                    if prioritized and prioritized[-1] != "":
                        prioritized.append("")
                    continue
                if any(token in s for token in ("@controller", "@requestmapping", "getmapping", "postmapping", "list.do", "detail.do", "form.do", "save.do", "delete.do", "redirect:", "model", "service", "pk", "id", "return")):
                    prioritized.append(ln)
            if prioritized:
                controller_limit = min(limit, 1800 if aggressive else 2600)
                controller_compact = "\n".join(prioritized).strip()
                if controller_compact:
                    compacted = controller_compact[:controller_limit]
        return compacted

    def _build_single_file_content_prompt(self, path: str, purpose: str, spec: str) -> str:
        backend = self.cfg.backend_label
        frontend = self.cfg.frontend_label
        db = self.cfg.database_label
        style = self.cfg.design_style_label
        design_url = self.cfg.design_url

        path = self._normalize_target_path(path)
        existing_content = self._read_existing_file_content(path) if self._is_modify_existing_mode() else ''
        java_pkg = self._expected_java_package(path)
        java_name = Path(path).stem
        java_extra = ""
        if self._ext_of(path) == ".java" and java_pkg:
            java_extra = (
                "\n[JAVA REQUIREMENTS]\n"
                f"- Line 2 MUST be: package {java_pkg};\n"
                f"- MUST declare a type named '{java_name}' (class/interface/enum).\n"
                "- Use standard Java 8+ style.\n"
            )

        sql_extra = ""
        if self._ext_of(path) == ".sql":
            sql_extra = (
                "\n[SQL REQUIREMENTS]\n"
                "- Use MySQL dialect unless the spec explicitly says otherwise.\n"
                "- If creating tables, include PRIMARY KEY and sensible VARCHAR lengths.\n"
            )

        xml_extra = ""
        if self._ext_of(path) == ".xml":
            xml_budget = self._stream_budget_for_path(path)
            xml_extra = (
                "\n[XML REQUIREMENTS]\n"
                "- Generate only one clean XML document for this mapper/config file.\n"
                "- No duplicated XML declaration. No explanation. No sample blocks.\n"
                f"- Keep mapper XML compact and practical. target <= {max(900, min(xml_budget - 200, 2600))} chars unless the schema truly requires more.\n"
                "- Stop immediately after the closing </mapper> or </configuration> tag.\n"
            )

        controller_extra = ""
        lower_path = (path or "").replace("\\", "/").lower()
        if self._ext_of(path) == ".java" and lower_path.endswith("controller.java"):
            controller_extra = (
                "\n[CONTROLLER REQUIREMENTS]\n"
                "- Only include imports, mappings, service calls, redirect/view return, and minimal helper methods needed by this controller.\n"
                "- Do NOT repeat mapper/sql/xml/jsp details inside the controller.\n"
                "- Keep the controller focused and compact. target <= 4500 chars.\n"
            )

        hard_rules = f"""[HARD RULES]
1) Output ONLY the file content. No JSON. No explanation. No markdown. No code fences.
2) Do NOT output any path comment such as // path:, <!-- path:, # path:, -- path:.
3) Generate ONLY this one file for the exact path: {path}
"""

        compact_spec = self._compact_file_spec(path, spec)

        modify_block = ""
        if existing_content:
            compact_existing = self._compact_existing_file_content(path, existing_content)
            modify_block = (
                "\n[MODIFY EXISTING FILE MODE]\n"
                "- This is an update to an existing file, not a greenfield rewrite.\n"
                "- Preserve existing shared layout/include/import structure unless the spec explicitly asks to change it.\n"
                "- For JSP, preserve common.jsp include, leftNav.jsp include, /css/common.css link, app-layout/app-main shell, and shared table/page classes when already present.\n"
                "- For CSS, keep existing rules and add only missing rules needed by the request.\n"
                "- Keep unrelated content stable. Touch only what is necessary for this request.\n"
                + "\n[CURRENT FILE CONTENT]\n" + compact_existing + "\n\n[CURRENT FILE SNAPSHOT]\n" + compact_existing + "\n"
            )

        reference_block = ""
        if self._is_modify_existing_mode():
            refs = []
            seen_refs = set()
            for rel in parse_reference_paths(getattr(self.cfg, 'extra_requirements', '') or ''):
                norm_rel = self._normalize_target_path(rel)
                if norm_rel == path or norm_rel in seen_refs:
                    continue
                seen_refs.add(norm_rel)
                target = self._existing_file_path(norm_rel)
                if target is None:
                    continue
                try:
                    ref_body = target.read_text(encoding='utf-8', errors='ignore')
                except Exception:
                    continue
                refs.append(
                    "- path: " + norm_rel + "\n" + self._compact_existing_file_content(norm_rel, ref_body, limit=2600)
                )
            if refs:
                reference_block = (
                    "\n[REFERENCE MERGE RULES]\n"
                    "- Treat the reference JSP files as merge blueprints, not as loose inspiration.\n"
                    "- When the current target JSP is weak or missing shared shell, copy/merge common.jsp, leftNav.jsp, /css/common.css, app-layout, app-main from the best matching reference JSP.\n"
                    "- For list JSP, preserve or recover search block, table block, c:forEach list binding, empty-state, and egov-compatible classes(search_box, board_list, btn_area, left) from the current file or reference JSP.\n"
                    "- CSS-only requests must keep the existing list markup stable. Do not remove table/search/list-binding structure.\n"
                    "\n[REFERENCE FILES]\n" + "\n\n".join(refs) + "\n"
                )

        return (
            "You are an expert eGovFrame(Spring Boot) code generator.\n\n"
            + "[TARGET CONTEXT]\n"
            + f"- Backend: {backend}\n- Frontend: {frontend}\n- Database: {db}\n- DesignStyle: {style}\n"
            + (f"- DesignURL: {design_url}\n" if design_url else "")
            + "\n"
            + hard_rules
            + java_extra
            + sql_extra
            + xml_extra
            + controller_extra
            + modify_block
            + reference_block
            + "\n[FILE SPEC FROM GEMINI]\n"
            + compact_spec
        )

    def _regenerate_file_once(self, path: str, purpose: str, spec: str, reason: str) -> str:
        pkg = self._expected_java_package(path)
        name = Path(path).stem

        extra_rules = ""
        if self._ext_of(path) == ".java" and pkg:
            extra_rules = (
                "\n[JAVA REQUIREMENTS]\n"
                f"- Line 2 MUST be: package {pkg};\n"
                f"- MUST declare: public class {name} (or interface/enum).\n"
                "- Do NOT output any shell/script syntax.\n"
            )

        prompt = build_targeted_regen_prompt(
            path=path,
            purpose=purpose,
            spec=spec,
            reason=(reason or "") + extra_rules,
        )

        r = call_ollama(
            prompt,
            restart_if_running=False,
            options=self._ollama_options_for_path(path),
            response_format=None,
        )
        if not getattr(r, "ok", False):
            raise RuntimeError(r.error or "Ollama regenerate failed")
        return (r.text or "")

    def _stream_budget_for_path(self, path: str) -> int:
        p = (path or "").replace("\\", "/")

        def _env_int(name: str, default: int) -> int:
            try:
                v = os.getenv(name)
                return int(v) if v else default
            except Exception:
                return default

        lower = p.lower()
        ext = self._ext_of(lower)
        if ext == ".xml" and "/mapper/" in lower:
            return max(600, _env_int("AI_PG_STREAM_BUDGET_MAPPER_XML", 2400))
        if ext == ".xml":
            return max(800, _env_int("AI_PG_STREAM_BUDGET_XML", 3200))
        if ext == ".java" and lower.endswith("controller.java"):
            return max(1200, _env_int("AI_PG_STREAM_BUDGET_CONTROLLER", 5200))
        if ext == ".jsp":
            return max(1000, _env_int("AI_PG_STREAM_BUDGET_JSP", 4200))
        if ext == ".java":
            return max(1200, _env_int("AI_PG_STREAM_BUDGET_JAVA", 6000))
        return max(1000, _env_int("AI_PG_STREAM_BUDGET_OTHER", 5000))

    def _ollama_options_for_path(self, path: str) -> dict:
        p = (path or "").replace("\\", "/").lower()

        def _env_int(name: str, default: int) -> int:
            try:
                v = os.getenv(name)
                return int(v) if v else default
            except Exception:
                return default

        if p.endswith(".sql") or p.endswith("schema-mysql.sql") or p.endswith("schema.sql"):
            num_predict = _env_int("AI_PG_OLLAMA_NUM_PREDICT_SQL", 12000)
        elif p.endswith("vo.java"):
            num_predict = _env_int("AI_PG_OLLAMA_NUM_PREDICT_VO", 6500)
        elif p.endswith("controller.java"):
            num_predict = _env_int("AI_PG_OLLAMA_NUM_PREDICT_CONTROLLER", 4800)
        elif p.endswith(".java"):
            num_predict = _env_int("AI_PG_OLLAMA_NUM_PREDICT_JAVA", 8000)
        elif p.endswith(".jsp"):
            num_predict = _env_int("AI_PG_OLLAMA_NUM_PREDICT_JSP", 6000)
        elif p.endswith(".xml"):
            xml_budget = self._stream_budget_for_path(p)
            num_predict = min(_env_int("AI_PG_OLLAMA_NUM_PREDICT_XML", 2200), max(800, xml_budget + 300))
        else:
            num_predict = _env_int("AI_PG_OLLAMA_NUM_PREDICT_OTHER", 5000)

        return {
            "num_predict": max(200, int(num_predict)),
            "temperature": float(os.getenv("AI_PG_OLLAMA_TEMPERATURE", "0.2")),
            "top_p": float(os.getenv("AI_PG_OLLAMA_TOP_P", "0.9")),
        }

    def _log_prompt_precheck(self, idx: int, total: int, report: Dict[str, object]) -> None:
        level = report.get("level", "SAFE")
        if level == "SAFE":
            return
        reasons = ", ".join(report.get("reasons") or []) or "size heuristic"
        self._log(
            f"[FILE {idx}/{total}] prompt precheck {level} "
            f"(spec_chars={report.get('spec_chars')}, prompt_chars={report.get('prompt_chars')}, "
            f"duplicate_ratio={report.get('duplicate_ratio')}) reasons={reasons}"
        )

    def _call_ollama_with_guard(self, idx: int, total: int, path: str, purpose: str, spec: str, prompt: str, report: Dict[str, object]):
        import time
        import threading

        def _run_call(call_prompt: str, *, restart_if_running: bool, attempt_label: str):
            _chars = [0]
            _received = [False]
            _last_chunk_at = [time.time()]
            _stop_watch = threading.Event()
            _budget = self._stream_budget_for_path(path)
            _aborted = [False]
            _abort_reason = [""]

            def _watch_progress() -> None:
                prev_chars = 0
                while not _stop_watch.wait(10.0):
                    total_chars = _chars[0]
                    delta_chars = total_chars - prev_chars
                    idle_s = int(max(0.0, time.time() - _last_chunk_at[0]))
                    if not _received[0]:
                        self._log(f"[FILE {idx}/{total}] {attempt_label} waiting first response... stream_chars=0 elapsed=10s")
                    elif delta_chars > 0:
                        self._log(f"[FILE {idx}/{total}] {attempt_label} receiving... stream_chars={total_chars} (+{delta_chars}/10s) budget={_budget}")
                    else:
                        self._log(f"[FILE {idx}/{total}] {attempt_label} stalled? stream_chars={total_chars} (no change, idle {idle_s}s) budget={_budget}")
                    prev_chars = total_chars

            def _on_chunk(piece: str):
                if piece:
                    _chars[0] += len(piece)
                    _last_chunk_at[0] = time.time()
                    if not _received[0]:
                        self._log(f"[FILE {idx}/{total}] {attempt_label} response started")
                        _received[0] = True
                    if _chars[0] > _budget:
                        _aborted[0] = True
                        _abort_reason[0] = f"stream budget exceeded ({_chars[0]}>{_budget})"
                        self._log(f"[FILE {idx}/{total}] {attempt_label} aborting stream: {_abort_reason[0]}")
                        return False
                return True

            watcher = threading.Thread(target=_watch_progress, daemon=True)
            watcher.start()
            self._log(f"[FILE {idx}/{total}] {attempt_label} ollama request")
            try:
                res = call_ollama(
                    call_prompt,
                    on_chunk=_on_chunk,
                    restart_if_running=restart_if_running,
                    options=self._ollama_options_for_path(path),
                    response_format=None,
                )
            finally:
                _stop_watch.set()
                watcher.join(timeout=0.2)
            if _aborted[0]:
                res.ok = False
                res.error = f"stream_guard_exceeded: {_abort_reason[0]}"
            self._log(f"[FILE {idx}/{total}] {attempt_label} response complete stream_chars={_chars[0]}")
            return res, _chars[0]

        level = str(report.get("level") or "SAFE")
        first_prompt = prompt
        first_restart = False
        if level == "HIGH":
            self._log(f"[FILE {idx}/{total}] prompt risk HIGH -> reset and compact before first call")
            compact_spec = self._compact_file_spec(path, spec, aggressive=True)
            first_prompt = self._build_single_file_content_prompt(path, purpose, compact_spec)
            first_restart = True
            retry_report = self._prompt_risk_report(path, compact_spec, first_prompt)
            self._log(
                f"[FILE {idx}/{total}] prompt reset ready "
                f"(spec_chars={len(compact_spec)}, prompt_chars={len(first_prompt)}, "
                f"duplicate_ratio={retry_report.get('duplicate_ratio')})"
            )
        elif level == "WARN":
            self._log(f"[FILE {idx}/{total}] prompt risk WARN -> proceeding with compact prompt")

        res, stream_chars = _run_call(first_prompt, restart_if_running=first_restart, attempt_label="attempt1")
        if getattr(res, "ok", False) and (res.text or "").strip():
            return res, stream_chars

        err_lower = str(getattr(res, "error", "") or "").lower()
        guard_hit = "stream_guard_exceeded" in err_lower
        if guard_hit:
            self._log(f"[FILE {idx}/{total}] first call exceeded stream budget -> reset and retry once with stricter compact prompt")
        else:
            self._log(f"[FILE {idx}/{total}] first call failed or empty -> reset and retry once")
        retry_spec = self._compact_file_spec(path, spec, aggressive=True)
        retry_prompt = self._build_single_file_content_prompt(path, purpose, retry_spec)
        if self._ext_of(path) == ".xml" and "/mapper/" in (path or "").replace("\\", "/").lower():
            retry_prompt += (
                "\n[RETRY XML LIMIT]\n"
                "- Retry mode: output ONLY the final mapper XML body.\n"
                "- Keep it minimal and stop immediately at </mapper>.\n"
                "- Do not emit comments, examples, duplicate CRUD blocks, or extra whitespace.\n"
            )
        retry_report = self._prompt_risk_report(path, retry_spec, retry_prompt)
        self._log(
            f"[FILE {idx}/{total}] retry prompt ready "
            f"(spec_chars={len(retry_spec)}, prompt_chars={len(retry_prompt)}, "
            f"duplicate_ratio={retry_report.get('duplicate_ratio')})"
        )
        res2, stream_chars2 = _run_call(retry_prompt, restart_if_running=True, attempt_label="attempt2")
        return res2, stream_chars2

    def run(self):
        try:
            self._log("[BATCH] run() entered")
            extracted = extract_json_array_text(self.gemini_text or "")
            file_ops = json.loads(extracted)
            if not isinstance(file_ops, list):
                raise ValueError("Gemini JSON root must be list")

            out_dir = Path((self.out_dir or "").strip())
            out_dir.mkdir(parents=True, exist_ok=True)

            tpl_ops = template_file_ops(self.cfg)
            tpl_map = {it["path"].replace("\\", "/"): it for it in tpl_ops}

            tasks = []
            for it in file_ops:
                p = (it.get("path") or "").strip().replace("\\", "/")
                if not p:
                    continue
                if p in ("src/main/resources/application.yml", "src/main/resources/application.yaml"):
                    continue
                if p in tpl_map:
                    continue
                tasks.append(it)

            tasks = self._augment_auth_bundle_tasks(tasks)
            self._log(f"[BATCH] tasks(after filtering)={len(tasks)}, templates={len(tpl_ops)}")

            total = len(tasks)
            if total == 0:
                self._log("[BATCH] No tasks from Gemini (after template filtering)")
            else:
                self._log("[BATCH] Ollama warmup/restart")
                _ = call_ollama(
                    "Return a JSON object only: {\"ok\": true}",
                    restart_if_running=True,
                    response_format="json",
                )

            import time
            import threading
            results: list[dict] = []
            for idx, it in enumerate(tasks, start=1):
                path = (it.get("path") or "").strip().replace("\\", "/")
                purpose = (it.get("purpose") or "").strip() or "generated"
                spec = (it.get("content") or "").strip()

                pct = int((idx - 1) / max(1, total) * 90)
                self._progress(pct, f"Ollama {idx}/{total}: {path}")
                self._log(f"[FILE {idx}/{total}] start: {path}")

                shortcut_content = builtin_shortcut_content(path, self.cfg.project_name or "")
                if shortcut_content:
                    self._log(f"[FILE {idx}/{total}] builtin shortcut applied: {path}")
                    existing_content = self._read_existing_file_content(path) if self._is_modify_existing_mode() else ''
                    one = {"path": path, "purpose": purpose, "content": self._postprocess_generated_content(path, shortcut_content, existing_content)}
                    okc, errc = self._validate_generated_content(path, one.get("content", ""))
                    if not okc:
                        raise RuntimeError(f"builtin shortcut invalid for {path}: {errc}")
                    self._log(f"[FILE {idx}/{total}] validating json")
                    ok, err = validate_file_ops_json(
                        json.dumps([one], ensure_ascii=False),
                        frontend_key=self.cfg.frontend_key,
                        skip_auth_bundle_check=True,
                    )
                    if not ok:
                        raise RuntimeError(f"validation failed for {path}: {err}")
                    results.append(one)
                    self._log(f"[FILE {idx}/{total}] queued for write")
                    self._log(f"[FILE {idx}/{total}] ok: {path}")
                    continue

                compact_spec = self._compact_file_spec(path, spec)
                prompt = self._build_single_file_content_prompt(path, purpose, compact_spec)
                self._log(f"[FILE {idx}/{total}] prompt ready (spec_chars={len(compact_spec)}, prompt_chars={len(prompt)})")
                prompt_report = self._prompt_risk_report(path, compact_spec, prompt)
                self._log_prompt_precheck(idx, total, prompt_report)

                res, final_stream_chars = self._call_ollama_with_guard(idx, total, path, purpose, spec, prompt, prompt_report)
                if not getattr(res, "ok", False):
                    raise RuntimeError(f"Ollama failed for {path}: {res.error}")

                self._log(f"[FILE {idx}/{total}] final stream summary stream_chars={final_stream_chars}")
                raw = (res.text or "").strip()
                one = self._one_from_model_text(raw, path, purpose)
                existing_content = self._read_existing_file_content(path) if self._is_modify_existing_mode() else ''
                one["content"] = self._postprocess_generated_content(path, one.get("content", ""), existing_content)

                self._log(f"[FILE {idx}/{total}] validating content")
                okc, errc = self._validate_generated_content(path, one.get("content", ""))
                if not okc:
                    self._log(f"[FILE {idx}/{total}] content invalid, regenerating: {errc}")
                    self._save_debug_text(f"decoded_{idx:02d}of{total:02d}_{Path(path).name}.txt", one.get("content", ""))
                    self._log(f"[FILE {idx}/{total}] regenerate request")
                    regen_raw = self._regenerate_file_once(path, purpose, spec, errc)
                    self._save_debug_text(f"regen_raw_{idx:02d}of{total:02d}_{Path(path).name}.txt", regen_raw)
                    self._log(f"[FILE {idx}/{total}] re-validating content")
                    one = self._one_from_model_text(regen_raw, path, purpose)
                    one["content"] = self._postprocess_generated_content(path, one.get("content", ""), existing_content)
                    okc2, errc2 = self._validate_generated_content(path, one.get("content", ""))
                    if not okc2:
                        fallback_content = build_builtin_fallback_content(path, spec, project_name=self.cfg.project_name or "", style_key=self.cfg.design_style_key)
                        if not fallback_content:
                            fallback_content = build_builtin_fallback_content(path, spec, project_name=self.cfg.project_name, style_key=self.cfg.design_style_key)
                        if not fallback_content and (self.cfg.frontend_key or "").strip().lower() == "react":
                            fallback_content = self._react_runtime_fallback_content(path)
                        if not fallback_content:
                            fallback_content = build_frontend_runtime_fallback(path, self.cfg.frontend_key, spec=spec, project_name=self.cfg.project_name)
                        if fallback_content:
                            okf, errf = self._validate_generated_content(path, fallback_content)
                            if okf:
                                self._log(f"[FILE {idx}/{total}] runtime baseline fallback applied: {path}")
                                one = {"path": path, "purpose": purpose, "content": self._postprocess_generated_content(path, fallback_content, existing_content)}
                            else:
                                raise RuntimeError(f"content still invalid after regenerate: {errc2}; fallback invalid: {errf}")
                        else:
                            raise RuntimeError(f"content still invalid after regenerate: {errc2}")

                self._log(f"[FILE {idx}/{total}] validating json")
                ok, err = validate_file_ops_json(
                    json.dumps([one], ensure_ascii=False),
                    frontend_key=self.cfg.frontend_key,
                    skip_auth_bundle_check=True,
                )
                if not ok:
                    raise RuntimeError(f"validation failed for {path}: {err}")

                results.append(one)
                self._log(f"[FILE {idx}/{total}] queued for write")
                self._log(f"[FILE {idx}/{total}] ok: {path}")

            final_ops = list(tpl_ops) + results
            self._log("[BATCH] validating final json")
            ok, err = validate_file_ops_json(
                json.dumps(final_ops, ensure_ascii=False),
                frontend_key=self.cfg.frontend_key,
            )
            if not ok:
                raise RuntimeError(f"final validation failed: {err}")

            self._progress(92, "Writing files")

            if _should_use_execution_core_apply(self.cfg):
                report = apply_file_ops_with_execution_core(final_ops, out_dir, self.cfg, overwrite=self.overwrite)
            else:
                report = apply_file_ops(final_ops, out_dir, overwrite=self.overwrite)

            (out_dir / "apply_report.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self._progress(100, "Done")
            self.done_sig.emit({"ok": True, "report": report, "out_dir": str(out_dir)})
        except Exception:
            import traceback
            tb = traceback.format_exc()
            self._log("[BATCH] FAILED\n" + tb)
            self.failed_sig.emit(tb)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Project Generator - Top Panel (eGovFrame)")
        self.setMinimumSize(1280, 920)

        self.cfg = ProjectConfig()
        self._gemini_worker: GeminiWorker | None = None
        self._ollama_worker: OllamaWorker | None = None  # legacy (single-shot)
        self._ollama_batch_worker: OllamaBatchWorker | None = None
        self._last_gemini_json_ok: bool = False
        self._last_analysis_result: dict | None = None
        self._last_validation_report: dict | None = None
        self._last_repair_plan: dict | None = None

        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.setSpacing(10)

        status_box = make_section("작업 상태", "sec_status", "#f8fafc")
        status_layout = QHBoxLayout(status_box)
        status_layout.setContentsMargins(12, 10, 12, 12)
        status_layout.setSpacing(12)
        self.status_lbl = QLabel("대기")
        self.status_lbl.setStyleSheet("font-weight:700; color:#0f172a;")
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(False)
        self.progress.setMaximumHeight(10)
        status_layout.addWidget(self.status_lbl, 0)
        status_layout.addWidget(self.progress, 1)
        outer.addWidget(status_box)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        outer.addWidget(splitter, 1)

        config_scroll = QScrollArea()
        config_scroll.setWidgetResizable(True)
        config_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        splitter.addWidget(config_scroll)

        config_host = QWidget()
        config_scroll.setWidget(config_host)
        config_layout = QVBoxLayout(config_host)
        config_layout.setContentsMargins(0, 0, 0, 0)
        config_layout.setSpacing(12)

        basic_box = make_section("기본 정보", "sec_basic", "#ffffff")
        basic_layout = QGridLayout(basic_box)
        basic_layout.setHorizontalSpacing(12)
        basic_layout.setVerticalSpacing(10)
        config_layout.addWidget(basic_box)

        basic_layout.addWidget(QLabel("프로젝트 이름"), 0, 0)
        self.project_name_edit = QLineEdit()
        self.project_name_edit.setPlaceholderText("프로젝트 이름")
        basic_layout.addWidget(self.project_name_edit, 0, 1, 1, 3)

        basic_layout.addWidget(QLabel("출력 폴더"), 1, 0)
        self.folder_picker = FolderPicker(placeholder="프로젝트 출력 폴더 경로")
        basic_layout.addWidget(self.folder_picker, 1, 1, 1, 3)

        self.overwrite_chk = QCheckBox("기존 폴더 덮어쓰기")
        self.overwrite_chk.setChecked(True)
        basic_layout.addWidget(self.overwrite_chk, 2, 1, 1, 1)
        self.modify_existing_chk = QCheckBox("기존 생성물 수정 모드")
        self.modify_existing_chk.setChecked(False)
        basic_layout.addWidget(self.modify_existing_chk, 2, 2, 1, 2)
        basic_layout.setColumnStretch(1, 1)
        basic_layout.setColumnStretch(3, 1)

        settings_grid = QGridLayout()
        settings_grid.setHorizontalSpacing(12)
        settings_grid.setVerticalSpacing(12)
        config_layout.addLayout(settings_grid)

        sec_stack = make_section("생성 대상", "sec_stack", "#eef6ff")
        settings_grid.addWidget(sec_stack, 0, 0)
        stack_layout = QGridLayout(sec_stack)
        stack_layout.setHorizontalSpacing(10)
        stack_layout.setVerticalSpacing(10)
        stack_layout.addWidget(QLabel("백엔드"), 0, 0)
        self.backend_combo = QComboBox()
        self._backend_map = _fill_combo(self.backend_combo, BACKENDS)
        stack_layout.addWidget(self.backend_combo, 0, 1)
        stack_layout.addWidget(QLabel("프론트엔드"), 0, 2)
        self.frontend_combo = QComboBox()
        self._frontend_map = _fill_combo(self.frontend_combo, FRONTENDS)
        stack_layout.addWidget(self.frontend_combo, 0, 3)
        stack_layout.setColumnStretch(1, 1)
        stack_layout.setColumnStretch(3, 1)

        sec_engine = make_section("생성 엔진", "sec_engine", "#eefaf1")
        settings_grid.addWidget(sec_engine, 0, 1)
        eng_layout = QGridLayout(sec_engine)
        eng_layout.setHorizontalSpacing(10)
        eng_layout.setVerticalSpacing(10)
        eng_layout.addWidget(QLabel("코드 생성 엔진"), 0, 0)
        self.engine_combo = QComboBox()
        self._engine_map = _fill_combo(self.engine_combo, CODE_ENGINES)
        eng_layout.addWidget(self.engine_combo, 0, 1)
        eng_layout.setColumnStretch(1, 1)

        sec_design = make_section("디자인 설정", "sec_design", "#fff7e8")
        settings_grid.addWidget(sec_design, 1, 0)
        design_layout = QGridLayout(sec_design)
        design_layout.setHorizontalSpacing(10)
        design_layout.setVerticalSpacing(10)
        design_layout.addWidget(QLabel("디자인 스타일"), 0, 0)
        self.design_style_combo = QComboBox()
        self._design_map = _fill_combo(self.design_style_combo, DESIGN_STYLES)
        design_layout.addWidget(self.design_style_combo, 0, 1)
        self.design_style_desc = QLabel()
        self.design_style_desc.setWordWrap(True)
        self.design_style_desc.setObjectName("design_style_desc")
        design_layout.addWidget(self.design_style_desc, 1, 1)
        design_layout.addWidget(QLabel("디자인 URL"), 2, 0)
        self.design_url_edit = QLineEdit()
        self.design_url_edit.setPlaceholderText("디자인 참고 URL (선택)")
        design_layout.addWidget(self.design_url_edit, 2, 1)
        design_layout.setColumnStretch(1, 1)

        sec_db = make_section("데이터베이스", "sec_db", "#f4efff")
        settings_grid.addWidget(sec_db, 1, 1)
        db_layout = QGridLayout(sec_db)
        db_layout.setHorizontalSpacing(10)
        db_layout.setVerticalSpacing(10)
        db_layout.addWidget(QLabel("데이터베이스"), 0, 0)
        self.db_combo = QComboBox()
        self._db_map = _fill_combo(self.db_combo, DATABASES)
        db_layout.addWidget(self.db_combo, 0, 1)
        db_layout.addWidget(QLabel("DB 이름"), 0, 2)
        self.db_name_edit = QLineEdit()
        self.db_name_edit.setPlaceholderText("DB 이름 (기본값: 프로젝트 이름)")
        db_layout.addWidget(self.db_name_edit, 0, 3)
        db_layout.addWidget(QLabel("DB Login ID"), 1, 0)
        self.db_login_edit = QLineEdit()
        self.db_login_edit.setPlaceholderText("DB Login ID (선택)")
        db_layout.addWidget(self.db_login_edit, 1, 1)
        db_layout.addWidget(QLabel("DB PW"), 1, 2)
        self.db_pw_edit = QLineEdit()
        self.db_pw_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.db_pw_edit.setPlaceholderText("DB PW (선택)")
        db_layout.addWidget(self.db_pw_edit, 1, 3)
        db_layout.setColumnStretch(1, 1)
        db_layout.setColumnStretch(3, 1)

        settings_grid.setColumnStretch(0, 1)
        settings_grid.setColumnStretch(1, 1)

        work_grid = QGridLayout()
        work_grid.setHorizontalSpacing(12)
        work_grid.setVerticalSpacing(12)
        config_layout.addLayout(work_grid)

        requirements_box = make_section("추가 요구사항", "sec_requirements", "#ffffff")
        work_grid.addWidget(requirements_box, 0, 0)
        req_layout = QVBoxLayout(requirements_box)
        req_layout.setSpacing(8)
        extra_header = QHBoxLayout()
        extra_header.addWidget(QLabel("요구사항 / 기능 설명"))
        extra_header.addStretch(1)
        self.extra_load_btn = QPushButton("요구사항 파일 불러오기")
        self.extra_load_btn.clicked.connect(self.on_load_extra_requirements_file)
        extra_header.addWidget(self.extra_load_btn)
        req_layout.addLayout(extra_header)
        self.extra_edit = QPlainTextEdit()
        self.extra_edit.setPlaceholderText("예) 로그인 페이지 UI 추가\n예) 회원 관리 목록/상세/등록/수정/삭제\n예) React 기준 REST API + 페이지 라우트 생성")
        self.extra_edit.setMinimumHeight(150)
        req_layout.addWidget(self.extra_edit)
        req_layout.addWidget(QLabel("수정 대상 파일(선택, 줄바꿈 또는 콤마 구분)"))
        self.target_files_edit = QPlainTextEdit()
        self.target_files_edit.setPlaceholderText("예) src/main/webapp/WEB-INF/views/member/memberList.jsp\n예) src/main/webapp/css/common.css")
        self.target_files_edit.setMinimumHeight(90)
        req_layout.addWidget(self.target_files_edit)

        actions_box = make_section("실행 / 상태", "sec_actions", "#ffffff")
        work_grid.addWidget(actions_box, 0, 1)
        action_layout = QVBoxLayout(actions_box)
        action_layout.setSpacing(10)
        self.only_allow_ollama_when_json_ok_chk = QCheckBox("Gemini 출력 json 검증 통과 시에만 Ollama 전달 허용")
        self.only_allow_ollama_when_json_ok_chk.setChecked(True)
        self.only_allow_ollama_when_json_ok_chk.stateChanged.connect(self._update_ollama_gate_state)
        action_layout.addWidget(self.only_allow_ollama_when_json_ok_chk)

        action_btn_row = QHBoxLayout()
        action_btn_row.setSpacing(8)
        self.gemini_btn = QPushButton("제미나이 생성")
        self.gemini_btn.clicked.connect(self.on_gemini_generate)
        action_btn_row.addWidget(self.gemini_btn)
        self.ollama_btn = QPushButton("Ollama 전달")
        self.ollama_btn.clicked.connect(self.on_ollama_send)
        action_btn_row.addWidget(self.ollama_btn)
        self.print_btn = QPushButton("현재 설정 출력")
        self.print_btn.clicked.connect(self._on_print)
        action_btn_row.addWidget(self.print_btn)
        self.refresh_debug_btn = QPushButton("디버그 결과 새로고침")
        self.refresh_debug_btn.clicked.connect(self._refresh_debug_views)
        action_btn_row.addWidget(self.refresh_debug_btn)
        action_layout.addLayout(action_btn_row)

        action_layout.addWidget(QLabel("현재 분석/계획/검증 요약"))
        self.debug_summary_view = QPlainTextEdit()
        self.debug_summary_view.setReadOnly(True)
        self.debug_summary_view.setMaximumBlockCount(300)
        self.debug_summary_view.setMinimumHeight(130)
        self.debug_summary_view.setMaximumHeight(180)
        action_layout.addWidget(self.debug_summary_view, 1)

        work_grid.setColumnStretch(0, 3)
        work_grid.setColumnStretch(1, 2)

        tabs_host = QWidget()
        tabs_layout = QVBoxLayout(tabs_host)
        tabs_layout.setContentsMargins(0, 0, 0, 0)
        tabs_layout.setSpacing(8)
        splitter.addWidget(tabs_host)

        tabs_header = QHBoxLayout()
        tabs_header.addWidget(QLabel("생성 결과 / 디버그 상세"))
        tabs_header.addStretch(1)
        tabs_layout.addLayout(tabs_header)

        self.gemini_out = QTextEdit()
        self.gemini_out.setReadOnly(True)
        self.gemini_out.setMinimumHeight(130)
        self.gemini_out.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self.output_tabs = QTabWidget()
        tabs = self.output_tabs
        tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        gem_tab = QWidget()
        gem_layout = QVBoxLayout(gem_tab)
        gem_layout.setContentsMargins(0, 0, 0, 0)
        gem_layout.setSpacing(6)
        gem_layout.addWidget(self.gemini_out)
        tabs.addTab(gem_tab, "Gemini 출력")

        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(6)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(2000)
        self.log_view.setMinimumHeight(140)
        log_layout.addWidget(self.log_view)
        tabs.addTab(log_tab, "실행 로그")

        analysis_tab = QWidget()
        analysis_layout = QVBoxLayout(analysis_tab)
        analysis_layout.setContentsMargins(0, 0, 0, 0)
        analysis_layout.setSpacing(6)
        self.analysis_view = QPlainTextEdit()
        self.analysis_view.setReadOnly(True)
        self.analysis_view.setMaximumBlockCount(4000)
        self.analysis_view.setMinimumHeight(140)
        analysis_layout.addWidget(self.analysis_view)
        tabs.addTab(analysis_tab, "분석 결과")

        plan_tab = QWidget()
        plan_layout = QVBoxLayout(plan_tab)
        plan_layout.setContentsMargins(0, 0, 0, 0)
        plan_layout.setSpacing(6)
        self.plan_view = QPlainTextEdit()
        self.plan_view.setReadOnly(True)
        self.plan_view.setMaximumBlockCount(6000)
        self.plan_view.setMinimumHeight(140)
        plan_layout.addWidget(self.plan_view)
        tabs.addTab(plan_tab, "생성 계획")

        validation_tab = QWidget()
        validation_layout = QVBoxLayout(validation_tab)
        validation_layout.setContentsMargins(0, 0, 0, 0)
        validation_layout.setSpacing(6)
        self.validation_view = QPlainTextEdit()
        self.validation_view.setReadOnly(True)
        self.validation_view.setMaximumBlockCount(4000)
        self.validation_view.setMinimumHeight(140)
        validation_layout.addWidget(self.validation_view)
        tabs.addTab(validation_tab, "검증/복구")

        apply_tab = QWidget()
        apply_layout = QVBoxLayout(apply_tab)
        apply_layout.setContentsMargins(0, 0, 0, 0)
        apply_layout.setSpacing(6)
        self.apply_report_view = QPlainTextEdit()
        self.apply_report_view.setReadOnly(True)
        self.apply_report_view.setMaximumBlockCount(6000)
        self.apply_report_view.setMinimumHeight(140)
        apply_layout.addWidget(self.apply_report_view)
        tabs.addTab(apply_tab, "적용 보고서")

        tabs_layout.addWidget(tabs, 1)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([520, 420])

        self._bind_events()
        self._apply_defaults()
        self._update_ollama_gate_state()
        self._refresh_debug_views()

        self.setStyleSheet(
            """
            QWidget { background: #f5f7fb; color: #111827; }
            QLabel { color: #1f2937; }
            QLineEdit, QPlainTextEdit, QComboBox, QTextEdit {
                background: #ffffff;
                border: 1px solid #d7dce5;
                border-radius: 8px;
                padding: 7px 8px;
                selection-background-color: #dbeafe;
            }
            QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QTextEdit:focus {
                border: 1px solid #93c5fd;
            }
            QPushButton {
                padding: 9px 14px;
                border-radius: 8px;
                border: 1px solid #cbd5e1;
                background: #ffffff;
            }
            QPushButton:hover { background: #f8fafc; }
            QPushButton:disabled { background: #f3f4f6; color: #9ca3af; }
            QTabWidget::pane {
                border: 1px solid #d7dce5;
                border-radius: 10px;
                background: #ffffff;
                top: -1px;
            }
            QTabBar::tab {
                background: #eef2f7;
                border: 1px solid #d7dce5;
                padding: 8px 14px;
                margin-right: 4px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #111827;
            }
            QCheckBox { spacing: 8px; }
            QProgressBar {
                border: 1px solid #d7dce5;
                border-radius: 6px;
                background: #eef2f7;
            }
            QProgressBar::chunk {
                border-radius: 6px;
                background: #60a5fa;
            }
            QScrollArea { border: none; }
            """
        )

    def _update_ollama_gate_state(self, _state=None) -> None:
        # 체크박스 ON이면: 마지막 Gemini JSON 검증(ok=True)일 때만 Ollama 전달 버튼 활성화
        gate_on = False
        try:
            gate_on = self.only_allow_ollama_when_json_ok_chk.isChecked()
        except Exception:
            gate_on = False

        if not hasattr(self, "ollama_btn"):
            return

        if gate_on:
            self.ollama_btn.setEnabled(bool(getattr(self, "_last_gemini_json_ok", False)))
        else:
            self.ollama_btn.setEnabled(True)

    def _ui_log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            self.log_view.appendPlainText(f"[{ts}] {msg}")
        except Exception:
            pass

    def _set_busy(self, busy: bool, phase: str = "", *, determinate: bool = False) -> None:
        for w in [getattr(self, "gemini_btn", None), getattr(self, "ollama_btn", None), getattr(self, "extra_load_btn", None)]:
            if w is not None:
                w.setEnabled(not busy)

        if busy:
            self.status_lbl.setText(phase or "작업 중...")
            self.progress.setVisible(True)
            if determinate:
                self.progress.setRange(0, 100)
                self.progress.setValue(0)
                self.progress.setTextVisible(False)
            else:
                # indeterminate
                self.progress.setRange(0, 0)
        else:
            self.progress.setVisible(False)
            self.progress.setRange(0, 100)
            if phase:
                self.status_lbl.setText(phase)
    def _current_output_dir(self) -> str:
        try:
            return (self.folder_picker.value() or self.cfg.output_dir or '').strip()
        except Exception:
            return (getattr(self.cfg, 'output_dir', '') or '').strip()

    def _set_debug_view_text(self, attr_name: str, text: str) -> None:
        widget = getattr(self, attr_name, None)
        if widget is None:
            return
        try:
            widget.setPlainText(text or '')
        except Exception:
            pass

    def _refresh_debug_views(self) -> None:
        out_dir = self._current_output_dir()
        bundle = load_debug_bundle(out_dir)
        self._set_debug_view_text('debug_summary_view', render_debug_summary_text(bundle))
        self._set_debug_view_text('analysis_view', render_analysis_text(bundle))
        self._set_debug_view_text('plan_view', render_plan_text(bundle))
        self._set_debug_view_text('validation_view', render_validation_text(bundle))
        self._set_debug_view_text('apply_report_view', render_apply_report_text(bundle))

    def on_load_extra_requirements_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "요구사항 파일 선택",
            "",
            "Text Files (*.txt *.md *.json);;All Files (*)",
        )
        if not path:
            return

        ok, content = read_text_file_best_effort(path)
        if not ok:
            QMessageBox.critical(self, "파일 읽기 실패", content)
            return

        existing = self.extra_edit.toPlainText().rstrip()
        merged = (existing + "\n\n" + content.strip() + "\n") if existing else (content.strip() + "\n")
        self.extra_edit.setPlainText(merged)

    def on_gemini_generate(self) -> None:
        self._sync_cfg()
        if not self.cfg.extra_requirements:
            QMessageBox.information(self, "알림", "추가 요구사항을 입력하세요. (또는 파일로 불러오기)")
            return
        if self.cfg.modify_existing_mode:
            out_dir = Path((self.cfg.output_dir or '').strip())
            if not out_dir.exists() or not out_dir.is_dir():
                QMessageBox.warning(self, "수정 모드", "기존 생성물 수정 모드에서는 실제 프로젝트 폴더를 출력 폴더로 선택해야 합니다.")
                return

        analysis_result = None
        backend_plan = None
        jsp_plan = None
        react_plan = None
        vue_plan = None
        nexacro_plan = None
        validation_report = None
        repair_plan = None
        try:
            analysis_obj = build_analysis_from_config(self.cfg)
            analysis_result = analysis_obj.to_dict()
            self._last_analysis_result = analysis_result
            analysis_path = save_analysis_result(analysis_result, self.cfg.output_dir)
            domains = analysis_result.get("domains") or []
            domain_summary = ", ".join(f"{d.get('name')}:{d.get('feature_kind')}" for d in domains[:5]) or "(none)"
            self._ui_log(f"공통 분석 완료: {domain_summary}")
            if analysis_path:
                self._ui_log(f"분석 결과 저장: {analysis_path}")

            backend_plan = build_backend_plan(analysis_result)
            backend_path = save_backend_plan(backend_plan, self.cfg.output_dir)
            backend_domains = backend_plan.get("domains") or []
            backend_summary = ", ".join(
                f"{d.get('domain_name')}:{d.get('controller_mode')}" for d in backend_domains[:5]
            ) or "(none)"
            self._ui_log(f"공통 백엔드 계획 완료: {backend_summary}")
            if backend_path:
                self._ui_log(f"백엔드 계획 저장: {backend_path}")

            if (self.cfg.frontend_key or "").strip().lower() == "jsp":
                jsp_plan = build_jsp_plan(analysis_result, backend_plan)
                jsp_path = save_jsp_plan(jsp_plan, self.cfg.output_dir)
                jsp_domains = jsp_plan.get("domains") or []
                jsp_summary = ", ".join(
                    f"{d.get('domain_name')}:{'/'.join(v.get('artifact_type') for v in (d.get('views') or []))}"
                    for d in jsp_domains[:3]
                ) or "(none)"
                self._ui_log(f"JSP 계획 완료: {jsp_summary}")
                if jsp_path:
                    self._ui_log(f"JSP 계획 저장: {jsp_path}")

            if (self.cfg.frontend_key or "").strip().lower() == "react":
                react_plan = build_react_plan(analysis_result, backend_plan)
                react_path = save_react_plan(react_plan, self.cfg.output_dir)
                react_domains = react_plan.get("domains") or []
                react_summary = ", ".join(
                    f"{d.get('domain_name')}:{'/'.join(a.get('artifact_type') for a in (d.get('artifacts') or []))}"
                    for d in react_domains[:3]
                ) or "(none)"
                self._ui_log(f"React 계획 완료: {react_summary}")
                if react_path:
                    self._ui_log(f"React 계획 저장: {react_path}")

            if (self.cfg.frontend_key or "").strip().lower() == "vue":
                vue_plan = build_vue_plan(analysis_result, backend_plan)
                vue_path = save_vue_plan(vue_plan, self.cfg.output_dir)
                vue_domains = vue_plan.get("domains") or []
                vue_summary = ", ".join(
                    f"{d.get('domain_name')}:{'/'.join(a.get('artifact_type') for a in (d.get('artifacts') or []))}"
                    for d in vue_domains[:3]
                ) or "(none)"
                self._ui_log(f"Vue 계획 완료: {vue_summary}")
                if vue_path:
                    self._ui_log(f"Vue 계획 저장: {vue_path}")

            if (self.cfg.frontend_key or "").strip().lower() == "nexacro":
                nexacro_plan = build_nexacro_plan(analysis_result, backend_plan)
                nexacro_path = save_nexacro_plan(nexacro_plan, self.cfg.output_dir)
                nexacro_domains = nexacro_plan.get("domains") or []
                nexacro_summary = ", ".join(
                    f"{d.get('domain_name')}:{'/'.join(a.get('artifact_type') for a in (d.get('artifacts') or []))}"
                    for d in nexacro_domains[:3]
                ) or "(none)"
                self._ui_log(f"Nexacro 계획 완료: {nexacro_summary}")
                if nexacro_path:
                    self._ui_log(f"Nexacro 계획 저장: {nexacro_path}")

            validation_report = build_validation_report(
                analysis_result,
                backend_plan=backend_plan,
                jsp_plan=jsp_plan,
                react_plan=react_plan,
                vue_plan=vue_plan,
                nexacro_plan=nexacro_plan,
                frontend_key=self.cfg.frontend_key,
            )
            validation_path = save_validation_report(validation_report, self.cfg.output_dir)
            repair_plan = build_auto_repair_plan(validation_report)
            repair_path = save_auto_repair_plan(repair_plan, self.cfg.output_dir)
            summary = validation_report.get("summary") or {}
            self._ui_log(
                f"전역 검증 완료: checks={summary.get('total_checks', 0)}, failed={summary.get('failed_checks', 0)}, errors={summary.get('total_errors', 0)}"
            )
            if validation_path:
                self._ui_log(f"검증 결과 저장: {validation_path}")
            if repair_path:
                self._ui_log(f"복구 계획 저장: {repair_path}")
            self._last_validation_report = validation_report
            self._last_repair_plan = repair_plan
            self._refresh_debug_views()
        except Exception as e:
            self._last_analysis_result = None
            self._last_validation_report = None
            self._last_repair_plan = None
            self._refresh_debug_views()
            self._ui_log(f"공통 분석/백엔드/프론트/검증 계획 실패, 기본 프롬프트로 계속 진행: {e}")

        snapshot_text = ''
        if self.cfg.modify_existing_mode:
            snapshot_text = build_project_snapshot_text(self.cfg.output_dir, self.cfg.target_files_text, self.cfg.extra_requirements, frontend_key=self.cfg.frontend_key)
            if snapshot_text:
                try:
                    debug_dir = Path(self.cfg.output_dir) / '.autopj_debug'
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    (debug_dir / 'current_project_snapshot.txt').write_text(snapshot_text, encoding='utf-8')
                    self._ui_log('현재 프로젝트 스냅샷 저장: ' + str(debug_dir / 'current_project_snapshot.txt'))
                except Exception:
                    pass

        prompt = build_gemini_json_fileops_prompt(
            self.cfg,
            analysis_result=analysis_result,
            backend_plan=backend_plan,
            jsp_plan=jsp_plan,
            react_plan=react_plan,
            vue_plan=vue_plan,
            nexacro_plan=nexacro_plan,
            validation_report=validation_report,
            repair_plan=repair_plan,
            current_project_snapshot=snapshot_text,
        )

        self.gemini_out.setPlainText("Gemini 호출 중... (JSON file-ops 강제)")
        self._ui_log("Gemini 호출 시작")
        self._set_busy(True, "Gemini 호출 중")

        self._gemini_worker = GeminiWorker(prompt)
        self._gemini_worker.log_sig.connect(self._ui_log)
        self._gemini_worker.done_sig.connect(self.on_gemini_done)
        self._gemini_worker.start()

    def on_gemini_done(self, res: GeminiCallResult) -> None:
        self._set_busy(False, "Gemini 완료")
        self._ui_log("Gemini 응답 수신")
        self._set_busy(False)

        if res.ok:
            text = res.text or ""
            #ok, err = validate_plan_json(text, frontend_key=self.cfg.frontend_key)
            try:
                ok, err = validate_plan_json(text, frontend_key=self.cfg.frontend_key)
            except Exception as e:
                ok, err = False, f"validate_plan_json exception: {e!r}"
            self._last_gemini_json_ok = bool(ok)
            self._update_ollama_gate_state()

            if ok:
                self.gemini_out.setPlainText(text)
            else:
                self.gemini_out.setHtml(
                    f'<span style="color:#d32f2f;"><b>Gemini JSON 검증 실패</b>'
                    f'<br>사유: {html.escape(err)}'
                    f'<hr><pre>{html.escape(text)}</pre></span>'
                )
        else:
            self._last_gemini_json_ok = False
            self._update_ollama_gate_state()
            self.gemini_out.setHtml(
                f'<span style="color:#d32f2f;"><b>Gemini ERROR</b><pre>{html.escape(res.error)}</pre></span>'
            )

    def on_ollama_send(self) -> None:
        self._sync_cfg()

        gemini_text = (self.gemini_out.toPlainText() or "").strip()
        if not gemini_text:
            QMessageBox.warning(self, "Ollama", "Gemini 출력이 비어있습니다.")
            return

        # 게이트가 켜져있고 검증 실패 상태면 차단
        if self.only_allow_ollama_when_json_ok_chk.isChecked() and not getattr(self, "_last_gemini_json_ok", False):
            QMessageBox.warning(self, "Ollama", "Gemini JSON 검증 통과 시에만 Ollama 전달이 허용됩니다.")
            return

        out_dir_text = (self.folder_picker.value() or "").strip()
        if not out_dir_text:
            QMessageBox.warning(self, "Ollama", "프로젝트 출력 폴더를 선택하세요.")
            return

        self._ui_log("Ollama 배치(파일별) 시작: Gemini -> (per-file) Ollama")
        self.gemini_out.setPlainText("Ollama 배치 실행 중... (파일별 생성)")
        self._set_busy(True, "Ollama 배치 실행 중", determinate=True)

        # start batch worker
        self._ollama_batch_worker = OllamaBatchWorker(
            self.cfg,
            gemini_text,
            out_dir_text,
            overwrite=self.overwrite_chk.isChecked(),
        )
        self._ollama_batch_worker.log_sig.connect(self._ui_log)
        self._ollama_batch_worker.progress_sig.connect(self._on_ollama_batch_progress)
        self._ollama_batch_worker.done_sig.connect(self._on_ollama_batch_done)
        self._ollama_batch_worker.failed_sig.connect(self._on_ollama_batch_failed)
        self._ollama_batch_worker.start()

    def _on_ollama_batch_progress(self, pct: int, status: str) -> None:
        self.status_lbl.setText(status or "진행중")
        try:
            self.progress.setRange(0, 100)
            self.progress.setValue(max(0, min(100, int(pct))))
        except Exception:
            pass

    def _on_ollama_batch_done(self, payload: dict) -> None:
        self._set_busy(False, "완료")
        self._update_ollama_gate_state()
        report = payload.get("report") if isinstance(payload, dict) else None
        out_dir = payload.get("out_dir") if isinstance(payload, dict) else None
        if report is None:
            self.gemini_out.setPlainText("완료(보고서 없음)")
            return
        self.gemini_out.setPlainText(
            "파일 생성 완료\n"
            + (f"output_dir={out_dir}\n\n" if out_dir else "")
            + json.dumps(report, indent=2, ensure_ascii=False)
        )
        self._refresh_debug_views()

    def _on_ollama_batch_failed(self, err: str) -> None:
        self._set_busy(False, "실패")
        self._update_ollama_gate_state()
        self.gemini_out.setPlainText("Ollama ERROR\n" + (err or ""))
        self._refresh_debug_views()
    def on_ollama_chunk(self, piece: str) -> None:
        if not hasattr(self, "_ollama_stream_buf"):
            self._ollama_stream_buf = ""
        self._ollama_stream_buf += (piece or "")
        if len(self._ollama_stream_buf) > 50000:
            self._ollama_stream_buf = self._ollama_stream_buf[-50000:]
        self.status_lbl.setText("Ollama 수신중...")
        tail = self._ollama_stream_buf[-5000:]
        self.gemini_out.setPlainText(tail)

    def on_ollama_done(self, res: OllamaCallResult) -> None:
        self._set_busy(False, "Ollama 완료")
        self._ui_log("Ollama 응답 수신")
        self._update_ollama_gate_state()

        if not getattr(res, "ok", False):
            self.gemini_out.setPlainText("Ollama ERROR\n" + (res.error or ""))
            self.ollama_btn.setEnabled(True)
            return

        raw = (res.text or "").strip()
        extracted = extract_json_array_text(raw)

        try:
            file_ops = json.loads(extracted)
            if not isinstance(file_ops, list):
                raise ValueError("JSON root must be list")

            # Ollama도 동일 검증 적용(최소 path 주석/경로규칙/프론트 폴더)
            ok, err = validate_plan_json(extracted, frontend_key=self.cfg.frontend_key)
            if not ok:
                raise ValueError(f"JSON validation failed: {err}")

            out_dir = Path((self.folder_picker.value() or "").strip())
            out_dir.mkdir(parents=True, exist_ok=True)

            # eGovFrame 생성물은 execution_core 적용 경로를 항상 거쳐서 backend/JSP 보정을 수행한다.
            if _should_use_execution_core_apply(self.cfg):
                report = apply_file_ops_with_execution_core(
                    file_ops, out_dir, self.cfg, overwrite=self.overwrite_chk.isChecked()
                )
            else:
                report = apply_file_ops(file_ops, out_dir, overwrite=self.overwrite_chk.isChecked())
            report_path = out_dir / "apply_report.json"
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

            self.gemini_out.setPlainText(
                "Ollama 파일 생성 완료\n" + json.dumps(report, indent=2, ensure_ascii=False)
            )
            self._refresh_debug_views()
        except Exception as e:
            self.gemini_out.setPlainText(
                "Ollama JSON 파싱 실패\n"
                + str(e)
                + "\n\n[RAW]\n"
                + raw
                + "\n\n[EXTRACTED]\n"
                + extracted
            )
        finally:
            self._update_ollama_gate_state()

    def _bind_events(self) -> None:
        self.project_name_edit.textChanged.connect(self._sync_db_name_default)
        self.backend_combo.currentIndexChanged.connect(lambda _: self._sync_cfg())
        self.frontend_combo.currentIndexChanged.connect(lambda _: self._sync_cfg())
        self.engine_combo.currentIndexChanged.connect(lambda _: self._sync_cfg())
        self.design_style_combo.currentIndexChanged.connect(lambda _: self._on_design_style_changed())
        self.design_url_edit.textChanged.connect(lambda _: self._sync_cfg())
        self.db_combo.currentIndexChanged.connect(lambda _: self._sync_cfg())
        self.db_name_edit.textChanged.connect(lambda _: self._sync_cfg())
        self.db_login_edit.textChanged.connect(lambda _: self._sync_cfg())
        self.db_pw_edit.textChanged.connect(lambda _: self._sync_cfg())
        self.folder_picker.changed.connect(lambda _: self._sync_cfg())
        self.folder_picker.changed.connect(lambda _: self._refresh_debug_views())
        self.overwrite_chk.stateChanged.connect(lambda _: self._sync_cfg())
        self.modify_existing_chk.stateChanged.connect(lambda _: self._sync_cfg())
        self.extra_edit.textChanged.connect(lambda: self._sync_cfg())
        self.target_files_edit.textChanged.connect(lambda: self._sync_cfg())

    def _apply_defaults(self) -> None:
        self.backend_combo.setCurrentIndex(self._backend_map.get(self.cfg.backend_key, 0))
        self.frontend_combo.setCurrentIndex(self._frontend_map.get(self.cfg.frontend_key, 0))
        self.engine_combo.setCurrentIndex(self._engine_map.get(self.cfg.code_engine_key, 0))
        self.design_style_combo.setCurrentIndex(self._design_map.get(normalize_style_key(self.cfg.design_style_key), 0))
        self._update_design_style_desc()
        self.db_combo.setCurrentIndex(self._db_map.get(self.cfg.database_key, 0))
        self.overwrite_chk.setChecked(self.cfg.overwrite)

    def _sync_db_name_default(self) -> None:
        if self.db_name_edit.text().strip():
            return
        pn = self.project_name_edit.text().strip()
        if pn:
            self.db_name_edit.setText(pn)

    def _sync_cfg(self) -> None:
        self.cfg.project_name = self.project_name_edit.text()
        self.cfg.backend_key = self.backend_combo.currentData() or "egov_spring"
        self.cfg.backend_label = self.backend_combo.currentText() or "전자정부프레임워크 (Spring Boot)"
        self.cfg.frontend_key = self.frontend_combo.currentData() or "jsp"
        self.cfg.frontend_label = self.frontend_combo.currentText() or "jsp"
        self.cfg.code_engine_key = self.engine_combo.currentData() or "ollama"
        self.cfg.code_engine_label = self.engine_combo.currentText() or "Ollama"
        self.cfg.design_style_key = normalize_style_key(self.design_style_combo.currentData() or "simple")
        self.cfg.design_style_label = self.design_style_combo.currentText() or "심플"
        self.cfg.design_url = self.design_url_edit.text()
        self.cfg.database_key = self.db_combo.currentData() or "sqlite"
        self.cfg.database_label = self.db_combo.currentText() or "SQLite"
        self.cfg.db_name = self.db_name_edit.text()
        self.cfg.db_login_id = self.db_login_edit.text()
        self.cfg.db_password = self.db_pw_edit.text()
        self.cfg.output_dir = self.folder_picker.value()
        self.cfg.overwrite = self.overwrite_chk.isChecked()
        self.cfg.modify_existing_mode = self.modify_existing_chk.isChecked()
        self.cfg.extra_requirements = self.extra_edit.toPlainText()
        self.cfg.target_files_text = self.target_files_edit.toPlainText()
        self.cfg.normalize()

    def _update_design_style_desc(self) -> None:
        key = normalize_style_key(self.design_style_combo.currentData() or "simple")
        self.design_style_desc.setText(build_design_style_hint(key))

    def _on_design_style_changed(self) -> None:
        self._update_design_style_desc()
        self._sync_cfg()

    def _on_print(self) -> None:
        self._sync_cfg()
        msg = (
            f"project_name={self.cfg.project_name}\n"
            f"backend={self.cfg.backend_label}\n"
            f"frontend={self.cfg.frontend_label}\n"
            f"code_engine={self.cfg.code_engine_label}\n"
            f"design_style={self.cfg.design_style_label}\n"
            f"design_url={self.cfg.design_url}\n"
            f"db={self.cfg.database_label}\n"
            f"db_name={self.cfg.db_name}\n"
            f"db_login={self.cfg.db_login_id}\n"
            f"output_dir={self.cfg.output_dir}\n"
            f"overwrite={self.cfg.overwrite}\n"
            f"modify_existing_mode={self.cfg.modify_existing_mode}\n"
            f"target_files={self.cfg.target_files_text}\n"
        )
        QMessageBox.information(self, "현재 설정", msg)
