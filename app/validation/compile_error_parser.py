from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_MAVEN_ERROR_RE = re.compile(
    r"^\s*\[ERROR\]\s+(?P<path>.*?\.java):\[(?P<line>\d+),(?P<column>\d+)\]\s+(?P<message>.+?)\s*$",
    re.MULTILINE,
)

_GRADLE_ERROR_RE = re.compile(
    r"^\s*(?P<path>.*?\.java):(?P<line>\d+):\s+error:\s+(?P<message>.+?)\s*$",
    re.MULTILINE,
)

_XML_ERROR_RE = re.compile(
    r"^\s*\[ERROR\]\s+(?P<path>.*?(?:Mapper\.xml|\.xml)):\[(?P<line>\d+),(?P<column>\d+)\]\s+(?P<message>.+?)\s*$",
    re.MULTILINE,
)

_SYMBOL_RE = re.compile(r"cannot find symbol(?:\s*symbol:\s*(?P<symbol>.+))?", re.IGNORECASE)
_PACKAGE_RE = re.compile(r"package\s+([^\s]+)\s+does not exist", re.IGNORECASE)
_INCOMPATIBLE_RE = re.compile(r"incompatible types?:\s*(.+)", re.IGNORECASE)
_DUPLICATE_RE = re.compile(r"duplicate class:\s*(.+)", re.IGNORECASE)
_OVERRIDE_RE = re.compile(r"does not override|method does not override", re.IGNORECASE)
_PRIMITIVE_OPTIONAL_RE = re.compile(r"Optional\s+\w+\s+parameter.+primitive type", re.IGNORECASE)

_BOOTSTRAP_HINTS = (
    ("maven_wrapper_bootstrap", re.compile(r"(?:Invoke-WebRequest|Expand-Archive).*(?:mvnw\.cmd|Maven)|\[mvnw\.cmd\].*(?:다운로드|압축 해제)|invalid characters in the path|경로에 잘못된 문자가 있습니다", re.IGNORECASE), "Maven wrapper bootstrap failed"),
    ("maven_wrapper_download", re.compile(r"(?:repo\.maven|apache-maven-\d|download).*(?:mvnw|wrapper)|\[mvnw(?:\.cmd)?\].*download", re.IGNORECASE), "Maven wrapper download failed"),
    ("pom_parse_error", re.compile(r"Non-parseable POM|Malformed POM|Failed to read artifact descriptor|Could not resolve dependencies for project", re.IGNORECASE), "Maven build configuration failed"),
    ("build_tool_missing", re.compile(r"(?:mvn|gradle|wrapper).*(?:not recognized|not found|No such file or directory)", re.IGNORECASE), "Build tool missing or not executable"),
)


def _normalize_path(raw: str, project_root: Optional[Path]) -> str:
    path = (raw or "").strip().replace('\\', '/')
    if not path:
        return path
    if project_root:
        proj = str(project_root).replace('\\', '/')
        if path.startswith(proj + '/'):
            path = path[len(proj) + 1:]
    idx = path.find('/src/')
    if idx != -1:
        path = path[idx + 1:]
    while path.startswith('./'):
        path = path[2:]
    while path.startswith('.\\'):
        path = path[2:]
    return path



def _classify_error(message: str) -> str:
    msg = message or ""
    if _SYMBOL_RE.search(msg):
        return 'cannot_find_symbol'
    if _PACKAGE_RE.search(msg):
        return 'package_missing'
    if _INCOMPATIBLE_RE.search(msg):
        return 'incompatible_types'
    if _DUPLICATE_RE.search(msg):
        return 'duplicate_class'
    if _OVERRIDE_RE.search(msg):
        return 'override_mismatch'
    if _PRIMITIVE_OPTIONAL_RE.search(msg):
        return 'optional_primitive_param'
    if 'package ' in msg and ' does not exist' in msg:
        return 'package_missing'
    if 'cannot find symbol' in msg.lower():
        return 'cannot_find_symbol'
    return 'compile_error'



def _extract_symbol(message: str) -> str:
    if not message:
        return ''
    m = _SYMBOL_RE.search(message)
    if m and m.group('symbol'):
        return m.group('symbol').strip()
    m = _PACKAGE_RE.search(message)
    if m:
        return m.group(1).strip()
    m = _DUPLICATE_RE.search(message)
    if m:
        return m.group(1).strip()
    return ''



def _detect_bootstrap_errors(log_text: str) -> List[Dict[str, Any]]:
    text = log_text or ''
    found: List[Dict[str, Any]] = []
    seen = set()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    joined = '\n'.join(lines)
    for code, pattern, message in _BOOTSTRAP_HINTS:
        m = pattern.search(joined)
        if not m or code in seen:
            continue
        seen.add(code)
        snippet = ''
        for line in lines:
            if pattern.search(line):
                snippet = line[:400]
                break
        path = ''
        if code.startswith('maven_wrapper_'):
            path = 'mvnw.cmd' if 'mvnw.cmd' in joined.lower() or 'Invoke-WebRequest' in joined or 'Expand-Archive' in joined else 'mvnw'
        elif code == 'pom_parse_error':
            path = 'pom.xml'
        found.append({
            'code': code,
            'path': path,
            'line': None,
            'column': None,
            'message': message,
            'symbol': '',
            'snippet': snippet or message,
        })
    return found



def parse_compile_errors(log_text: str, project_root: Optional[Path] = None) -> List[Dict[str, Any]]:
    text = log_text or ''
    found: List[Dict[str, Any]] = []
    seen = set()
    patterns = (_MAVEN_ERROR_RE, _GRADLE_ERROR_RE, _XML_ERROR_RE)
    for pattern in patterns:
        for m in pattern.finditer(text):
            rel_path = _normalize_path(m.group('path'), project_root)
            line = int(m.group('line')) if m.groupdict().get('line') else None
            column = int(m.group('column')) if m.groupdict().get('column') else None
            message = (m.group('message') or '').strip()
            key = (rel_path, line, column, message)
            if key in seen:
                continue
            seen.add(key)
            found.append({
                'code': _classify_error(message),
                'path': rel_path,
                'line': line,
                'column': column,
                'message': message,
                'symbol': _extract_symbol(message),
                'snippet': (m.group(0) or '').strip()[:400],
            })
    if not found and 'cannot find symbol' in text.lower():
        for raw_line in text.splitlines():
            if 'cannot find symbol' in raw_line.lower():
                found.append({
                    'code': 'cannot_find_symbol',
                    'path': '',
                    'line': None,
                    'column': None,
                    'message': raw_line.strip(),
                    'symbol': _extract_symbol(raw_line),
                    'snippet': raw_line.strip()[:400],
                })
                break
    bootstrap = _detect_bootstrap_errors(text)
    for item in bootstrap:
        key = (item.get('path') or '', item.get('code') or '', item.get('message') or '')
        if key in seen:
            continue
        seen.add(key)
        found.append(item)
    return found



def summarize_compile_errors(errors: List[Dict[str, Any]], limit: int = 10) -> List[str]:
    lines: List[str] = []
    for item in (errors or [])[: max(1, int(limit))]:
        path = (item.get('path') or '').strip()
        line = item.get('line')
        message = (item.get('message') or item.get('snippet') or 'compile error').strip()
        if path and line:
            lines.append(f"{path}:{line} {message}")
        elif path:
            lines.append(f"{path} {message}")
        else:
            lines.append(message)
    return lines



def compile_error_paths(errors: List[Dict[str, Any]]) -> List[str]:
    seen = set()
    paths: List[str] = []
    for item in errors or []:
        path = (item.get('path') or '').replace('\\', '/').strip()
        while path.startswith('./'):
            path = path[2:]
        while path.startswith('.\\'):
            path = path[2:]
        if path and path not in seen:
            seen.add(path)
            paths.append(path)
    return paths
