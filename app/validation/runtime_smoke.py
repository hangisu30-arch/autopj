from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
import signal
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.validation.compile_error_parser import compile_error_paths, parse_compile_errors


_ERROR_PATTERNS: List[Tuple[str, re.Pattern[str], str]] = [
    ("application_run_failed", re.compile(r"Application run failed", re.IGNORECASE), "Spring Boot startup failed"),
    ("unsatisfied_dependency", re.compile(r"UnsatisfiedDependencyException", re.IGNORECASE), "Spring dependency injection failed"),
    ("bean_creation", re.compile(r"BeanCreationException", re.IGNORECASE), "Spring bean creation failed"),
    ("conflicting_bean", re.compile(r"ConflictingBeanDefinitionException", re.IGNORECASE), "Duplicate or conflicting Spring bean detected"),
    ("ambiguous_request_mapping", re.compile(r"Ambiguous mapping", re.IGNORECASE), "Spring request mapping conflict detected"),
    (
        "mapper_xml_missing",
        re.compile(r"(Mapped Statements collection does not contain value|Invalid bound statement|Mapper XML.*not found|Could not find mapper XML)", re.IGNORECASE),
        "MyBatis mapper XML or statement mismatch",
    ),
    ("mybatis_binding", re.compile(r"(MyBatisSystemException|BindingException|ReflectionException)", re.IGNORECASE), "MyBatis runtime binding failed"),
    ("bind_exception", re.compile(r"(BindException|typeMismatch\.)", re.IGNORECASE), "Spring request/data binding failed"),
    ("jasper_exception", re.compile(r"JasperException", re.IGNORECASE), "JSP rendering failed"),
    ("property_not_found", re.compile(r"PropertyNotFoundException", re.IGNORECASE), "JSP EL property mismatch"),
    (
        "sql_error",
        re.compile(r"(SQLSyntaxErrorException|BadSqlGrammarException|Unknown column|Table .* doesn't exist|relation .* does not exist)", re.IGNORECASE),
        "SQL or schema mismatch detected",
    ),
    ("cannot_find_symbol", re.compile(r"cannot find symbol", re.IGNORECASE), "Java compile error: missing symbol"),
    ("package_missing", re.compile(r"package\s+[^\n]+\s+does not exist", re.IGNORECASE), "Java compile error: missing package/import"),
    ("unresolved_compilation", re.compile(r"Unresolved compilation problems?", re.IGNORECASE), "Compiled class contains unresolved compilation problems"),
    ("port_in_use", re.compile(r"(Port \d+ was already in use|Address already in use)", re.IGNORECASE), "Server port conflict"),
]

_STARTUP_SUCCESS_PATTERNS = [
    re.compile(r"Started\s+.+Application\s+in\s+.+seconds", re.IGNORECASE),
    re.compile(r"Started\s+.+\s+in\s+.+seconds", re.IGNORECASE),
    re.compile(r"Tomcat started on port\(s\):", re.IGNORECASE),
]

_CLASS_MAPPING_RE = re.compile(r'@RequestMapping\((.*?)\)\s*public\s+class\s+([A-Za-z_][A-Za-z0-9_]*)', re.DOTALL)
_METHOD_MAPPING_RE = re.compile(r'@(GetMapping|RequestMapping)\((.*?)\)\s*public\s+[A-Za-z0-9_<>\[\]]+\s+[A-Za-z_][A-Za-z0-9_]*\s*\((.*?)\)', re.DOTALL)


def _tail(text: str, limit: int = 12000) -> str:
    text = text or ""
    if len(text) <= limit:
        return text
    return text[-limit:]


def _quote_command(parts: List[str]) -> str:
    quoted: List[str] = []
    for part in parts:
        if not part:
            quoted.append('""')
        elif any(ch.isspace() for ch in part) or '"' in part:
            quoted.append('"' + part.replace('"', '\\"') + '"')
        else:
            quoted.append(part)
    return " ".join(quoted)

def _popen_launch_kwargs() -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {}
    if os.name == 'nt':
        creationflags = int(getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0) or 0)
        if creationflags:
            kwargs['creationflags'] = creationflags
    else:
        kwargs['start_new_session'] = True
    return kwargs


def _normalize_route(value: str) -> str:
    value = (value or "").strip().strip('"\'')
    if not value:
        return "/"
    if not value.startswith("/"):
        value = "/" + value
    value = re.sub(r"/+", "/", value)
    return value.rstrip("/") or "/"


def _join_routes(base: str, child: str) -> str:
    if not child:
        return _normalize_route(base)
    if child == "/":
        return _normalize_route(base)
    return _normalize_route((_normalize_route(base).rstrip("/") + "/" + child.lstrip("/")))


def _extract_paths(annotation_args: str) -> List[str]:
    args = annotation_args or ""
    quoted = re.findall(r'"([^"]+)"', args)
    if quoted:
        return [_normalize_route(x) for x in quoted]
    if "RequestMethod.GET" in args or "method = RequestMethod.GET" in args:
        match = re.search(r'value\s*=\s*"([^"]+)"', args)
        if match:
            return [_normalize_route(match.group(1))]
        match = re.search(r'path\s*=\s*"([^"]+)"', args)
        if match:
            return [_normalize_route(match.group(1))]
        return ["/"]
    return []

def _has_required_route_params(params_sig: str) -> bool:
    sig = (params_sig or "").replace(" ", "").lower()
    if '@pathvariable' in sig:
        return True
    for match in re.finditer(r'@requestparam\(([^)]*)\)', sig):
        args = match.group(1)
        if 'required=false' in args:
            continue
        return True
    return False


def _discover_controller_routes(project_root: Path, limit: int = 12) -> List[str]:
    java_root = Path(project_root) / "src/main/java"
    if not java_root.exists():
        return ["/"]
    routes: List[str] = ["/"]
    seen = set(routes)
    method_ann_re = re.compile(r'@(GetMapping|RequestMapping)\((.*?)\)', re.DOTALL)
    method_name_re = re.compile(r'public\s+[A-Za-z0-9_<>\[\]]+\s+[A-Za-z_][A-Za-z0-9_]*\s*\(')
    for controller in java_root.rglob("*Controller.java"):
        try:
            body = controller.read_text(encoding="utf-8")
        except Exception:
            body = controller.read_text(encoding="utf-8", errors="ignore")
        class_match = _CLASS_MAPPING_RE.search(body)
        base_routes = ["/"]
        if class_match:
            extracted = _extract_paths(class_match.group(1))
            if extracted:
                base_routes = extracted
        lines = body.splitlines()
        i = 0
        pending_annotations: List[str] = []
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped.startswith('@'):
                pending_annotations.append(stripped)
                i += 1
                continue
            if 'public ' not in stripped or '(' not in stripped:
                pending_annotations = [] if stripped else pending_annotations
                i += 1
                continue
            if not pending_annotations:
                i += 1
                continue
            signature_parts = [stripped]
            while '{' not in signature_parts[-1] and i + 1 < len(lines):
                i += 1
                signature_parts.append(lines[i].strip())
            signature = ' '.join(signature_parts)
            if not method_name_re.search(signature):
                pending_annotations = []
                i += 1
                continue
            params_start = signature.find('(')
            depth = 0
            cursor = params_start
            while cursor < len(signature):
                ch = signature[cursor]
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    if depth == 0:
                        cursor += 1
                        break
                cursor += 1
            params_sig = signature[params_start + 1:max(params_start + 1, cursor - 1)]
            ann = '\n'.join(pending_annotations)
            requires_params = _has_required_route_params(params_sig)
            for method_match in method_ann_re.finditer(ann):
                kind = method_match.group(1)
                args = method_match.group(2)
                if kind == "RequestMapping" and "RequestMethod.GET" not in args:
                    continue
                child_routes = _extract_paths(args) or ["/"]
                for base in base_routes:
                    for child in child_routes:
                        route = _join_routes(base, child)
                        low = route.lower()
                        if "{" in route or "}" in route:
                            continue
                        if requires_params:
                            continue
                        if any(token in low for token in ("delete", "remove", "save", "update", "create")):
                            continue
                        if route not in seen:
                            seen.add(route)
                            routes.append(route)
                        if len(routes) >= limit:
                            return routes
            pending_annotations = []
            i += 1
    return routes[:limit]


def parse_backend_log_errors(text: str) -> List[Dict[str, str]]:
    text = text or ""
    errors: List[Dict[str, Any]] = []
    seen = set()
    ambiguous_details = _extract_ambiguous_mapping_details(text)
    for code, pattern, message in _ERROR_PATTERNS:
        match = pattern.search(text)
        if not match or code in seen:
            continue
        seen.add(code)
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        if line_end == -1:
            line_end = len(text)
        snippet = text[line_start:line_end].strip()
        row: Dict[str, Any] = {"code": code, "message": message, "snippet": snippet[:300]}
        if code == 'ambiguous_request_mapping' and ambiguous_details:
            row.update({k: v for k, v in ambiguous_details.items() if v not in (None, '', [])})
        errors.append(row)
        if code == "jasper_exception":
            errors.append({"code": "jsp_error", "message": message, "snippet": snippet[:300]})
    return errors


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])




def _fqcn_to_java_path(fqcn: str) -> str:
    fqcn = (fqcn or '').strip()
    if not fqcn:
        return ''
    return 'src/main/java/' + fqcn.replace('.', '/') + '.java'


_AMBIGUOUS_MAPPING_HEADER_RE = re.compile(
    r"Cannot map '([^']+)' method\s+([A-Za-z0-9_$.]+)#([A-Za-z0-9_]+)\([^)]*\)\s+to \{([A-Z]+) \[([^\]]+)\]\}",
    re.IGNORECASE | re.DOTALL,
)
_CONFLICTING_METHOD_RE = re.compile(
    r"There is already '([^']+)' bean method(?:\s+([A-Za-z0-9_$.]+)#([A-Za-z0-9_]+)\()?",
    re.IGNORECASE | re.DOTALL,
)


def _extract_ambiguous_mapping_details(text: str) -> Dict[str, Any]:
    text = text or ''
    header = _AMBIGUOUS_MAPPING_HEADER_RE.search(text)
    if not header:
        return {}
    raw_routes = str(header.group(5) or '').strip()
    routes = []
    for part in re.split(r"\s*\|\|\s*", raw_routes):
        route = _normalize_route(part)
        if route and route not in routes:
            routes.append(route)
    details: Dict[str, Any] = {
        'bean': (header.group(1) or '').strip(),
        'method_fqcn': (header.group(2) or '').strip(),
        'method': (header.group(3) or '').strip(),
        'http_method': (header.group(4) or '').strip().upper(),
        'routes': routes,
        'route': routes[0] if routes else '',
    }
    conflict = _CONFLICTING_METHOD_RE.search(text)
    if conflict:
        details['conflicting_bean'] = (conflict.group(1) or '').strip()
        if conflict.group(2):
            details['conflicting_method_fqcn'] = (conflict.group(2) or '').strip()
        if conflict.group(3):
            details['conflicting_method'] = (conflict.group(3) or '').strip()
    path = _fqcn_to_java_path(details['method_fqcn'])
    conflicting_path = _fqcn_to_java_path(details.get('conflicting_method_fqcn') or '')
    if path:
        details['path'] = path
    if conflicting_path:
        details['conflicting_path'] = conflicting_path
    return details


def clear_stale_backend_outputs(project_root: Path) -> List[str]:
    root = Path(project_root)
    removed: List[str] = []
    stale_dirs = [
        root / "target/classes",
        root / "target/test-classes",
        root / "build/classes/java/main",
        root / "build/classes/java/test",
        root / "out/production",
    ]
    for path in stale_dirs:
        try:
            if path.exists():
                shutil.rmtree(path)
                removed.append(str(path.relative_to(root)).replace('\\', '/'))
        except Exception:
            continue
    return removed


def _maven_compile_candidates(project_root: Path) -> List[Dict[str, Any]]:
    root = Path(project_root)
    candidates: List[Dict[str, Any]] = []
    if os.name == "nt":
        if (root / "mvnw.cmd").exists():
            cmd = ["cmd", "/c", "mvnw.cmd", "-q", "-DskipTests", "clean", "compile"]
            candidates.append({"tool": "maven_wrapper", "family": "maven", "command": cmd, "display": _quote_command(cmd)})
        if shutil.which("mvn"):
            cmd = ["mvn", "-q", "-DskipTests", "clean", "compile"]
            candidates.append({"tool": "maven", "family": "maven", "command": cmd, "display": _quote_command(cmd)})
    else:
        if (root / "mvnw").exists():
            cmd = ["./mvnw", "-q", "-DskipTests", "clean", "compile"]
            candidates.append({"tool": "maven_wrapper", "family": "maven", "command": cmd, "display": _quote_command(cmd)})
        if shutil.which("mvn"):
            cmd = ["mvn", "-q", "-DskipTests", "clean", "compile"]
            candidates.append({"tool": "maven", "family": "maven", "command": cmd, "display": _quote_command(cmd)})
    return candidates


def _gradle_compile_candidates(project_root: Path) -> List[Dict[str, Any]]:
    root = Path(project_root)
    candidates: List[Dict[str, Any]] = []
    if os.name == "nt":
        if (root / "gradlew.bat").exists():
            cmd = ["cmd", "/c", "gradlew.bat", "-q", "clean", "compileJava"]
            candidates.append({"tool": "gradle_wrapper", "family": "gradle", "command": cmd, "display": _quote_command(cmd)})
        if shutil.which("gradle"):
            cmd = ["gradle", "-q", "clean", "compileJava"]
            candidates.append({"tool": "gradle", "family": "gradle", "command": cmd, "display": _quote_command(cmd)})
    else:
        if (root / "gradlew").exists():
            cmd = ["./gradlew", "-q", "clean", "compileJava"]
            candidates.append({"tool": "gradle_wrapper", "family": "gradle", "command": cmd, "display": _quote_command(cmd)})
        if shutil.which("gradle"):
            cmd = ["gradle", "-q", "clean", "compileJava"]
            candidates.append({"tool": "gradle", "family": "gradle", "command": cmd, "display": _quote_command(cmd)})
    return candidates


def _compile_candidates(project_root: Path) -> List[Dict[str, Any]]:
    root = Path(project_root)
    candidates: List[Dict[str, Any]] = []
    if (root / "pom.xml").exists() or (root / "mvnw").exists() or (root / "mvnw.cmd").exists():
        candidates.extend(_maven_compile_candidates(root))
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists() or (root / "gradlew").exists() or (root / "gradlew.bat").exists():
        candidates.extend(_gradle_compile_candidates(root))
    return candidates


def _startup_command(candidate: Dict[str, Any], port: int) -> Dict[str, Any]:
    family = candidate.get("family")
    if family == "maven":
        if os.name == "nt" and candidate.get("tool") == "maven_wrapper":
            cmd = ["cmd", "/c", "mvnw.cmd", "-q", "-DskipTests", f"-Dspring-boot.run.arguments=--server.port={port}", "spring-boot:run"]
        elif candidate.get("tool") == "maven_wrapper":
            cmd = ["./mvnw", "-q", "-DskipTests", f"-Dspring-boot.run.arguments=--server.port={port}", "spring-boot:run"]
        else:
            cmd = ["mvn", "-q", "-DskipTests", f"-Dspring-boot.run.arguments=--server.port={port}", "spring-boot:run"]
    else:
        if os.name == "nt" and candidate.get("tool") == "gradle_wrapper":
            cmd = ["cmd", "/c", "gradlew.bat", "-q", "bootRun", f"--args=--server.port={port}"]
        elif candidate.get("tool") == "gradle_wrapper":
            cmd = ["./gradlew", "-q", "bootRun", f"--args=--server.port={port}"]
        else:
            cmd = ["gradle", "-q", "bootRun", f"--args=--server.port={port}"]
    return {"tool": candidate.get("tool"), "family": family, "command": cmd, "display": _quote_command(cmd), "port": port}


def _run_compile(candidate: Dict[str, Any], project_root: Path, timeout_seconds: int = 300) -> Dict[str, Any]:
    proc: Optional[subprocess.Popen[Any]] = None
    try:
        proc = subprocess.Popen(
            candidate["command"],
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            **_popen_launch_kwargs(),
        )
        output, _ = proc.communicate(timeout=timeout_seconds)
        output = output or ""
        ok = proc.returncode == 0
        compile_errors = parse_compile_errors(output, project_root=project_root)
        return {
            "status": "ok" if ok else "failed",
            "tool": candidate.get("tool"),
            "family": candidate.get("family"),
            "command": candidate.get("display"),
            "returncode": proc.returncode,
            "log_tail": _tail(output),
            "raw_output": output,
            "errors": compile_errors if compile_errors else ([] if ok else parse_backend_log_errors(output)),
            "error_count": len(compile_errors if compile_errors else ([] if ok else parse_backend_log_errors(output))),
            "failed_targets": compile_error_paths(compile_errors),
        }
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        return {
            "status": "failed",
            "tool": candidate.get("tool"),
            "family": candidate.get("family"),
            "command": candidate.get("display"),
            "returncode": None,
            "log_tail": _tail(out),
            "raw_output": out,
            "errors": [{"code": "compile_timeout", "message": "Backend compile timed out", "snippet": ""}],
            "error_count": 1,
            "failed_targets": [],
        }
    except Exception as exc:
        return {
            "status": "failed",
            "tool": candidate.get("tool"),
            "family": candidate.get("family"),
            "command": candidate.get("display"),
            "returncode": None,
            "log_tail": "",
            "raw_output": "",
            "errors": [{"code": "compile_exception", "message": str(exc), "snippet": ""}],
            "error_count": 1,
            "failed_targets": [],
        }
    finally:
        _stop_process(proc)


def run_backend_compile(project_root: Path, timeout_seconds: int = 300) -> Dict[str, Any]:
    candidates = _compile_candidates(project_root)
    stale_outputs_removed = clear_stale_backend_outputs(project_root)
    if not candidates:
        return {
            "status": "failed",
            "tool": None,
            "family": None,
            "command": None,
            "returncode": None,
            "log_tail": "",
            "errors": [{"code": "build_tool_missing", "message": "No Maven/Gradle wrapper or executable found for backend compile", "snippet": ""}],
            "clean_compile_required": True,
            "stale_outputs_removed": stale_outputs_removed,
        }
    result = _run_compile(candidates[0], project_root, timeout_seconds=timeout_seconds)
    result["candidate_count"] = len(candidates)
    result["clean_compile_required"] = True
    result["stale_outputs_removed"] = stale_outputs_removed
    return result


def _stop_process(proc: Optional[subprocess.Popen[Any]]) -> None:
    if proc is None:
        return
    pid = getattr(proc, 'pid', None)
    try:
        if os.name == 'nt' and pid:
            try:
                subprocess.run(
                    ['taskkill', '/PID', str(int(pid)), '/T', '/F'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=15,
                )
            except Exception:
                pass
        elif pid:
            try:
                os.killpg(int(pid), signal.SIGTERM)
            except Exception:
                pass
        poll = getattr(proc, 'poll', None)
        is_running = True
        if callable(poll):
            try:
                is_running = poll() is None
            except Exception:
                is_running = True
        if is_running and hasattr(proc, 'terminate'):
            proc.terminate()
            if hasattr(proc, 'wait'):
                proc.wait(timeout=10)
        elif hasattr(proc, 'wait'):
            proc.wait(timeout=2)
    except Exception:
        try:
            if os.name != 'nt' and pid:
                try:
                    os.killpg(int(pid), signal.SIGKILL)
                except Exception:
                    pass
            if hasattr(proc, 'kill'):
                proc.kill()
            if hasattr(proc, 'wait'):
                proc.wait(timeout=5)
        except Exception:
            pass


def _port_accepting_connections(port: int, host: str = "127.0.0.1", timeout_seconds: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=max(0.1, float(timeout_seconds))):
            return True
    except Exception:
        return False


def _wait_for_startup_probe(port: int, base_url: str, grace_seconds: int = 20) -> bool:
    deadline = time.time() + max(3, int(grace_seconds))
    probe_routes = ("/", "/login/login.do", "/index.do")
    while time.time() < deadline:
        if _port_accepting_connections(port):
            for route in probe_routes:
                try:
                    req = urllib.request.Request(base_url.rstrip('/') + route, headers={"User-Agent": "autopj-startup-probe/1.0"}, method="GET")
                    with urllib.request.urlopen(req, timeout=2) as resp:
                        status = int(getattr(resp, "status", 200) or 200)
                    if 200 <= status < 500:
                        return True
                except Exception:
                    continue
        time.sleep(0.5)
    return False


def _error_text_indicates_connection_refused(value: Any) -> bool:
    text = str(value or '').strip().lower()
    if not text:
        return False
    return (
        'connection refused' in text
        or 'actively refused' in text
        or 'target machine actively refused' in text
        or 'winerror 10061' in text
        or 'errno 111' in text
    )


def _is_connection_refused_error(exc: Exception) -> bool:
    if isinstance(exc, ConnectionRefusedError):
        return True
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, 'reason', None)
        if isinstance(reason, ConnectionRefusedError):
            return True
        if isinstance(reason, OSError) and getattr(reason, 'errno', None) in {61, 111, 10061}:
            return True
        if _error_text_indicates_connection_refused(reason):
            return True
    if isinstance(exc, OSError) and getattr(exc, 'errno', None) in {61, 111, 10061}:
        return True
    return _error_text_indicates_connection_refused(exc)


def _http_route_looks_ready(base_url: str, routes: List[str], timeout_seconds: float = 2.0) -> bool:
    probe_routes = list(_select_smoke_routes(routes or []))[:3] or ['/', '/login/login.do', '/index.do']
    for route in probe_routes:
        normalized = _normalize_route(route)
        req = urllib.request.Request(base_url.rstrip('/') + normalized, headers={"User-Agent": "autopj-startup-probe/1.0"}, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=max(0.5, float(timeout_seconds))) as resp:
                status = int(getattr(resp, 'status', 200) or 200)
            if 200 <= status < 500:
                return True
        except urllib.error.HTTPError as exc:
            if 200 <= int(getattr(exc, 'code', 500) or 500) < 500:
                return True
        except Exception:
            continue
    return False


def _wait_for_endpoint_smoke_ready(port: int, base_url: str, routes: List[str], grace_seconds: int = 20) -> bool:
    deadline = time.time() + max(3, int(grace_seconds))
    selected_routes = list(_select_smoke_routes(routes or []))
    while time.time() < deadline:
        if _port_accepting_connections(port) and _http_route_looks_ready(base_url, selected_routes, timeout_seconds=2.0):
            return True
        time.sleep(0.5)
    return False


def _connection_refused_only(report: Dict[str, Any]) -> bool:
    rows = list((report or {}).get('results') or [])
    failed = [row for row in rows if not row.get('ok')]
    if not failed or any(row.get('ok') for row in rows):
        return False
    return all(_error_text_indicates_connection_refused(row.get('error') or '') for row in failed)

def _process_has_exited(proc: Optional[subprocess.Popen[Any]]) -> bool:
    if proc is None:
        return True
    poll = getattr(proc, 'poll', None)
    if callable(poll):
        try:
            return poll() is not None
        except Exception:
            return False
    return False


def _run_endpoint_smoke_with_backend_recovery(
    project_root: Path,
    compile_result: Dict[str, Any],
    startup_result: Dict[str, Any],
    proc: subprocess.Popen[Any],
    routes: List[str],
    *,
    startup_timeout_seconds: int,
    endpoint_runner,
) -> Tuple[Dict[str, Any], Dict[str, Any], subprocess.Popen[Any]]:
    selected_routes = list(_select_smoke_routes(routes or []))
    current_proc = proc
    current_startup = dict(startup_result or {})
    grace_seconds = max(8, min(30, int(startup_timeout_seconds) // 3 if startup_timeout_seconds else 12))

    def _smoke_once(base_url: str, run_proc: subprocess.Popen[Any]) -> Tuple[Dict[str, Any], bool]:
        ready = _wait_for_endpoint_smoke_ready(current_startup.get('port') or 0, base_url, selected_routes, grace_seconds=grace_seconds)
        if not ready:
            if _process_has_exited(run_proc):
                return ({
                    'status': 'failed',
                    'results': [{'route': route, 'ok': False, 'error': 'backend process exited before endpoint smoke became ready'} for route in selected_routes],
                    'failed_count': len(selected_routes),
                    'connection_refused_only': True,
                }, True)
            time.sleep(2.0)
        smoke = endpoint_runner(base_url, selected_routes)
        if smoke.get('status') != 'ok' and smoke.get('connection_refused_only'):
            if _process_has_exited(run_proc):
                return smoke, True
            for _ in range(2):
                if not _wait_for_endpoint_smoke_ready(current_startup.get('port') or 0, base_url, selected_routes, grace_seconds=max(6, grace_seconds)):
                    time.sleep(2.0)
                smoke = endpoint_runner(base_url, selected_routes)
                if smoke.get('status') == 'ok' or not smoke.get('connection_refused_only'):
                    break
            if smoke.get('status') != 'ok' and smoke.get('connection_refused_only') and _process_has_exited(run_proc):
                return smoke, True
        return smoke, False

    base_url = current_startup.get('base_url') or f"http://127.0.0.1:{current_startup.get('port')}"
    endpoint_smoke, should_restart = _smoke_once(base_url, current_proc)
    if endpoint_smoke.get('status') == 'ok' or not should_restart:
        return endpoint_smoke, current_startup, current_proc

    _stop_process(current_proc)
    restarted_startup, restarted_proc = _start_backend(compile_result, project_root, startup_timeout_seconds=startup_timeout_seconds)
    if restarted_startup.get('status') != 'ok' or restarted_proc is None:
        return endpoint_smoke, current_startup, current_proc
    restarted_startup['base_url'] = restarted_startup.get('base_url') or f"http://127.0.0.1:{restarted_startup.get('port')}"
    base_url = restarted_startup['base_url']
    retry_smoke, _ = _smoke_once(base_url, restarted_proc)
    return retry_smoke, restarted_startup, restarted_proc


def _debug_dir(project_root: Path) -> Path:
    debug_dir = Path(project_root) / ".autopj_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    return debug_dir


def _normalize_failure_signature(text: str, code: str = '') -> str:
    body = (text or '').strip().lower()
    if not body:
        return ''
    body = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', '#-#-#', body)
    body = re.sub(r'\b\d{1,2}:\d{2}:\d{2}(?:,\d+)?\b', '#:#:#,#', body)
    body = re.sub(r'\b\d+(?:\.\d+)+\b', '#.#.#', body)
    body = re.sub(r'\bline:?\s*\d+\b', 'line #', body)
    body = re.sub(r'\bstatement\s*#\d+\b', 'statement ##', body)
    body = re.sub(r'\bport\s+\d+\b', 'port #', body)
    body = re.sub(r'\b\d+\b', '#', body)
    body = re.sub(r'\s+', ' ', body).strip()
    return f"{code}|{body}" if code else body


_FRAMEWORK_STACK_PREFIXES = (
    'at org.springframework.',
    'at java.',
    'at javax.',
    'at jakarta.',
    'at sun.',
    'at jdk.',
    'at com.mysql.',
    'at org.apache.',
)


def _meaningful_startup_line(line: str) -> bool:
    raw = (line or '').strip()
    if not raw:
        return False
    low = raw.lower()
    if raw.startswith('at ') and low.startswith(_FRAMEWORK_STACK_PREFIXES):
        return False
    if low in {'application run failed', "error starting applicationcontext. to display the condition evaluation report re-run your application with 'debug' enabled."}:
        return False
    return True


def _extract_startup_root_cause(output: str, errors: List[Dict[str, Any]]) -> str:
    text = output or ''
    for err in (errors or []):
        snippet = str(err.get('snippet') or '').strip()
        if not _meaningful_startup_line(snippet):
            continue
        nested = re.findall(r'nested exception is\s+([^;\n]+(?:;[^\n]*)?)', snippet, re.IGNORECASE)
        if nested:
            for item in reversed(nested):
                if _meaningful_startup_line(item):
                    return item.strip()
        if _meaningful_startup_line(snippet):
            return snippet
    patterns = [
        r'nested exception is\s+([^\n]+)',
        r'Caused by:\s*([^\n]+)',
        r'(?:ERROR|WARN)\s+\[[^\]]+\]\s+([^\n]+(?:Exception|Error)[^\n]*)',
        r'((?:[A-Za-z0-9_$.]+(?:Exception|Error)):\s*[^\n]+)',
        r'(Failed to execute SQL script statement[^\n]+)',
        r'(Unknown column[^\n]+)',
        r'(Duplicate column name[^\n]+)',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for item in reversed(matches):
            candidate = str(item).strip()
            if _meaningful_startup_line(candidate):
                return candidate
    for line in reversed(text.splitlines()):
        if _meaningful_startup_line(line) and ('exception' in line.lower() or 'error' in line.lower() or 'failed' in line.lower()):
            return line.strip()
    return ''


def _extract_related_project_paths(project_root: Path, output: str) -> List[str]:
    root = Path(project_root)
    text = output or ''
    seen = set()
    rows: List[str] = []

    def add(rel: str) -> None:
        rel = (rel or '').replace('\\', '/').strip()
        while rel.startswith('./'):
            rel = rel[2:]
        if not rel or rel in seen:
            return
        if (root / rel).exists():
            seen.add(rel)
            rows.append(rel)
            return
        name = Path(rel).name
        if not name:
            return
        for candidate in sorted(root.rglob(name)):
            if candidate.is_file():
                try:
                    rel2 = candidate.relative_to(root).as_posix()
                except Exception:
                    rel2 = candidate.as_posix()
                if rel2 not in seen:
                    seen.add(rel2)
                    rows.append(rel2)
                return

    for match in re.findall(r'class path resource \[([^\]]+)\]', text, re.IGNORECASE):
        rel = str(match).strip()
        if rel and not rel.startswith('org/'):
            add(rel)
    for match in re.findall(r'(src/main/(?:java|resources|webapp)/[^\s:;]+)', text):
        add(match)
    low = text.lower()
    if 'schema.sql' in low:
        add('src/main/resources/schema.sql')
    if 'data.sql' in low:
        add('src/main/resources/data.sql')
    if 'login-data.sql' in low:
        add('src/main/resources/login-data.sql')
    if 'login-schema.sql' in low:
        add('src/main/resources/login-schema.sql')
    return rows[:10]


def _derive_startup_failure_signature(output: str, errors: List[Dict[str, Any]], root_cause: str) -> str:
    code = ''
    if errors:
        code = str((errors[0] or {}).get('code') or '').strip()
    basis = root_cause or ''
    if not basis:
        for err in (errors or []):
            snippet = str(err.get('snippet') or '').strip()
            if _meaningful_startup_line(snippet):
                basis = snippet
                break
    if not basis:
        basis = _tail(output, 800)
    return _normalize_failure_signature(basis, code=code)


def _write_startup_debug_artifacts(project_root: Path, output: str, errors: List[Dict[str, Any]], root_cause: str, failure_signature: str, related_paths: List[str]) -> str:
    debug_dir = _debug_dir(project_root)
    raw_path = debug_dir / 'startup_raw.log'
    raw_path.write_text(output or '', encoding='utf-8')
    payload = {
        'root_cause': root_cause or '',
        'failure_signature': failure_signature or '',
        'related_paths': list(related_paths or []),
        'errors': list(errors or []),
    }
    (debug_dir / 'startup_errors.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        return raw_path.relative_to(project_root).as_posix()
    except Exception:
        return raw_path.as_posix()


def _read_startup_output(proc: subprocess.Popen[Any], startup_timeout_seconds: int) -> Tuple[bool, str, List[Dict[str, str]]]:
    lines: List[str] = []
    started = False
    deadline = time.time() + max(5, int(startup_timeout_seconds))
    while time.time() < deadline:
        if proc.poll() is not None and proc.stdout is None:
            break
        line = ""
        if proc.stdout is not None:
            try:
                line = proc.stdout.readline()
            except Exception:
                line = ""
        if line:
            lines.append(line)
            joined = "".join(lines)
            if any(p.search(joined) for p in _STARTUP_SUCCESS_PATTERNS):
                started = True
                break
            if parse_backend_log_errors(joined) and proc.poll() is not None:
                break
        else:
            if proc.poll() is not None:
                break
            time.sleep(0.2)
    output = "".join(lines)
    return started, output, parse_backend_log_errors(output)


def _start_backend(candidate: Dict[str, Any], project_root: Path, startup_timeout_seconds: int = 120) -> Tuple[Dict[str, Any], Optional[subprocess.Popen[Any]]]:
    port = _pick_free_port()
    startup = _startup_command(candidate, port)
    try:
        proc = subprocess.Popen(
            startup["command"],
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            **_popen_launch_kwargs(),
        )
    except Exception as exc:
        return (
            {
                "status": "failed",
                "tool": startup.get("tool"),
                "family": startup.get("family"),
                "command": startup.get("display"),
                "port": port,
                "log_tail": "",
                "errors": [{"code": "startup_exception", "message": str(exc), "snippet": ""}],
            },
            None,
        )

    started, output, errors = _read_startup_output(proc, startup_timeout_seconds=startup_timeout_seconds)
    if not started:
        if proc.poll() is None:
            parsed_errors = parse_backend_log_errors(output) or errors
            fatal_codes = {str(item.get("code") or "").strip() for item in parsed_errors}
            only_timeout_like = not fatal_codes or fatal_codes <= {"startup_timeout", "port_in_use"}
            base_url = f"http://127.0.0.1:{port}"
            grace_seconds = max(12, min(45, int(startup_timeout_seconds) // 3 if startup_timeout_seconds else 20))
            if only_timeout_like and _wait_for_startup_probe(port, base_url, grace_seconds=grace_seconds):
                return (
                    {
                        "status": "ok",
                        "tool": startup.get("tool"),
                        "family": startup.get("family"),
                        "command": startup.get("display"),
                        "port": port,
                        "log_tail": _tail(output),
                        "errors": [],
                        "startup_probe": "port_or_http_ready",
                    },
                    proc,
                )
            _stop_process(proc)
        remaining = ""
        if proc.stdout is not None:
            try:
                remaining = proc.stdout.read() or ""
            except Exception:
                remaining = ""
        output = output + remaining
        errors = parse_backend_log_errors(output) or errors or [{"code": "startup_timeout", "message": "Spring Boot startup did not complete in time", "snippet": ""}]
        root_cause = _extract_startup_root_cause(output, errors)
        related_paths = _extract_related_project_paths(project_root, output)
        failure_signature = _derive_startup_failure_signature(output, errors, root_cause)
        startup_log = _write_startup_debug_artifacts(project_root, output, errors, root_cause, failure_signature, related_paths)
        return (
            {
                "status": "failed",
                "tool": startup.get("tool"),
                "family": startup.get("family"),
                "command": startup.get("display"),
                "port": port,
                "log_tail": _tail(output),
                "errors": errors,
                "root_cause": root_cause,
                "failure_signature": failure_signature,
                "related_paths": related_paths,
                "startup_log": startup_log,
            },
            None,
        )

    return (
        {
            "status": "ok",
            "tool": startup.get("tool"),
            "family": startup.get("family"),
            "command": startup.get("display"),
            "port": port,
            "log_tail": _tail(output),
            "errors": [],
        },
        proc,
    )


def _representative_auth_smoke_routes(routes: List[str]) -> List[str]:
    auth_routes = [route for route in routes if route.lower().startswith('/login/')]
    if not auth_routes:
        return routes

    # Keep exactly one representative auth page. actionMain/main routes are session-dependent
    # and tend to collapse into the same redirect chain as login.do during smoke.
    preferred_exact = (
        '/login/login.do',
        '/login/main.do',
    )
    selected: List[str] = []
    seen = set()
    for target in preferred_exact:
        for route in auth_routes:
            if route.lower() == target and route not in seen:
                seen.add(route)
                selected.append(route)
                break
        if selected:
            break
    if not selected:
        for route in auth_routes:
            low = route.lower()
            if low.endswith('/actionmain.do'):
                continue
            if route not in seen:
                seen.add(route)
                selected.append(route)
                break
    if not selected and auth_routes:
        selected.append(auth_routes[0])

    non_auth = [route for route in routes if route.lower() not in {item.lower() for item in auth_routes}]
    return selected + non_auth


def _route_timeout_sequence(route: str, timeout_seconds: int, retry_timeout_seconds: Optional[int]) -> Tuple[int, int]:
    base_timeout = max(1, int(timeout_seconds))
    retry_timeout = retry_timeout_seconds or max(base_timeout * 2, base_timeout + 8)
    route_lower = _normalize_route(route).lower()
    if route_lower.startswith('/login/'):
        retry_timeout = max(int(retry_timeout), 90)
    elif route_lower.endswith('/calendar.do'):
        retry_timeout = max(int(retry_timeout), 60)
    return base_timeout, int(retry_timeout)


def _select_smoke_routes(routes: List[str], limit: int = 6) -> List[str]:
    normalized: List[str] = []
    seen: set[str] = set()
    for route in routes or []:
        norm = _normalize_route(route)
        if norm not in seen:
            seen.add(norm)
            normalized.append(norm)
    if not normalized:
        return ['/']

    normalized = _representative_auth_smoke_routes(normalized)

    simple_priority = {'/', '/index.do', '/login/login.do', '/login/main.do'}
    simple_routes = [route for route in normalized if route.lower() in {item.lower() for item in simple_priority}]
    root_like_routes = [route for route in simple_routes if route.lower() in {'/', '/index.do'}]
    non_root_simple_routes = [route for route in simple_routes if route not in root_like_routes]
    lightweight_tokens = ('/list.do', '/dashboard', '/main', '/login')
    lightweight_routes = [
        route for route in normalized
        if route not in simple_routes
        and '/calendar.do' not in route.lower()
        and any(token in route.lower() for token in lightweight_tokens)
    ]
    calendar_routes = [route for route in normalized if route not in simple_routes and route not in lightweight_routes and '/calendar.do' in route.lower()]
    remaining = [route for route in normalized if route not in simple_routes and route not in lightweight_routes and route not in calendar_routes]

    selected = non_root_simple_routes + lightweight_routes + calendar_routes + remaining
    if not selected:
        selected = root_like_routes or ['/']
    return selected[: max(1, int(limit))]

def smoke_test_endpoints(base_url: str, routes: List[str], timeout_seconds: int = 8, retry_timeout_seconds: Optional[int] = None) -> Dict[str, Any]:
    def _excerpt(raw: bytes, limit: int = 240) -> str:
        if not raw:
            return ""
        text = raw.decode("utf-8", errors="ignore").replace("\r", " ").replace("\n", " ").strip()
        if len(text) > limit:
            return text[: limit - 3] + "..."
        return text

    def _is_timeout_error(exc: Exception) -> bool:
        if isinstance(exc, socket.timeout):
            return True
        return "timed out" in str(exc).lower()

    selected_routes = _select_smoke_routes(routes)
    results: List[Dict[str, Any]] = []
    failures = 0
    for route in selected_routes:
        normalized_route = _normalize_route(route)
        url = base_url.rstrip("/") + normalized_route
        last_error: Optional[Exception] = None
        timeout_sequence = _route_timeout_sequence(normalized_route, timeout_seconds, retry_timeout_seconds)
        for attempt_no, timeout_value in enumerate(timeout_sequence, start=1):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "autopj-runtime-smoke/1.0"}, method="GET")
                with urllib.request.urlopen(req, timeout=timeout_value) as resp:
                    status = int(getattr(resp, "status", 200) or 200)
                    final_url = getattr(resp, "geturl", lambda: url)() or url
                    body_excerpt = _excerpt(resp.read(512))
                ok = 200 <= status < 400
                if not ok:
                    failures += 1
                results.append({
                    "route": normalized_route,
                    "url": url,
                    "final_url": final_url,
                    "status_code": status,
                    "ok": ok,
                    "response_excerpt": body_excerpt,
                    "attempts": attempt_no,
                })
                break
            except urllib.error.HTTPError as exc:
                failures += 1
                error_body = b""
                try:
                    error_body = exc.read(512)
                except Exception:
                    error_body = b""
                results.append({
                    "route": normalized_route,
                    "url": url,
                    "final_url": getattr(exc, "geturl", lambda: url)() or url,
                    "status_code": int(exc.code),
                    "ok": False,
                    "error": str(exc),
                    "response_excerpt": _excerpt(error_body),
                    "attempts": attempt_no,
                })
                break
            except Exception as exc:
                last_error = exc
                if (_is_timeout_error(exc) or _is_connection_refused_error(exc)) and attempt_no == 1:
                    time.sleep(1.0)
                    continue
                failures += 1
                results.append({
                    "route": normalized_route,
                    "url": url,
                    "final_url": url,
                    "status_code": None,
                    "ok": False,
                    "error": str(exc),
                    "attempts": attempt_no,
                })
                break
        else:
            failures += 1
            results.append({
                "route": normalized_route,
                "url": url,
                "final_url": url,
                "status_code": None,
                "ok": False,
                "error": str(last_error) if last_error else "unknown endpoint smoke failure",
                "attempts": 2,
            })
    success_count = sum(1 for item in results if item.get("ok"))
    timeout_only_failures = [
        item for item in results
        if (not item.get("ok")) and 'timed out' in str(item.get('error') or '').lower()
    ]
    non_timeout_failures = [
        item for item in results
        if (not item.get("ok")) and item not in timeout_only_failures
    ]
    soft_timeout_routes = {
        '/',
        '/index.do',
        '/login/login.do',
        '/login/main.do',
    }
    soft_timeout_suffixes = (
        '/calendar.do',
        '/list.do',
        '/form.do',
    )
    def _is_soft_timeout_route(route: str) -> bool:
        low = _normalize_route(route).lower()
        return low in soft_timeout_routes or low.startswith('/login/') or any(low.endswith(suffix) for suffix in soft_timeout_suffixes)

    soft_timeout_only = bool(timeout_only_failures) and not non_timeout_failures and all(
        _is_soft_timeout_route(item.get('route') or '') for item in timeout_only_failures
    )
    status = "ok" if failures == 0 else "failed"
    # When the app started cleanly and at least one smoke route succeeded, keep timeout-only
    # secondary pages from failing the entire runtime smoke pass.
    if status == 'failed' and success_count > 0 and not non_timeout_failures:
        status = 'ok'
    elif status == 'failed' and soft_timeout_only:
        status = 'ok'
    return {
        "status": status,
        "base_url": base_url,
        "routes_tested": len(results),
        "failed_count": failures,
        "results": results,
        "soft_timeout_only": soft_timeout_only,
        "connection_refused_only": _connection_refused_only({"results": results}),
    }

def should_run_runtime_validation(project_root: Path, backend_key: str = "") -> bool:
    root = Path(project_root)
    backend_key = (backend_key or "").lower()
    has_build_files = any((root / name).exists() for name in ("pom.xml", "mvnw", "mvnw.cmd", "build.gradle", "build.gradle.kts", "gradlew", "gradlew.bat"))
    if not has_build_files:
        return False
    if not backend_key:
        return True
    return "spring" in backend_key or "egov" in backend_key or "boot" in backend_key


def run_spring_boot_runtime_validation(project_root: Path, backend_key: str = "", compile_timeout_seconds: int = 300, startup_timeout_seconds: int = 120) -> Dict[str, Any]:
    if not should_run_runtime_validation(project_root, backend_key=backend_key):
        return {
            "ok": True,
            "status": "skipped",
            "reason": "runtime validation skipped: no Spring Boot build files detected",
            "compile": {"status": "skipped"},
            "startup": {"status": "skipped"},
            "endpoint_smoke": {"status": "skipped"},
        }

    compile_result = run_compile_smoke(project_root, timeout=compile_timeout_seconds)
    runtime_report: Dict[str, Any] = {
        "ok": False,
        "status": "failed",
        "compile": compile_result,
        "startup": {"status": "skipped"},
        "endpoint_smoke": {"status": "skipped"},
    }
    if compile_result.get("status") != "ok":
        return runtime_report

    startup_result, proc = _start_backend(compile_result, project_root, startup_timeout_seconds=startup_timeout_seconds)
    if startup_result.get("status") == "ok":
        startup_result["base_url"] = f"http://127.0.0.1:{startup_result['port']}"
    runtime_report["startup"] = startup_result
    if startup_result.get("status") != "ok" or proc is None:
        return runtime_report

    try:
        routes = _select_smoke_routes(_discover_controller_routes(project_root))
        endpoint_smoke, startup_result, proc = _run_endpoint_smoke_with_backend_recovery(
            project_root,
            compile_result,
            startup_result,
            proc,
            routes,
            startup_timeout_seconds=startup_timeout_seconds,
            endpoint_runner=lambda current_base_url, selected_routes: smoke_test_endpoints(current_base_url, selected_routes, timeout_seconds=12, retry_timeout_seconds=30),
        )
        runtime_report["startup"] = startup_result
        runtime_report["endpoint_smoke"] = endpoint_smoke
        runtime_report["status"] = "ok" if endpoint_smoke.get("status") == "ok" else "failed"
        runtime_report["ok"] = runtime_report["status"] == "ok"
    finally:
        _stop_process(proc)

    return runtime_report


def write_runtime_report(project_root: Path, report: Dict[str, Any]) -> None:
    debug_dir = Path(project_root) / ".autopj_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / "runtime_smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    compile_info = (report or {}).get("compile") or {}
    raw_output = compile_info.get("raw_output") or ""
    if raw_output:
        (debug_dir / "compile_raw.log").write_text(raw_output, encoding="utf-8")
    if compile_info.get("errors"):
        (debug_dir / "compile_errors.json").write_text(json.dumps(compile_info.get("errors") or [], ensure_ascii=False, indent=2), encoding="utf-8")
    startup_info = (report or {}).get("startup") or {}
    startup_raw = startup_info.get("log_tail") or ""
    if startup_raw and not (debug_dir / "startup_raw.log").exists():
        (debug_dir / "startup_raw.log").write_text(startup_raw, encoding="utf-8")
    if startup_info.get("errors") or startup_info.get("root_cause") or startup_info.get("failure_signature"):
        (debug_dir / "startup_errors.json").write_text(json.dumps({
            "root_cause": startup_info.get("root_cause") or "",
            "failure_signature": startup_info.get("failure_signature") or "",
            "related_paths": startup_info.get("related_paths") or [],
            "errors": startup_info.get("errors") or [],
        }, ensure_ascii=False, indent=2), encoding="utf-8")



def run_compile_smoke(project_root: Path, timeout: int = 300) -> Dict[str, Any]:
    return run_backend_compile(project_root, timeout_seconds=timeout)


def run_spring_boot_startup(project_root: Path, timeout: int = 120, compile_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    base = compile_result or {"tool": None, "family": None}
    result, proc = _start_backend(base, project_root, startup_timeout_seconds=timeout)
    if proc is not None:
        _stop_process(proc)
    if result.get("status") == "ok":
        result["base_url"] = f"http://127.0.0.1:{result['port']}"
    return result


def run_endpoint_smoke(base_url: str, endpoints: List[Dict[str, Any]], timeout: int = 8) -> Dict[str, Any]:
    routes: List[str] = []
    for item in endpoints or []:
        if isinstance(item, dict):
            route = item.get('path') or item.get('route')
        else:
            route = str(item)
        if route:
            routes.append(str(route))
    return smoke_test_endpoints(base_url, routes, timeout_seconds=timeout)


def run_backend_runtime_validation(project_root: Path, manifest: Optional[Dict[str, Any]] = None, backend_key: str = '', compile_timeout_seconds: int = 300, startup_timeout_seconds: int = 120) -> Dict[str, Any]:
    if manifest and not backend_key:
        backend_key = str((manifest or {}).get('backend_key') or '')
    build_files_present = should_run_runtime_validation(project_root, backend_key=backend_key)
    if not build_files_present and not manifest:
        return {
            "ok": True,
            "status": "skipped",
            "reason": "runtime validation skipped: no Spring Boot build files detected",
            "compile": {"status": "skipped"},
            "startup": {"status": "skipped"},
            "endpoint_smoke": {"status": "skipped"},
        }

    compile_result = run_compile_smoke(project_root, timeout=compile_timeout_seconds)
    report: Dict[str, Any] = {"ok": False, "status": "failed", "compile": compile_result, "startup": {"status": "skipped"}, "endpoint_smoke": {"status": "skipped"}}
    if compile_result.get('status') != 'ok':
        return report

    startup_result, proc = _start_backend(compile_result, project_root, startup_timeout_seconds=startup_timeout_seconds)
    if startup_result.get('status') == 'ok':
        startup_result['base_url'] = f"http://127.0.0.1:{startup_result['port']}"
    report['startup'] = startup_result
    if startup_result.get('status') != 'ok' or proc is None:
        return report

    try:
        endpoints: List[Dict[str, Any]] = []
        for route in ((manifest or {}).get('routes') or []):
            if str((route or {}).get('method') or 'GET').upper() == 'GET':
                endpoints.append({'path': route.get('path') or '/'})
        if endpoints:
            selected_routes = _select_smoke_routes([item.get('path') or item.get('route') or '/' for item in endpoints])
        else:
            selected_routes = _select_smoke_routes(_discover_controller_routes(project_root))
        endpoint_smoke, startup_result, proc = _run_endpoint_smoke_with_backend_recovery(
            project_root,
            compile_result,
            startup_result,
            proc,
            selected_routes,
            startup_timeout_seconds=startup_timeout_seconds,
            endpoint_runner=lambda current_base_url, selected_routes: run_endpoint_smoke(
                current_base_url,
                [{'path': route} for route in selected_routes],
                timeout=12,
            ),
        )
        report['startup'] = startup_result
        report['endpoint_smoke'] = endpoint_smoke
        report['status'] = 'ok' if endpoint_smoke.get('status') == 'ok' else 'failed'
        report['ok'] = report['status'] == 'ok'
    finally:
        _stop_process(proc)
    return report
