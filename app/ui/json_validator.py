# path: app/ui/json_validator.py
from __future__ import annotations

import json
import re
from typing import Tuple, Optional


TEMPLATE_MANAGED_PATHS = {
    "pom.xml",
    "mvnw",
    "mvnw.cmd",
    "gradlew",
    "gradlew.bat",
    ".mvn/wrapper/maven-wrapper.properties",
    "src/main/resources/application.properties",
    "src/main/resources/application.yml",
    "src/main/resources/application.yaml",
}

SPECIAL_COMMENTLESS_PATHS = {
    "mvnw",
    "mvnw.cmd",
    "gradlew",
    "gradlew.bat",
    "dockerfile",
}

COMMENTLESS_EXTS = {".json", ".env", ".txt", ".java", ".js", ".jsx", ".ts", ".tsx", ".py", ".ps1", ".sh", ".bat", ".cmd", ".yml", ".yaml", ".properties", ".sql", ".xml", ".jsp", ".html", ".vue", ".css", ".md", ".xfdl", ".xjs"}
COMMENT_PREFIX_BY_EXT = {
    ".java": "// path:",
    ".js": "// path:",
    ".jsx": "// path:",
    ".ts": "// path:",
    ".tsx": "// path:",
    ".py": "# path:",
    ".ps1": "// path:",
    ".sh": "# path:",
    ".cmd": "REM path:",
    ".bat": "REM path:",
    ".yml": "# path:",
    ".yaml": "# path:",
    ".properties": "# path:",
    ".sql": "-- path:",
    ".xml": "<!-- path:",
    ".jsp": "<!-- path:",
    ".html": "<!-- path:",
    ".vue": "<!-- path:",
    ".css": "/* path:",
    ".md": "<!-- path:",
}


def _ext_of(path: str) -> str:
    p = (path or "").lower().strip().replace("\\", "/")
    name = p.rsplit("/", 1)[-1]
    if name == "pom.xml":
        return ".xml"
    if name == ".env" or name.startswith(".env.") or name == "env" or name.startswith("env."):
        return ".env"
    dot = name.rfind(".")
    if dot == -1:
        return ""
    return name[dot:]



def _normalize_path_text(path: str) -> str:
    p = (path or "").strip()
    if not p:
        return ""
    m = re.fullmatch(r"<path>\s*([\s\S]*?)\s*</path>", p, re.IGNORECASE)
    if m:
        p = (m.group(1) or "").strip()
    return p.replace("\\", "/").strip()

def validate_file_ops_json(
    text: str,
    frontend_key: Optional[str] = None,
) -> Tuple[bool, str]:
    """Gemini 출력이 file-op JSON 배열인지 검증.

    규칙:
    - 확장자별 path 주석 문법을 검증한다.
    - 단, JSON(.json) 등 주석 불가 타입은 검사 생략한다.
    - React/Vue 선택 시 JSP 생성 금지(하드 FAIL).
    """

    s = (text or "").strip()
    if not s:
        return False, "empty output"

    try:
        data = json.loads(s)
    except Exception as e:
        return False, f"JSON parse 실패: {repr(e)}"

    if not isinstance(data, list):
        return False, "최상위는 JSON 배열(list)이어야 합니다."

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            return False, f"items[{i}]는 객체(dict)여야 합니다."

        for k in ("path", "purpose", "content"):
            if k not in item:
                return False, f"items[{i}]에 '{k}' 키가 없습니다."
            if not isinstance(item[k], str):
                return False, f"items[{i}].{k}는 문자열(str)이어야 합니다."

        path = _normalize_path_text(item["path"])
        if not path:
            return False, f"items[{i}].path가 비어있습니다."

        # Hard rule: non-JSP frontend 선택 시 JSP 생성 금지
        if frontend_key in ("react", "vue", "nexacro"):
            if "/webapp/" in path.lower() and path.lower().endswith(".jsp"):
                return False, f"{frontend_key} 선택 상태에서 JSP 파일이 생성되었습니다: {path}"
            if path.lower().endswith(".jsp"):
                return False, f"{frontend_key} 선택 상태에서 JSP 파일이 생성되었습니다: {path}"

        ext = _ext_of(path)
        path_key = path.lower().strip().replace("\\", "/")
        content = item["content"] or ""

        if path_key in SPECIAL_COMMENTLESS_PATHS or ext in COMMENTLESS_EXTS:
            continue

        expected = COMMENT_PREFIX_BY_EXT.get(ext, "// path:")
        first_line = content.splitlines()[0].lstrip() if content else ""

        if not first_line.lower().startswith(expected):
            return False, (
                f"items[{i}].content 첫 줄 path 주석이 필요합니다. "
                f"(expected prefix: '{expected}' for path='{path}')"
            )

    return True, ""

def _looks_like_code(content: str, ext: str) -> bool:
    c = (content or "").strip()
    if not c:
        return False

    # Planner는 "완성 파일"을 내면 안 됨: path 주석으로 시작하면 무조건 코드로 간주
    if c.startswith("// path:") or c.startswith("<!-- path:") or c.startswith("# path:") or c.startswith("-- path:") or c.startswith("/* path:"):
        return True

    # 라인 단위 정규식(라인 시작에서만 코드 패턴을 잡는다)
    if ext == ".java":
        java_code_patterns = [
            r"(?m)^\s*package\s+[\w\.]+\s*;",                 # package xxx.yyy;
            r"(?m)^\s*import\s+[\w\.]+\s*;",                  # import xxx.yyy;
            r"(?m)^\s*@\w+(\(.*\))?\s*$",                     # @Annotation
            r"(?m)^\s*(public|protected|private)?\s*(class|interface|enum)\s+\w+.*\{",  # class ... {
            r"(?m)^\s*(public|protected|private)\s+[\w\<\>\[\]]+\s+\w+\s*\(.*\)\s*\{", # method(...) {
        ]
        return any(re.search(p, c) for p in java_code_patterns)

    if ext in (".xml", ".jsp", ".html", ".vue"):
        markup_patterns = [
            r"(?m)^\s*<\?xml\b",          # XML declaration
            r"(?m)^\s*<%@\b",             # JSP directive
            r"(?m)^\s*</\w+",             # closing tag
            r"(?m)^\s*<\w+[^>]*>",        # opening tag
        ]
        return any(re.search(p, c) for p in markup_patterns)

    if ext in (".js", ".jsx", ".ts", ".tsx"):
        js_patterns = [
            r"(?m)^\s*import\s+.+\s+from\s+['\"].+['\"];?\s*$",
            r"(?m)^\s*export\s+",
            r"(?m)^\s*(const|let|var)\s+\w+\s*=",
            r"(?m)^\s*function\s+\w+\s*\(",
            r"(?m)^\s*return\s+",
        ]
        return any(re.search(p, c) for p in js_patterns)

    # default: 강한 코드 시그니처(중괄호 블록)만 코드로 처리
    if re.search(r"(?m)^\s*\{.*$", c) and re.search(r"(?m)^\s*\}.*$", c):
        return True

    return False


def validate_plan_json(
    text: str,
    frontend_key: Optional[str] = None,
) -> Tuple[bool, str]:
    """Gemini Planner 출력(= 파일 스펙 JSON 배열) 검증.

    규칙:
    - 최상위 JSON 배열(list)
    - 각 item은 {path,purpose,content} 문자열
    - content는 '코드'가 아니라 '스펙'이어야 함
    - React/Vue 선택 시 JSP 계획 금지
    """

    s = (text or "").strip()
    if not s:
        return False, "empty output"

    try:
        data = json.loads(s)
    except Exception as e:
        return False, f"JSON parse 실패: {repr(e)}"

    if not isinstance(data, list):
        return False, "최상위는 JSON 배열(list)이어야 합니다."

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            return False, f"items[{i}]는 객체(dict)여야 합니다."

        for k in ("path", "purpose", "content"):
            if k not in item:
                return False, f"items[{i}]에 '{k}' 키가 없습니다."
            if not isinstance(item[k], str):
                return False, f"items[{i}].{k}는 문자열(str)이어야 합니다."

        path = item["path"].strip().replace("\\", "/")
        if not path:
            return False, f"items[{i}].path가 비어있습니다."

        if path.lower() in TEMPLATE_MANAGED_PATHS:
            return False, f"템플릿 파일은 Planner 출력에 포함하면 안 됩니다: {path}"

        if frontend_key in ("react", "vue", "nexacro") and path.lower().endswith(".jsp"):
            return False, f"{frontend_key} 선택 상태에서 JSP 파일이 계획되었습니다: {path}"

        content = (item.get("content") or "").strip()
        ext = _ext_of(path)
        # content should be short spec, not code
        if len(content) > 1200:
            return False, f"items[{i}].content가 너무 깁니다(스펙은 1200자 이내 권장): {path}"
        if _looks_like_code(content, ext):
            return False, f"items[{i}] Planner content가 코드 형태입니다(스펙만 필요): {path}"

    return True, ""
