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
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QStandardPaths
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
from app.ui.state import ProjectConfig
from app.ui.widgets.section_box import make_section
from app.ui.widgets.path_picker import FolderPicker
from app.ui.file_loader import read_text_file_best_effort
from app.ui.gemini_client import call_gemini, GeminiCallResult
from app.ui.ollama_client import call_ollama, OllamaCallResult
from app.ui.json_extract import extract_json_array_text, extract_json_object_or_array_text, maybe_extract_valid_json_text
from app.io.file_writer import apply_file_ops
from app.io.execution_core_apply import apply_file_ops_with_execution_core, _REACT_RUNTIME_BASELINE, _VUE_RUNTIME_BASELINE
from app.ui.prompt_templates import build_gemini_json_fileops_prompt
from app.ui.analysis_bridge import build_analysis_from_config, save_analysis_result
from app.ui.backend_bridge import build_backend_plan, save_backend_plan
from app.ui.jsp_bridge import build_jsp_plan, save_jsp_plan
from app.ui.react_bridge import build_react_plan, save_react_plan
from app.ui.vue_bridge import build_vue_plan, save_vue_plan
from app.ui.nexacro_bridge import build_nexacro_plan, save_nexacro_plan
from app.ui.validation_bridge import build_validation_report, save_validation_report, build_auto_repair_plan, save_auto_repair_plan
from app.ui.debug_artifacts import load_debug_bundle, render_debug_summary_text, render_analysis_text, render_plan_text, render_validation_text, render_apply_report_text
from app.validation import build_targeted_regen_prompt, validate_and_repair_generated_files
from app.ui.template_generator import template_file_ops
from app.ui.apply_strategy import should_use_execution_core_apply
from app.ui.builtin_shortcuts import builtin_shortcut_content
from app.ui.json_validator import validate_file_ops_json, validate_plan_json
from app.ui.generated_content_validator import validate_generated_content
from app.ui.ui_sanitize_common import repair_invalid_generated_content
from app.ui.fallback_builder import build_builtin_fallback_content
from app.validation.compile_error_parser import summarize_compile_errors
from app.ui.runtime_fallbacks import build_frontend_runtime_fallback
from app.ui.post_validation_logging import post_validation_diagnostic_lines, post_validation_failure_message
from app.ui.project_registry import (
    clear_registry,
    get_registered_project,
    list_registered_projects,
    project_display_label,
    register_project,
    registry_summary,
    remove_registered_project,
    validate_registered_project,
)
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
        idx_map[opt.key] = i
    return idx_map
def _post_validation_failure_message(post_validation: dict) -> str:
    runtime = post_validation.get("runtime_validation") or {}
    compile_info = runtime.get("compile") or {}
    startup_info = runtime.get("startup") or {}
    smoke_info = runtime.get("endpoint_smoke") or {}
    compile_status = compile_info.get("status", "unknown")
    startup_status = startup_info.get("status", "unknown")
    smoke_status = smoke_info.get("status", "unknown")
    remaining = int(post_validation.get("remaining_invalid_count", 0) or 0)
    reasons = []
    for item in (post_validation.get("remaining_invalid_files") or [])[:5]:
        reason = (item.get("reason") or "validation failed").strip()
        path = (item.get("path") or "").strip()
        reasons.append(f"{path}: {reason}" if path else reason)
    compile_lines = summarize_compile_errors(compile_info.get("errors") or [], limit=3)
    if compile_lines:
        reasons.extend(compile_lines)
    tail = "; ".join(reasons)
    return (
        f"generated project validation failed (remaining_invalid={remaining}, "
        f"compile={compile_status}, startup={startup_status}, endpoint_smoke={smoke_status})"
        + (f": {tail}" if tail else "")
    )
def _post_validation_diagnostic_lines(post_validation: dict) -> list[str]:
    lines: list[str] = []
    delta = post_validation.get("invalid_delta") or {}
    added = list(delta.get("added") or [])
    removed = list(delta.get("removed") or [])
    if delta:
        lines.append(
            f"[POST-VALIDATION-DELTA] added={int(delta.get('added_count', 0) or 0)}, removed={int(delta.get('removed_count', 0) or 0)}, grew={'yes' if delta.get('grew') else 'no'}"
        )
        for item in added[:3]:
            reason = (item.get("reason") or "validation failed").strip()
            path = (item.get("path") or "").strip()
            lines.append(f"[POST-VALIDATION-DELTA] added {path}: {reason}" if path else f"[POST-VALIDATION-DELTA] added {reason}")
        for item in removed[:2]:
            reason = (item.get("reason") or "validation failed").strip()
            path = (item.get("path") or "").strip()
            lines.append(f"[POST-VALIDATION-DELTA] removed {path}: {reason}" if path else f"[POST-VALIDATION-DELTA] removed {reason}")
    unresolved = list(post_validation.get("unresolved_initial_invalid") or [])
    if unresolved:
        lines.append(f"[POST-VALIDATION-UNRESOLVED] count={len(unresolved)}")
        for item in unresolved[:3]:
            reason = (item.get("reason") or "validation failed").strip()
            path = (item.get("path") or "").strip()
            lines.append(f"[POST-VALIDATION-UNRESOLVED] {path}: {reason}" if path else f"[POST-VALIDATION-UNRESOLVED] {reason}")
    compile_rounds = list(post_validation.get("compile_repair_rounds") or [])
    for round_info in compile_rounds:
        round_no = int(round_info.get("round", 0) or 0)
        before = round_info.get("before") or {}
        after = round_info.get("after") or {}
        lines.append(
            f"[COMPILE-REPAIR] round={round_no}, targets={len(round_info.get('targets') or [])}, changed={len(round_info.get('changed') or [])}, skipped={len(round_info.get('skipped') or [])}"
        )
        if before or after:
            lines.append(
                f"[COMPILE-RETRY-{round_no}] before compile={before.get('compile_status', 'unknown')}, startup={before.get('startup_status', 'unknown')}, endpoint_smoke={before.get('endpoint_smoke_status', 'unknown')} -> after compile={after.get('compile_status', 'unknown')}, startup={after.get('startup_status', 'unknown')}, endpoint_smoke={after.get('endpoint_smoke_status', 'unknown')}"
            )
        if round_info.get("terminal_failure"):
            lines.append(f"[COMPILE-RETRY-{round_no}] terminal={round_info.get('terminal_failure')}")
        for line in (after.get("compile_errors") or [])[:3]:
            lines.append(f"[COMPILE-RETRY-{round_no}] {line}")
    if not compile_rounds:
        compile_repair = post_validation.get("compile_repair") or {}
        if compile_repair.get("attempted"):
            lines.append(
                f"[COMPILE-REPAIR] targets={len(compile_repair.get('targets') or [])}, changed={len(compile_repair.get('changed') or [])}, skipped={len(compile_repair.get('skipped') or [])}"
            )
    smoke_rounds = list(post_validation.get("smoke_repair_rounds") or [])
    for round_info in smoke_rounds:
        round_no = int(round_info.get("round", 0) or 0)
        before = round_info.get("before") or {}
        after = round_info.get("after") or {}
        lines.append(
            f"[SMOKE-REPAIR] round={round_no}, targets={len(round_info.get('targets') or [])}, changed={len(round_info.get('changed') or [])}, skipped={len(round_info.get('skipped') or [])}"
        )
        if before or after:
            lines.append(
                f"[SMOKE-RETRY-{round_no}] before compile={before.get('compile_status', 'unknown')}, startup={before.get('startup_status', 'unknown')}, endpoint_smoke={before.get('endpoint_smoke_status', 'unknown')} -> after compile={after.get('compile_status', 'unknown')}, startup={after.get('startup_status', 'unknown')}, endpoint_smoke={after.get('endpoint_smoke_status', 'unknown')}"
            )
        if round_info.get("terminal_failure"):
            lines.append(f"[SMOKE-RETRY-{round_no}] terminal={round_info.get('terminal_failure')}")
        for line in (after.get("compile_errors") or [])[:3]:
            lines.append(f"[SMOKE-RETRY-{round_no}] {line}")
    if not smoke_rounds:
        smoke_repair = post_validation.get("smoke_repair") or {}
        if smoke_repair.get("attempted"):
            lines.append(
                f"[SMOKE-REPAIR] targets={len(smoke_repair.get('targets') or [])}, changed={len(smoke_repair.get('changed') or [])}, skipped={len(smoke_repair.get('skipped') or [])}"
            )
    return lines
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
        p = (path or "").strip()
        m = re.fullmatch(r"<path>\s*([\s\S]*?)\s*</path>", p, re.IGNORECASE)
        if m:
            p = (m.group(1) or "").strip()
        p = p.replace("\\", "/").lstrip("./")
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
        return p
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
    def _auth_root_path(self, path: str) -> str:
        p = self._normalize_target_path(path).replace('\\', '/')
        anchor = 'src/main/java/'
        if anchor in p:
            rest = p.split(anchor, 1)[1]
            parts = [part for part in rest.split('/') if part]
            if len(parts) >= 2:
                return '/'.join(parts[:2])
        project_name = re.sub(r"[^A-Za-z0-9_]+", "", (self.cfg.project_name or "").strip()) or "app"
        project_seg = project_name[:1].lower() + project_name[1:]
        return f"egovframework/{project_seg}"
    def _canonicalize_auth_target_path(self, path: str) -> str:
        p = self._normalize_target_path(path).replace('\\', '/')
        name = Path(p).name
        java_map = {
            'LoginController.java': 'login/web/LoginController.java',
            'LoginService.java': 'login/service/LoginService.java',
            'LoginServiceImpl.java': 'login/service/impl/LoginServiceImpl.java',
            'LoginVO.java': 'login/service/vo/LoginVO.java',
            'LoginDAO.java': 'login/service/impl/LoginDAO.java',
            'LoginMapper.java': 'login/service/mapper/LoginMapper.java',
            'IntegratedAuthService.java': 'login/service/IntegratedAuthService.java',
            'IntegratedAuthServiceImpl.java': 'login/service/impl/IntegratedAuthServiceImpl.java',
            'CertLoginService.java': 'login/service/CertLoginService.java',
            'CertLoginServiceImpl.java': 'login/service/impl/CertLoginServiceImpl.java',
            'CertLoginController.java': 'login/web/CertLoginController.java',
            'JwtLoginController.java': 'login/web/JwtLoginController.java',
            'JwtTokenProvider.java': 'config/JwtTokenProvider.java',
            'AuthLoginInterceptor.java': 'config/AuthLoginInterceptor.java',
            'AuthenticInterceptor.java': 'config/AuthLoginInterceptor.java',
            'AuthInterceptor.java': 'config/AuthLoginInterceptor.java',
            'WebConfig.java': 'config/WebMvcConfig.java',
            'WebMvcConfig.java': 'config/WebMvcConfig.java',
            'LoginDatabaseInitializer.java': 'config/LoginDatabaseInitializer.java',
        }
        jsp_map = {
            'login.jsp': 'src/main/webapp/WEB-INF/views/login/login.jsp',
            'main.jsp': 'src/main/webapp/WEB-INF/views/login/main.jsp',
            'integrationGuide.jsp': 'src/main/webapp/WEB-INF/views/login/integrationGuide.jsp',
            'certLogin.jsp': 'src/main/webapp/WEB-INF/views/login/certLogin.jsp',
            'jwtLogin.jsp': 'src/main/webapp/WEB-INF/views/login/jwtLogin.jsp',
        }
        if name in jsp_map:
            return jsp_map[name]
        if name in java_map:
            return f"src/main/java/{self._auth_root_path(p)}/{java_map[name]}"
        return p
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
        p = self._canonicalize_auth_target_path(path)
        body = content or ""
        name = Path(p).name
        auth_helper_names = {
            'LoginController.java', 'LoginService.java', 'LoginServiceImpl.java', 'LoginVO.java', 'LoginDAO.java', 'LoginMapper.java',
            'IntegratedAuthService.java', 'IntegratedAuthServiceImpl.java', 'CertLoginService.java', 'CertLoginServiceImpl.java',
            'CertLoginController.java', 'JwtLoginController.java', 'JwtTokenProvider.java', 'AuthLoginInterceptor.java', 'AuthenticInterceptor.java', 'AuthInterceptor.java', 'WebConfig.java', 'WebMvcConfig.java', 'LoginDatabaseInitializer.java',
            'login.jsp', 'main.jsp', 'integrationGuide.jsp', 'certLogin.jsp', 'jwtLogin.jsp'
        }
        entity = 'Login' if name in auth_helper_names else self._entity_from_target_path(p)
        if classify_feature_kind(entity) != FEATURE_KIND_AUTH and name not in auth_helper_names:
            return body
        logical = self._logical_builtin_path(p)
        if not logical:
            return body
        module_base = self._module_base_from_target_path(p)
        if not module_base:
            return body
        lower = body.lower()
        expected_type = Path(p).stem
        type_mismatch = bool(re.search(rf"public\s+(?:class|interface|enum)\s+(?!{re.escape(expected_type)}\b)[A-Za-z_][A-Za-z0-9_]*", body))
        needs_rebuild = type_mismatch
        if name.endswith("ServiceImpl.java"):
            needs_rebuild = needs_rebuild or (
                bool(re.search(r"public\s+void\s+(authenticate|login)\s*\(", body))
                or " ma.glasnost.orika" in lower
                or "map<string" in lower
            )
        elif name.endswith("Service.java"):
            needs_rebuild = needs_rebuild or (
                " map<" in lower
                or bool(re.search(r"\bvoid\s+(authenticate|login)\s*\(", body))
                or (name == 'LoginService.java' and "authenticate(" not in body)
            )
        elif name.endswith("Mapper.java"):
            needs_rebuild = needs_rebuild or (
                "ma.glasnost.orika" in lower
                or "interface" not in body
                or "org.apache.ibatis.annotations.mapper" not in lower
            )
        elif name.endswith("Controller.java"):
            needs_rebuild = needs_rebuild or (
                "httpsession" not in lower
                or (name == 'LoginController.java' and "authenticate(" not in body)
            )
        elif name.endswith("Mapper.xml"):
            needs_rebuild = needs_rebuild or (
                "<beans" in lower
                or "<sqlmap" in lower
                or "<mapper" not in lower
                or "id=\"authenticate\"" not in lower
            )
        if name in auth_helper_names and not body.strip():
            needs_rebuild = True
        if not needs_rebuild:
            return body
        schema = schema_for(
            'Login',
            feature_kind=FEATURE_KIND_AUTH,
            unified_auth=bool(getattr(self.cfg, 'auth_unified_auth', False) or name in {'IntegratedAuthService.java', 'IntegratedAuthServiceImpl.java', 'integrationGuide.jsp'}),
            cert_login=bool(getattr(self.cfg, 'auth_cert_login', False) or name in {'CertLoginService.java', 'CertLoginServiceImpl.java', 'CertLoginController.java', 'certLogin.jsp'}),
            jwt_login=bool(getattr(self.cfg, 'auth_jwt_login', False) or name in {'JwtLoginController.java', 'JwtTokenProvider.java', 'jwtLogin.jsp'}),
        )
        rebuilt = builtin_file(logical, module_base, schema)
        return rebuilt or body
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
    def _validate_generated_content(self, path: str, content: str) -> Tuple[bool, str]:
        return validate_generated_content(path, content, frontend_key=getattr(self.cfg, "frontend_key", ""))
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
        expected_path = self._canonicalize_auth_target_path(expected_path)
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
        expected_path = self._canonicalize_auth_target_path(expected_path)
        content = cleaned
        # [수정] JSON 파일은 모델이 설명 문구를 섞어도 첫 valid JSON object/array를 최대한 추출한다.
        if self._ext_of(expected_path) == ".json":
            content = maybe_extract_valid_json_text(cleaned)
        content = self._ensure_path_comment(expected_path, content)
        content = self._repair_auth_generated_content(expected_path, content)
        if content.strip() == "..." or any(line.strip() == "..." for line in content.splitlines()[:10]):
            raise ValueError("content contains placeholder '...'")
        return {"path": expected_path, "purpose": purpose or "generated", "content": content}
    def _build_single_file_content_prompt(self, path: str, purpose: str, spec: str) -> str:
        backend = self.cfg.backend_label
        frontend = self.cfg.frontend_label
        db = self.cfg.database_label
        style = self.cfg.design_style_label
        design_url = self.cfg.design_url
        path = self._normalize_target_path(path)
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
        hard_rules = f"""[HARD RULES]
1) Output ONLY the file content. No JSON. No explanation. No markdown. No code fences.
2) Do NOT output any path comment such as // path:, <!-- path:, # path:, -- path:.
3) Generate ONLY this one file for the exact path: {path}
"""
        return (
            "You are an expert eGovFrame(Spring Boot) code generator.\n\n"
            + "[TARGET CONTEXT]\n"
            + f"- Backend: {backend}\n- Frontend: {frontend}\n- Database: {db}\n- DesignStyle: {style}\n"
            + (f"- DesignURL: {design_url}\n" if design_url else "")
            + "\n"
            + hard_rules
            + java_extra
            + sql_extra
            + "\n[FILE SPEC FROM GEMINI]\n"
            + (spec or "")
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
    def _regenerate_file_op_once(self, path: str, purpose: str, spec: str, reason: str) -> dict | None:
        raw = self._regenerate_file_once(path, purpose, spec, reason)
        one = self._one_from_model_text(raw, path, purpose)
        okc, errc = self._validate_generated_content(path, one.get("content", ""))
        if not okc:
            self._log(f"[POST-VALIDATION] regenerate invalid for {path}: {errc}")
            return None
        return one
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
        elif p.endswith(".java"):
            num_predict = _env_int("AI_PG_OLLAMA_NUM_PREDICT_JAVA", 8000)
        elif p.endswith(".jsp"):
            num_predict = _env_int("AI_PG_OLLAMA_NUM_PREDICT_JSP", 6000)
        elif p.endswith(".xml"):
            num_predict = _env_int("AI_PG_OLLAMA_NUM_PREDICT_XML", 6000)
        else:
            num_predict = _env_int("AI_PG_OLLAMA_NUM_PREDICT_OTHER", 5000)
        return {
            "num_predict": max(200, int(num_predict)),
            "temperature": float(os.getenv("AI_PG_OLLAMA_TEMPERATURE", "0.2")),
            "top_p": float(os.getenv("AI_PG_OLLAMA_TOP_P", "0.9")),
        }
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
            self._log(f"[BATCH] tasks(after filtering)={len(tasks)}, templates={len(tpl_ops)}")
            total = len(tasks)
            if total == 0:
                self._log("[BATCH] No tasks from Gemini (after template filtering)")
            else:
                self._log("[BATCH] Ollama warmup/restart")
                _ = call_ollama(
                    "Return a JSON object only: {\"ok\": true}",
                    restart_if_running=False,
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
                    one = {"path": path, "purpose": purpose, "content": shortcut_content}
                    okc, errc = self._validate_generated_content(path, one.get("content", ""))
                    if not okc:
                        raise RuntimeError(f"builtin shortcut invalid for {path}: {errc}")
                    self._log(f"[FILE {idx}/{total}] validating json")
                    ok, err = validate_file_ops_json(json.dumps([one], ensure_ascii=False), frontend_key=self.cfg.frontend_key)
                    if not ok:
                        raise RuntimeError(f"validation failed for {path}: {err}")
                    results.append(one)
                    self._log(f"[FILE {idx}/{total}] queued for write")
                    self._log(f"[FILE {idx}/{total}] ok: {path}")
                    continue
                prompt = self._build_single_file_content_prompt(path, purpose, spec)
                self._log(f"[FILE {idx}/{total}] prompt ready")
                _chars = [0]
                _received = [False]
                _last_chunk_at = [time.time()]
                _stop_watch = threading.Event()
                def _watch_progress() -> None:
                    prev_chars = 0
                    while not _stop_watch.wait(15.0):
                        total_chars = _chars[0]
                        delta_chars = total_chars - prev_chars
                        idle_s = int(max(0.0, time.time() - _last_chunk_at[0]))
                        if not _received[0]:
                            self._log(f"[FILE {idx}/{total}] waiting first response... idle={idle_s}s")
                        elif delta_chars > 0:
                            self._log(f"[FILE {idx}/{total}] receiving... chars={total_chars} (+{delta_chars}/15s)")
                        else:
                            self._log(f"[FILE {idx}/{total}] stalled? chars={total_chars} idle={idle_s}s")
                        prev_chars = total_chars
                def _on_chunk(piece: str) -> None:
                    if piece:
                        _chars[0] += len(piece)
                        _last_chunk_at[0] = time.time()
                        if not _received[0]:
                            self._log(f"[FILE {idx}/{total}] response started")
                            _received[0] = True
                watcher = threading.Thread(target=_watch_progress, daemon=True)
                watcher.start()
                self._log(f"[FILE {idx}/{total}] ollama request")
                try:
                    res = call_ollama(
                        prompt,
                        on_chunk=_on_chunk,
                        restart_if_running=False,
                        options=self._ollama_options_for_path(path),
                        response_format=None,
                    )
                finally:
                    _stop_watch.set()
                    watcher.join(timeout=0.2)
                if not getattr(res, "ok", False):
                    raise RuntimeError(f"Ollama failed for {path}: {res.error}")
                self._log(f"[FILE {idx}/{total}] response complete chars={_chars[0]}")
                raw = (res.text or "").strip()
                one = self._one_from_model_text(raw, path, purpose)
                self._log(f"[FILE {idx}/{total}] validating content")
                okc, errc = self._validate_generated_content(path, one.get("content", ""))
                if not okc:
                    repaired_content, repaired, repair_ok, repair_err = repair_invalid_generated_content(
                        path, one.get("content", ""), errc, frontend_key=self.cfg.frontend_key
                    )
                    if repaired and repair_ok:
                        self._log(f"[FILE {idx}/{total}] in-memory sanitize applied before regenerate: {path}")
                        one = {"path": path, "purpose": purpose, "content": repaired_content}
                        okc = True
                    else:
                        self._log(f"[FILE {idx}/{total}] content invalid, regenerating: {errc}")
                        self._save_debug_text(f"decoded_{idx:02d}of{total:02d}_{Path(path).name}.txt", one.get("content", ""))
                        self._log(f"[FILE {idx}/{total}] regenerate request")
                        regen_raw = self._regenerate_file_once(path, purpose, spec, errc)
                        self._save_debug_text(f"regen_raw_{idx:02d}of{total:02d}_{Path(path).name}.txt", regen_raw)
                        self._log(f"[FILE {idx}/{total}] re-validating content")
                        one = self._one_from_model_text(regen_raw, path, purpose)
                        okc2, errc2 = self._validate_generated_content(path, one.get("content", ""))
                        if not okc2:
                            repaired_regen, regen_repaired, regen_ok, regen_err = repair_invalid_generated_content(
                                path, one.get("content", ""), errc2, frontend_key=self.cfg.frontend_key
                            )
                            if regen_repaired and regen_ok:
                                self._log(f"[FILE {idx}/{total}] in-memory sanitize applied after regenerate: {path}")
                                one = {"path": path, "purpose": purpose, "content": repaired_regen}
                            else:
                                fallback_content = build_builtin_fallback_content(path, spec, project_name=self.cfg.project_name or "")
                                if not fallback_content:
                                    fallback_content = build_builtin_fallback_content(path, spec, project_name=self.cfg.project_name)
                                if not fallback_content and (self.cfg.frontend_key or "").strip().lower() == "react":
                                    fallback_content = self._react_runtime_fallback_content(path)
                                if not fallback_content:
                                    fallback_content = build_frontend_runtime_fallback(path, self.cfg.frontend_key, spec=spec, project_name=self.cfg.project_name)
                                if fallback_content:
                                    okf, errf = self._validate_generated_content(path, fallback_content)
                                    if not okf:
                                        repaired_fallback, fallback_repaired, fallback_ok, fallback_err = repair_invalid_generated_content(
                                            path, fallback_content, errf, frontend_key=self.cfg.frontend_key
                                        )
                                        if fallback_repaired and fallback_ok:
                                            fallback_content = repaired_fallback
                                            okf, errf = True, ''
                                        elif fallback_repaired and not fallback_ok:
                                            errf = fallback_err
                                    if okf:
                                        self._log(f"[FILE {idx}/{total}] runtime baseline fallback applied: {path}")
                                        one = {"path": path, "purpose": purpose, "content": fallback_content}
                                    else:
                                        raise RuntimeError(f"content still invalid after regenerate: {errc2}; fallback invalid: {errf}")
                                else:
                                    raise RuntimeError(f"content still invalid after regenerate: {errc2}")
                self._log(f"[FILE {idx}/{total}] validating json")
                ok, err = validate_file_ops_json(json.dumps([one], ensure_ascii=False), frontend_key=self.cfg.frontend_key)
                if not ok:
                    raise RuntimeError(f"validation failed for {path}: {err}")
                results.append(one)
                self._log(f"[FILE {idx}/{total}] queued for write")
                self._log(f"[FILE {idx}/{total}] ok: {path}")
            final_ops = list(tpl_ops) + results
            self._progress(92, "Writing files")
            if _should_use_execution_core_apply(self.cfg):
                report = apply_file_ops_with_execution_core(final_ops, out_dir, self.cfg, overwrite=self.overwrite)
            else:
                report = apply_file_ops(final_ops, out_dir, overwrite=self.overwrite)
            (out_dir / "apply_report.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            try:
                self._progress(96, "Validating generated files")
                post_validation = validate_and_repair_generated_files(
                    project_root=out_dir,
                    cfg=self.cfg,
                    report=report,
                    file_ops=final_ops,
                    regenerate_callback=self._regenerate_file_op_once,
                    use_execution_core=_should_use_execution_core_apply(self.cfg),
                    max_regen_attempts=1,
                )
                report.setdefault("patched", {})["post_generation_validation"] = post_validation
                (out_dir / "apply_report.json").write_text(
                    json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                runtime_info = post_validation.get("runtime_validation") or {}
                self._log(
                    f"[POST-VALIDATION] files={post_validation.get('generated_file_count', 0)}, initial_invalid={post_validation.get('initial_invalid_count', 0)}, remaining_invalid={post_validation.get('remaining_invalid_count', 0)}, compile={(runtime_info.get('compile') or {}).get('status', 'unknown')}, startup={(runtime_info.get('startup') or {}).get('status', 'unknown')}, endpoint_smoke={(runtime_info.get('endpoint_smoke') or {}).get('status', 'unknown')}"
                )
                compile_info = (runtime_info.get('compile') or {})
                compile_errors = compile_info.get('errors') or []
                if compile_errors:
                    self._log(f"[COMPILE] command={compile_info.get('command') or '-'}")
                    for line in summarize_compile_errors(compile_errors, limit=5):
                        self._log(f"[COMPILE] {line}")
                for line in post_validation_diagnostic_lines(post_validation):
                    self._log(line)
                if not post_validation.get("ok", False):
                    raise RuntimeError(post_validation_failure_message(post_validation))
            except Exception as post_e:
                import traceback
                post_tb = traceback.format_exc()
                report.setdefault("errors", []).append({"path": ".autopj_debug/post_generation_validation.json", "reason": f"post_generation_validation_failed: {post_e}"})
                try:
                    (out_dir / "apply_report.json").write_text(
                        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
                    )
                except Exception:
                    pass
                self._log("[POST-VALIDATION] FAILED\n" + post_tb)
                raise
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
        self._form_state_version: int = 1
        self._saved_projects_cache: list[dict] = []
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
        basic_layout.addWidget(QLabel("작업 모드"), 3, 0)
        self.operation_mode_combo = QComboBox()
        self.operation_mode_combo.addItem("신규 생성", "create")
        self.operation_mode_combo.addItem("기존 프로젝트 수정", "modify")
        basic_layout.addWidget(self.operation_mode_combo, 3, 1, 1, 1)
        self.operation_mode_lbl = QLabel()
        self.operation_mode_lbl.setWordWrap(True)
        self.operation_mode_lbl.setStyleSheet("padding:8px 10px; border:1px solid #dbe4f0; border-radius:10px; background:#f8fbff; color:#334155;")
        basic_layout.addWidget(self.operation_mode_lbl, 4, 0, 1, 4)
        self.saved_projects_title_lbl = QLabel("저장된 autopj 프로젝트")
        basic_layout.addWidget(self.saved_projects_title_lbl, 5, 0)
        saved_projects_row = QHBoxLayout()
        saved_projects_row.setSpacing(8)
        self.saved_projects_combo = QComboBox()
        self.saved_projects_combo.setMinimumContentsLength(40)
        self.saved_projects_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        saved_projects_row.addWidget(self.saved_projects_combo, 1)
        self.refresh_saved_projects_btn = QPushButton("목록 새로고침")
        saved_projects_row.addWidget(self.refresh_saved_projects_btn, 0)
        self.clear_saved_project_selection_btn = QPushButton("선택 초기화")
        saved_projects_row.addWidget(self.clear_saved_project_selection_btn, 0)
        self.reset_saved_projects_btn = QPushButton("저장 목록 초기화")
        saved_projects_row.addWidget(self.reset_saved_projects_btn, 0)
        basic_layout.addLayout(saved_projects_row, 5, 1, 1, 3)
        self.saved_projects_hint_lbl = QLabel()
        self.saved_projects_hint_lbl.setWordWrap(True)
        self.saved_projects_hint_lbl.setStyleSheet("padding:8px 10px; border:1px solid #dbe4f0; border-radius:10px; background:#f8fbff; color:#334155;")
        basic_layout.addWidget(self.saved_projects_hint_lbl, 6, 0, 1, 4)
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
        self.frontend_branch_lbl = QLabel()
        self.frontend_branch_lbl.setWordWrap(True)
        self.frontend_branch_lbl.setStyleSheet("padding:8px 10px; border:1px solid #dbe4f0; border-radius:10px; background:#f8fbff; color:#334155;")
        stack_layout.addWidget(self.frontend_branch_lbl, 1, 0, 1, 4)
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
        design_layout.addWidget(QLabel("디자인 URL"), 1, 0)
        self.design_url_edit = QLineEdit()
        self.design_url_edit.setPlaceholderText("디자인 참고 URL (선택)")
        design_layout.addWidget(self.design_url_edit, 1, 1)
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
        self.clear_requirements_context_btn = QPushButton("요구사항 / 기능설명 초기화")
        self.clear_requirements_context_btn.clicked.connect(self.on_clear_requirements_context)
        extra_header.addWidget(self.clear_requirements_context_btn)
        req_layout.addLayout(extra_header)
        self.extra_edit = QPlainTextEdit()
        self.extra_edit.setPlaceholderText("예) 로그인 페이지 UI 추가\n예) 회원 관리 목록/상세/등록/수정/삭제\n예) React 기준 REST API + 페이지 라우트 생성")
        self.extra_edit.setMinimumHeight(180)
        req_layout.addWidget(self.extra_edit)
        req_layout.addWidget(QLabel("인증/로그인 감지 결과"))
        self.auth_detect_lbl = QLabel("감지된 기능: (없음)")
        self.auth_detect_lbl.setWordWrap(True)
        self.auth_detect_lbl.setStyleSheet("padding:8px 10px; border:1px solid #dbe4f0; border-radius:10px; background:#f8fbff; color:#334155;")
        req_layout.addWidget(self.auth_detect_lbl)
        auth_box = make_section("인증/로그인 설정", "sec_auth_login", "#f8fbff")
        auth_layout = QGridLayout(auth_box)
        auth_layout.setHorizontalSpacing(10)
        auth_layout.setVerticalSpacing(8)
        self.login_feature_chk = QCheckBox("로그인 기능 포함")
        self.auth_general_chk = QCheckBox("일반 로그인(ID/PW)")
        self.auth_unified_chk = QCheckBox("통합인증")
        self.auth_cert_chk = QCheckBox("인증서 로그인")
        self.auth_jwt_chk = QCheckBox("JWT 로그인")
        self.auth_general_chk.setChecked(True)
        self.auth_unified_chk.setChecked(True)
        auth_layout.addWidget(self.login_feature_chk, 0, 0, 1, 2)
        auth_layout.addWidget(self.auth_general_chk, 1, 0)
        auth_layout.addWidget(self.auth_unified_chk, 1, 1)
        auth_layout.addWidget(self.auth_cert_chk, 2, 0)
        auth_layout.addWidget(self.auth_jwt_chk, 2, 1)
        auth_layout.addWidget(QLabel("기본 진입 방식"), 3, 0)
        self.auth_primary_combo = QComboBox()
        self.auth_primary_combo.addItem("통합인증 우선", "integrated")
        self.auth_primary_combo.addItem("일반 로그인 우선", "general")
        self.auth_primary_combo.addItem("JWT 로그인 우선", "jwt")
        auth_layout.addWidget(self.auth_primary_combo, 3, 1)
        self.auth_selection_lbl = QLabel("최종 적용 설정: 로그인 기능 미사용")
        self.auth_selection_lbl.setWordWrap(True)
        self.auth_selection_lbl.setStyleSheet("color:#0f172a; font-weight:600;")
        auth_layout.addWidget(self.auth_selection_lbl, 4, 0, 1, 2)
        req_layout.addWidget(auth_box)
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
        self.load_last_input_btn = QPushButton("이전 입력 불러오기")
        self.load_last_input_btn.clicked.connect(self.on_load_last_form_state)
        action_btn_row.addWidget(self.load_last_input_btn)
        self.clear_input_btn = QPushButton("초기화")
        self.clear_input_btn.clicked.connect(self.on_clear_form)
        action_btn_row.addWidget(self.clear_input_btn)
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
        for w in [
            getattr(self, "load_last_input_btn", None),
            getattr(self, "clear_input_btn", None),
            getattr(self, "clear_requirements_context_btn", None),
            getattr(self, "gemini_btn", None),
            getattr(self, "ollama_btn", None),
            getattr(self, "extra_load_btn", None),
        ]:
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
    def _update_frontend_branch_state(self) -> None:
        try:
            self._sync_cfg()
        except Exception:
            pass
        summary = self.cfg.frontend_branch_summary() if hasattr(self.cfg, "frontend_branch_summary") else ""
        self.frontend_branch_lbl.setText(f"생성 분기: {summary}")

    def _update_operation_mode_state(self) -> None:
        try:
            self._sync_cfg()
        except Exception:
            pass
        mode_label = self.cfg.operation_mode_label() if hasattr(self.cfg, "operation_mode_label") else ("기존 프로젝트 수정" if getattr(self.cfg, "operation_mode", "create") == "modify" else "신규 생성")
        summary = self.cfg.operation_mode_summary() if hasattr(self.cfg, "operation_mode_summary") else ""
        self.operation_mode_lbl.setText(f"현재 모드: {mode_label}\n{summary}")
        is_modify = bool(getattr(self.cfg, "is_modify_mode", lambda: False)()) if hasattr(self.cfg, "is_modify_mode") else (getattr(self.cfg, "operation_mode", "create") == "modify")
        if is_modify:
            self.overwrite_chk.setText("기존 프로젝트 파일 수정 허용")
            self.folder_picker.setToolTip("수정 모드에서는 저장된 autopj 프로젝트를 선택하세요.")
            self._refresh_saved_projects()
        else:
            self.overwrite_chk.setText("기존 폴더 덮어쓰기")
            self.folder_picker.setToolTip("프로젝트 출력 폴더 경로")
        self._update_saved_projects_ui_state()
    def _current_registered_project(self) -> dict | None:
        project_id = ""
        try:
            project_id = (self.saved_projects_combo.currentData() or "").strip()
        except Exception:
            project_id = ""
        if not project_id:
            return None
        for entry in self._saved_projects_cache:
            if (entry.get("id") or "").strip() == project_id:
                return dict(entry)
        entry = get_registered_project(project_id)
        return dict(entry) if isinstance(entry, dict) else None

    def _refresh_saved_projects(self, preserve_current: bool = True) -> None:
        current_id = ""
        try:
            current_id = (self.saved_projects_combo.currentData() or "").strip() if preserve_current else ""
        except Exception:
            current_id = ""
        self._saved_projects_cache = list_registered_projects()
        self.saved_projects_combo.blockSignals(True)
        try:
            self.saved_projects_combo.clear()
            self.saved_projects_combo.addItem("저장된 autopj 프로젝트 선택", "")
            for entry in self._saved_projects_cache:
                self.saved_projects_combo.addItem(project_display_label(entry), entry.get("id") or "")
            restore_id = current_id or (getattr(self.cfg, "selected_project_id", "") or "")
            if restore_id:
                idx = self.saved_projects_combo.findData(restore_id)
                if idx >= 0:
                    self.saved_projects_combo.setCurrentIndex(idx)
                elif len(self._saved_projects_cache) == 1 and getattr(self.cfg, "is_modify_mode", lambda: False)():
                    self.saved_projects_combo.setCurrentIndex(1)
            elif len(self._saved_projects_cache) == 1 and getattr(self.cfg, "is_modify_mode", lambda: False)():
                self.saved_projects_combo.setCurrentIndex(1)
        finally:
            self.saved_projects_combo.blockSignals(False)
        self._update_saved_projects_ui_state()

    def _apply_selected_registered_project(self) -> None:
        entry = self._current_registered_project()
        if entry:
            selected_path = (entry.get("project_root") or "").strip()
            if selected_path:
                try:
                    self.folder_picker.set_value(selected_path)
                except Exception:
                    pass
            if not self.project_name_edit.text().strip():
                try:
                    self.project_name_edit.setText((entry.get("project_name") or "").strip())
                except Exception:
                    pass
            self._ui_log(f"[PROJECT-REGISTRY] selected: {(entry.get('project_name') or '').strip()} @ {selected_path}")
        self._update_saved_projects_ui_state()
        self._sync_cfg()
        self._refresh_debug_views()

    def _clear_registered_project_selection(self) -> None:
        try:
            self.saved_projects_combo.blockSignals(True)
            self.saved_projects_combo.setCurrentIndex(0)
        finally:
            self.saved_projects_combo.blockSignals(False)
        try:
            if (self.operation_mode_combo.currentData() or "create") == "modify":
                self.folder_picker.set_value("")
        except Exception:
            pass
        self._sync_cfg()
        self._update_saved_projects_ui_state()
        self._refresh_debug_views()
        self.status_lbl.setText("저장 프로젝트 선택 초기화 완료")
        self._ui_log("[PROJECT-REGISTRY] selected project cleared")

    def _reset_registered_projects(self) -> None:
        summary = registry_summary()
        if not summary.get("count", 0):
            self.status_lbl.setText("초기화할 저장 프로젝트 없음")
            self._ui_log("[PROJECT-REGISTRY] reset skipped: registry empty")
            return
        answer = QMessageBox.question(
            self,
            "저장 프로젝트 초기화",
            f"저장된 autopj 프로젝트 {summary.get('count', 0)}건을 목록에서 제거합니다.\n실제 프로젝트 폴더는 삭제하지 않습니다. 계속할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.status_lbl.setText("저장 프로젝트 초기화 취소")
            return
        clear_registry()
        self._saved_projects_cache = []
        self._clear_registered_project_selection()
        self._refresh_saved_projects(preserve_current=False)
        self.status_lbl.setText("저장 프로젝트 목록 초기화 완료")
        self._ui_log("[PROJECT-REGISTRY] registry cleared")

    def _update_saved_projects_ui_state(self) -> None:
        is_modify = bool(getattr(self.cfg, "is_modify_mode", lambda: False)()) if hasattr(self.cfg, "is_modify_mode") else (getattr(self.cfg, "operation_mode", "create") == "modify")
        widgets = [self.saved_projects_title_lbl, self.saved_projects_combo, self.refresh_saved_projects_btn, self.clear_saved_project_selection_btn, self.reset_saved_projects_btn, self.saved_projects_hint_lbl]
        for widget in widgets:
            widget.setVisible(is_modify)
        try:
            self.folder_picker.setEnabled(not is_modify)
        except Exception:
            pass
        summary = registry_summary()
        self.clear_saved_project_selection_btn.setEnabled(is_modify and bool(self.saved_projects_combo.currentData() or ""))
        self.reset_saved_projects_btn.setEnabled(bool(summary.get("count", 0)))
        if not is_modify:
            self.saved_projects_hint_lbl.setText(
                "수정 모드에서 autopj가 저장한 프로젝트 목록이 표시됩니다.\n"
                f"현재 저장 수: {summary.get('count', 0)}개 / 경로 유효: {summary.get('available', 0)}개"
            )
            return
        entry = self._current_registered_project()
        if not self._saved_projects_cache:
            self.saved_projects_hint_lbl.setText(
                "저장된 autopj 프로젝트가 없습니다. 신규 생성이 성공하면 자동으로 목록에 등록됩니다.\n"
                f"레지스트리 파일: {summary.get('path', '-') }"
            )
            return
        if not entry:
            self.saved_projects_hint_lbl.setText(
                "수정 모드에서는 저장된 autopj 프로젝트 목록에서 대상 프로젝트를 선택해야 합니다.\n"
                f"현재 저장 수: {summary.get('count', 0)}개 / 경로 유효: {summary.get('available', 0)}개"
            )
            return
        updated_at = (entry.get("updated_at") or entry.get("created_at") or "-").strip()
        self.saved_projects_hint_lbl.setText(
            f"선택 프로젝트: {(entry.get('project_name') or '(이름 없음)').strip()}\n"
            f"경로: {(entry.get('project_root') or '-').strip()}\n"
            f"최근 저장/수정: {updated_at}\n"
            f"저장 수: {summary.get('count', 0)}개 / 경로 유효: {summary.get('available', 0)}개"
        )

    def _register_successful_project(self, out_dir: str | None, report: dict | None = None) -> None:
        target_dir = (out_dir or getattr(self.cfg, "output_dir", "") or self.folder_picker.value() or "").strip()
        if not target_dir:
            return
        entry = register_project(target_dir, cfg=self.cfg, report=report if isinstance(report, dict) else None)
        if not entry:
            return
        self._ui_log(f"[PROJECT-REGISTRY] saved: {(entry.get('project_name') or '').strip()} @ {(entry.get('project_root') or '').strip()}")
        self._refresh_saved_projects(preserve_current=False)
        project_id = (entry.get("id") or "").strip()
        if project_id:
            idx = self.saved_projects_combo.findData(project_id)
            if idx >= 0:
                self.saved_projects_combo.setCurrentIndex(idx)
        self._sync_cfg()

    def _last_form_state_path(self) -> Path:
        override = (os.environ.get("AUTOPJ_LAST_FORM_STATE_PATH") or "").strip()
        if override:
            path = Path(override).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        base_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        if not base_dir:
            base_dir = str(Path.home() / ".autopj")
        path = Path(base_dir) / "last_form_state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    def _form_field_specs(self) -> list[dict]:
        return [
            {"key": "project_name", "kind": "line", "widget": self.project_name_edit, "default": ""},
            {"key": "output_dir", "kind": "folder", "widget": self.folder_picker, "default": ""},
            {"key": "overwrite", "kind": "check", "widget": self.overwrite_chk, "default": True},
            {"key": "operation_mode", "kind": "combo_data", "widget": self.operation_mode_combo, "default": "create"},
            {"key": "selected_project_id", "kind": "combo_data", "widget": self.saved_projects_combo, "default": ""},
            {"key": "backend_key", "kind": "combo_data", "widget": self.backend_combo, "default": "egov_spring"},
            {"key": "frontend_key", "kind": "combo_data", "widget": self.frontend_combo, "default": "jsp"},
            {"key": "code_engine_key", "kind": "combo_data", "widget": self.engine_combo, "default": "ollama"},
            {"key": "design_style_key", "kind": "combo_data", "widget": self.design_style_combo, "default": "simple"},
            {"key": "design_url", "kind": "line", "widget": self.design_url_edit, "default": ""},
            {"key": "database_key", "kind": "combo_data", "widget": self.db_combo, "default": "sqlite"},
            {"key": "db_name", "kind": "line", "widget": self.db_name_edit, "default": ""},
            {"key": "db_login_id", "kind": "line", "widget": self.db_login_edit, "default": ""},
            {"key": "db_password", "kind": "line", "widget": self.db_pw_edit, "default": "", "sensitive": True, "persist": False},
            {"key": "extra_requirements", "kind": "plain_text", "widget": self.extra_edit, "default": ""},
            {"key": "login_feature_enabled", "kind": "check", "widget": self.login_feature_chk, "default": False},
            {"key": "auth_general_login", "kind": "check", "widget": self.auth_general_chk, "default": True},
            {"key": "auth_unified_auth", "kind": "check", "widget": self.auth_unified_chk, "default": True},
            {"key": "auth_cert_login", "kind": "check", "widget": self.auth_cert_chk, "default": False},
            {"key": "auth_jwt_login", "kind": "check", "widget": self.auth_jwt_chk, "default": False},
            {"key": "auth_primary_mode", "kind": "combo_data", "widget": self.auth_primary_combo, "default": "integrated"},
            {"key": "only_allow_ollama_when_json_ok", "kind": "check", "widget": self.only_allow_ollama_when_json_ok_chk, "default": True},
        ]
    def _read_form_field_value(self, spec: dict):
        widget = spec.get("widget")
        kind = spec.get("kind")
        if widget is None:
            return None
        try:
            if kind == "line":
                return widget.text()
            if kind == "plain_text":
                return widget.toPlainText()
            if kind == "check":
                return bool(widget.isChecked())
            if kind == "combo_data":
                return widget.currentData() or spec.get("default")
            if kind == "folder":
                return widget.value()
        except Exception:
            return spec.get("default")
        return spec.get("default")
    def _apply_form_field_value(self, spec: dict, value) -> None:
        widget = spec.get("widget")
        kind = spec.get("kind")
        default = spec.get("default")
        if value is None:
            value = default
        if widget is None:
            return
        try:
            if kind == "line":
                widget.setText("" if value is None else str(value))
                return
            if kind == "plain_text":
                widget.setPlainText("" if value is None else str(value))
                return
            if kind == "check":
                widget.setChecked(bool(value))
                return
            if kind == "combo_data":
                idx = widget.findData(value)
                if idx < 0:
                    idx = widget.findData(default)
                if idx < 0:
                    idx = 0
                widget.setCurrentIndex(idx)
                return
            if kind == "folder":
                widget.set_value("" if value is None else str(value))
                return
        except Exception:
            return
    def collect_current_form_state(self) -> dict:
        state: dict = {}
        for spec in self._form_field_specs():
            key = str(spec.get("key") or "").strip()
            if not key:
                continue
            state[key] = self._read_form_field_value(spec)
        return state
    def apply_form_state(self, state: dict | None) -> None:
        payload = state or {}
        self._refresh_saved_projects()
        for spec in self._form_field_specs():
            key = str(spec.get("key") or "").strip()
            value = payload.get(key, spec.get("default"))
            if spec.get("sensitive") and key not in payload:
                value = spec.get("default")
            self._apply_form_field_value(spec, value)
        self._sync_cfg()
        self._update_auth_ui_state()
        self._update_frontend_branch_state()
        self._refresh_saved_projects()
        self._update_saved_projects_ui_state()
        self._update_operation_mode_state()
        self._update_ollama_gate_state()
        self._refresh_debug_views()
    def clear_form_state(self) -> None:
        defaults = {str(spec.get("key")): spec.get("default") for spec in self._form_field_specs() if spec.get("key")}
        self.apply_form_state(defaults)

    def _clear_requirement_related_outputs(self) -> None:
        self._last_gemini_json_ok = False
        self._last_analysis_result = None
        self._last_validation_report = None
        self._last_repair_plan = None
        if hasattr(self, "_ollama_stream_buf"):
            self._ollama_stream_buf = ""
        for attr_name in (
            "gemini_out",
            "log_view",
            "debug_summary_view",
            "analysis_view",
            "plan_view",
            "validation_view",
            "apply_report_view",
        ):
            widget = getattr(self, attr_name, None)
            if widget is None:
                continue
            try:
                widget.clear()
            except Exception:
                try:
                    widget.setPlainText("")
                except Exception:
                    pass
        self._update_ollama_gate_state()

    def on_clear_requirements_context(self) -> None:
        try:
            self.extra_edit.clear()
        except Exception:
            self.extra_edit.setPlainText("")
        self._clear_requirement_related_outputs()
        self._sync_cfg()
        self._update_auth_ui_state()
        try:
            self.extra_edit.setFocus()
        except Exception:
            pass
        self.status_lbl.setText("요구사항 / 기능설명 초기화 완료")
    def save_last_form_state(self) -> bool:
        payload = {
            "version": self._form_state_version,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "fields": {},
        }
        current = self.collect_current_form_state()
        for spec in self._form_field_specs():
            key = str(spec.get("key") or "").strip()
            if not key:
                continue
            if spec.get("persist", True) is False:
                continue
            if spec.get("sensitive"):
                continue
            payload["fields"][key] = current.get(key, spec.get("default"))
        try:
            path = self._last_form_state_path()
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception as exc:
            self._ui_log(f"[FORM-STATE] save failed: {exc}")
            return False
    def load_last_form_state(self) -> dict | None:
        path = self._last_form_state_path()
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
            obj = json.loads(raw)
            if not isinstance(obj, dict):
                return None
            fields = obj.get("fields")
            return fields if isinstance(fields, dict) else None
        except Exception as exc:
            self._ui_log(f"[FORM-STATE] load failed: {exc}")
            return None
    def on_clear_form(self) -> None:
        self.clear_form_state()
        self.status_lbl.setText("입력값 초기화 완료")
        self._ui_log("[FORM-STATE] current inputs cleared")
    def on_load_last_form_state(self) -> None:
        state = self.load_last_form_state()
        if not state:
            self.status_lbl.setText("이전 입력값 없음")
            self._ui_log("[FORM-STATE] no saved form state")
            return
        self.apply_form_state(state)
        self.status_lbl.setText("이전 입력값 불러오기 완료")
        self._ui_log("[FORM-STATE] last form state restored")
    def _detected_auth_labels(self, text: str) -> list[str]:
        raw = (text or "").lower()
        labels: list[str] = []
        if any(token in raw for token in ("로그인", "login", "signin", "auth", "인증")):
            labels.append("로그인")
        if any(token in raw for token in ("통합인증", "sso", "single sign-on", "single sign on")):
            labels.append("통합인증")
        if any(token in raw for token in ("인증서 로그인", "인증서로그인", "공동인증서", "certificate login", "cert login")):
            labels.append("인증서 로그인")
        if any(token in raw for token in ("jwt", "jwt login", "token login", "jwt 로그인", "토큰 로그인")):
            labels.append("JWT 로그인")
        if any(token in raw for token in ("일정", "schedule", "calendar", "캘린더")):
            labels.append("일정")
        if any(token in raw for token in ("게시판", "board")):
            labels.append("게시판")
        return labels
    def _update_auth_ui_state(self) -> None:
        detected = self._detected_auth_labels(self.extra_edit.toPlainText())
        detect_text = ", ".join(detected) if detected else "(없음)"
        self.auth_detect_lbl.setText(f"감지된 기능: {detect_text}")
        login_enabled = self.login_feature_chk.isChecked()
        for widget in (self.auth_general_chk, self.auth_unified_chk, self.auth_cert_chk, self.auth_jwt_chk, self.auth_primary_combo):
            widget.setEnabled(login_enabled)
        if not login_enabled:
            self.auth_selection_lbl.setText("최종 적용 설정: 로그인 기능 미사용")
            return
        selected = []
        if self.auth_general_chk.isChecked():
            selected.append("일반 로그인")
        if self.auth_unified_chk.isChecked():
            selected.append("통합인증")
        if self.auth_cert_chk.isChecked():
            selected.append("인증서 로그인")
        if self.auth_jwt_chk.isChecked():
            selected.append("JWT 로그인")
        selected_text = " + ".join(selected) if selected else "로그인 기능만 표시"
        mode_label = self.auth_primary_combo.currentText() or "통합인증 우선"
        self.auth_selection_lbl.setText(f"최종 적용 설정: {selected_text} / {mode_label}")
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
    def _validate_run_preconditions(self) -> bool:
        mode = (getattr(self.cfg, "operation_mode", "create") or "create").strip().lower()
        out_dir_text = (self.folder_picker.value() or self.cfg.output_dir or "").strip()
        if mode != "modify":
            return True
        selected_entry = self._current_registered_project()
        selected_project_id = (selected_entry or {}).get("id") or ""
        ok, entry, message = validate_registered_project(selected_project_id)
        if not ok or not entry:
            QMessageBox.warning(self, "수정 모드", message or "저장된 autopj 프로젝트만 수정할 수 있습니다.")
            return False
        target_root = (entry.get("project_root") or "").strip()
        if not target_root:
            QMessageBox.warning(self, "수정 모드", "저장된 프로젝트 경로를 확인할 수 없습니다.")
            return False
        try:
            self.folder_picker.set_value(target_root)
        except Exception:
            pass
        self._sync_cfg()
        return True

    def on_gemini_generate(self) -> None:
        self._sync_cfg()
        self.save_last_form_state()
        if not self._validate_run_preconditions():
            return
        effective_requirements = self.cfg.effective_extra_requirements() if hasattr(self.cfg, "effective_extra_requirements") else self.cfg.extra_requirements
        if not effective_requirements:
            QMessageBox.information(self, "알림", "추가 요구사항을 입력하거나 인증/로그인 설정을 선택하세요.")
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
        )
        self.gemini_out.setPlainText("Gemini 호출 중... (JSON file-ops 강제)")
        if getattr(self.cfg, "is_modify_mode", lambda: False)():
            self._ui_log("Gemini 호출 시작 (기존 프로젝트 수정 모드)")
        else:
            self._ui_log("Gemini 호출 시작 (신규 생성 모드)")
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
        self.save_last_form_state()
        if not self._validate_run_preconditions():
            return
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
        if getattr(self.cfg, "is_modify_mode", lambda: False)():
            self._ui_log("Ollama 배치(파일별) 시작: Gemini -> (per-file) Ollama [기존 프로젝트 수정 모드]")
        else:
            self._ui_log("Ollama 배치(파일별) 시작: Gemini -> (per-file) Ollama [신규 생성 모드]")
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
        self._register_successful_project(out_dir, report)
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
            try:
                post_validation = validate_and_repair_generated_files(
                    project_root=out_dir,
                    cfg=self.cfg,
                    report=report,
                    file_ops=file_ops,
                    regenerate_callback=None,
                    use_execution_core=_should_use_execution_core_apply(self.cfg),
                    max_regen_attempts=0,
                )
                report.setdefault("patched", {})["post_generation_validation"] = post_validation
                report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
                if not post_validation.get("ok", False):
                    raise RuntimeError(post_validation_failure_message(post_validation))
            except Exception as post_e:
                import traceback
                post_tb = traceback.format_exc()
                report.setdefault("errors", []).append({"path": ".autopj_debug/post_generation_validation.json", "reason": f"post_generation_validation_failed: {post_e}"})
                try:
                    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
                except Exception:
                    pass
                raise RuntimeError(f"post_generation_validation_failed: {post_e}\n{post_tb}")
            self.gemini_out.setPlainText(
                "Ollama 파일 생성 완료\n" + json.dumps(report, indent=2, ensure_ascii=False)
            )
            self._register_successful_project(str(out_dir), report)
            self._refresh_debug_views()
        except Exception as e:
            self.gemini_out.setPlainText(
                "Ollama 생성/검증 실패\n"
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
        self.frontend_combo.currentIndexChanged.connect(lambda _: self._update_frontend_branch_state())
        self.engine_combo.currentIndexChanged.connect(lambda _: self._sync_cfg())
        self.design_style_combo.currentIndexChanged.connect(lambda _: self._sync_cfg())
        self.design_url_edit.textChanged.connect(lambda _: self._sync_cfg())
        self.db_combo.currentIndexChanged.connect(lambda _: self._sync_cfg())
        self.db_name_edit.textChanged.connect(lambda _: self._sync_cfg())
        self.db_login_edit.textChanged.connect(lambda _: self._sync_cfg())
        self.db_pw_edit.textChanged.connect(lambda _: self._sync_cfg())
        self.folder_picker.changed.connect(lambda _: self._sync_cfg())
        self.folder_picker.changed.connect(lambda _: self._refresh_debug_views())
        self.refresh_saved_projects_btn.clicked.connect(self._refresh_saved_projects)
        self.clear_saved_project_selection_btn.clicked.connect(self._clear_registered_project_selection)
        self.reset_saved_projects_btn.clicked.connect(self._reset_registered_projects)
        self.saved_projects_combo.currentIndexChanged.connect(lambda _: self._apply_selected_registered_project())
        self.overwrite_chk.stateChanged.connect(lambda _: self._sync_cfg())
        self.operation_mode_combo.currentIndexChanged.connect(lambda _: self._update_operation_mode_state())
        self.operation_mode_combo.currentIndexChanged.connect(lambda _: self._update_saved_projects_ui_state())
        self.operation_mode_combo.currentIndexChanged.connect(lambda _: self._sync_cfg())
        self.extra_edit.textChanged.connect(self._update_auth_ui_state)
        self.extra_edit.textChanged.connect(lambda: self._sync_cfg())
        self.login_feature_chk.stateChanged.connect(lambda _: self._update_auth_ui_state())
        self.login_feature_chk.stateChanged.connect(lambda _: self._sync_cfg())
        self.auth_general_chk.stateChanged.connect(lambda _: self._update_auth_ui_state())
        self.auth_general_chk.stateChanged.connect(lambda _: self._sync_cfg())
        self.auth_unified_chk.stateChanged.connect(lambda _: self._update_auth_ui_state())
        self.auth_unified_chk.stateChanged.connect(lambda _: self._sync_cfg())
        self.auth_cert_chk.stateChanged.connect(lambda _: self._update_auth_ui_state())
        self.auth_cert_chk.stateChanged.connect(lambda _: self._sync_cfg())
        self.auth_jwt_chk.stateChanged.connect(lambda _: self._update_auth_ui_state())
        self.auth_jwt_chk.stateChanged.connect(lambda _: self._sync_cfg())
        self.auth_primary_combo.currentIndexChanged.connect(lambda _: self._update_auth_ui_state())
        self.auth_primary_combo.currentIndexChanged.connect(lambda _: self._sync_cfg())
    def _apply_defaults(self) -> None:
        self.backend_combo.setCurrentIndex(self._backend_map.get(self.cfg.backend_key, 0))
        self.frontend_combo.setCurrentIndex(self._frontend_map.get(self.cfg.frontend_key, 0))
        self.engine_combo.setCurrentIndex(self._engine_map.get(self.cfg.code_engine_key, 0))
        self.design_style_combo.setCurrentIndex(self._design_map.get(self.cfg.design_style_key, 0))
        self.db_combo.setCurrentIndex(self._db_map.get(self.cfg.database_key, 0))
        self.overwrite_chk.setChecked(self.cfg.overwrite)
        self.operation_mode_combo.setCurrentIndex(max(0, self.operation_mode_combo.findData(getattr(self.cfg, "operation_mode", "create"))))
        self.login_feature_chk.setChecked(self.cfg.login_feature_enabled)
        self.auth_general_chk.setChecked(self.cfg.auth_general_login if self.cfg.login_feature_enabled else True)
        self.auth_unified_chk.setChecked(self.cfg.auth_unified_auth if self.cfg.login_feature_enabled else True)
        self.auth_cert_chk.setChecked(self.cfg.auth_cert_login)
        self.auth_jwt_chk.setChecked(self.cfg.auth_jwt_login)
        self.auth_primary_combo.setCurrentIndex(max(0, self.auth_primary_combo.findData(self.cfg.auth_primary_mode)))
        self._update_auth_ui_state()
        self._update_frontend_branch_state()
        self._refresh_saved_projects()
        self._update_saved_projects_ui_state()
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
        self.cfg.design_style_key = self.design_style_combo.currentData() or "simple"
        self.cfg.design_style_label = self.design_style_combo.currentText() or "심플"
        self.cfg.design_url = self.design_url_edit.text()
        self.cfg.database_key = self.db_combo.currentData() or "sqlite"
        self.cfg.database_label = self.db_combo.currentText() or "SQLite"
        self.cfg.db_name = self.db_name_edit.text()
        self.cfg.db_login_id = self.db_login_edit.text()
        self.cfg.db_password = self.db_pw_edit.text()
        selected_entry = self._current_registered_project()
        selected_project_path = (selected_entry or {}).get("project_root") or ""
        if (self.operation_mode_combo.currentData() or "create") == "modify" and selected_project_path:
            try:
                self.folder_picker.set_value(selected_project_path)
            except Exception:
                pass
        self.cfg.output_dir = selected_project_path if (self.operation_mode_combo.currentData() or "create") == "modify" and selected_project_path else self.folder_picker.value()
        self.cfg.overwrite = self.overwrite_chk.isChecked()
        self.cfg.operation_mode = self.operation_mode_combo.currentData() or "create"
        self.cfg.selected_project_id = (selected_entry or {}).get("id") or ""
        self.cfg.selected_project_name = (selected_entry or {}).get("project_name") or ""
        self.cfg.selected_project_path = selected_project_path
        self.cfg.extra_requirements = self.extra_edit.toPlainText()
        self.cfg.login_feature_enabled = self.login_feature_chk.isChecked()
        self.cfg.auth_general_login = self.auth_general_chk.isChecked()
        self.cfg.auth_unified_auth = self.auth_unified_chk.isChecked()
        self.cfg.auth_cert_login = self.auth_cert_chk.isChecked()
        self.cfg.auth_jwt_login = self.auth_jwt_chk.isChecked()
        self.cfg.auth_primary_mode = (self.auth_primary_combo.currentData() or "integrated")
        self.cfg.normalize()
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
            f"selected_project_id={self.cfg.selected_project_id}\n"
            f"selected_project_path={self.cfg.selected_project_path}\n"
        )
        QMessageBox.information(self, "현재 설정", msg)
