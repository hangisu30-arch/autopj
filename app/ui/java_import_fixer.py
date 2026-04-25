from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Dict, List, Set, Tuple

_PKG_RE = re.compile(r"^\s*package\s+([a-zA-Z0-9_.]+)\s*;\s*$", re.MULTILINE)
_IMPORT_RE = re.compile(r"^\s*import\s+([a-zA-Z0-9_.*]+)\s*;\s*$", re.MULTILINE)
_PUBLIC_TYPE_RE = re.compile(r"\bpublic\s+(class|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_ANY_TOP_TYPE_RE = re.compile(r"\b(class|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_DECLARED_TYPE_RE = re.compile(r"\b(?:class|interface|enum|record)\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_CAP_TOKEN_RE = re.compile(r"\b([A-Z][A-Za-z0-9_]*)\b")

JAVA_LANG_TYPES: Set[str] = {
    "String", "Integer", "Long", "Double", "Float", "Short", "Byte", "Boolean", "Character",
    "Object", "Exception", "RuntimeException", "IllegalArgumentException", "IllegalStateException",
    "Override", "Deprecated", "SuppressWarnings", "FunctionalInterface", "Iterable", "Comparable",
    "System", "Math", "Thread", "Void"
}

STANDARD_IMPORTS: Dict[str, str] = {
    "List": "java.util.List",
    "ArrayList": "java.util.ArrayList",
    "LinkedList": "java.util.LinkedList",
    "Map": "java.util.Map",
    "HashMap": "java.util.HashMap",
    "LinkedHashMap": "java.util.LinkedHashMap",
    "Set": "java.util.Set",
    "HashSet": "java.util.HashSet",
    "LinkedHashSet": "java.util.LinkedHashSet",
    "Optional": "java.util.Optional",
    "Collections": "java.util.Collections",
    "Collection": "java.util.Collection",
    "Date": "java.util.Date",
    "LocalDate": "java.time.LocalDate",
    "LocalDateTime": "java.time.LocalDateTime",
    "LocalTime": "java.time.LocalTime",
    "BigDecimal": "java.math.BigDecimal",
    "Timestamp": "java.sql.Timestamp",
    "Autowired": "org.springframework.beans.factory.annotation.Autowired",
    "Service": "org.springframework.stereotype.Service",
    "Controller": "org.springframework.stereotype.Controller",
    "RestController": "org.springframework.web.bind.annotation.RestController",
    "RequestMapping": "org.springframework.web.bind.annotation.RequestMapping",
    "GetMapping": "org.springframework.web.bind.annotation.GetMapping",
    "PostMapping": "org.springframework.web.bind.annotation.PostMapping",
    "RequestParam": "org.springframework.web.bind.annotation.RequestParam",
    "PathVariable": "org.springframework.web.bind.annotation.PathVariable",
    "ModelAttribute": "org.springframework.web.bind.annotation.ModelAttribute",
    "ResponseBody": "org.springframework.web.bind.annotation.ResponseBody",
    "Mapper": "org.apache.ibatis.annotations.Mapper",
    "Param": "org.apache.ibatis.annotations.Param",
    "Repository": "org.springframework.stereotype.Repository",
}

@dataclass(frozen=True)
class ClassInfo:
    name: str
    fqn: str
    file: Path

def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return p.read_text(encoding="utf-8", errors="ignore")

def _get_package(java: str) -> str:
    m = _PKG_RE.search(java or "")
    return (m.group(1) if m else "").strip()

def _get_top_type_name(java: str, fallback: str) -> str:
    m = _PUBLIC_TYPE_RE.search(java or "")
    if m:
        return m.group(2)
    m2 = _ANY_TOP_TYPE_RE.search(java or "")
    if m2:
        return m2.group(2)
    return fallback

def build_class_index(src_main_java: Path) -> Dict[str, List[ClassInfo]]:
    index: Dict[str, List[ClassInfo]] = {}
    if not src_main_java.exists():
        return index
    for f in src_main_java.rglob("*.java"):
        if not f.is_file():
            continue
        text = _read_text(f)
        pkg = _get_package(text)
        name = _get_top_type_name(text, f.stem)
        if not pkg or not name:
            continue
        fqn = f"{pkg}.{name}"
        index.setdefault(name, []).append(ClassInfo(name=name, fqn=fqn, file=f))
    return index

def _choose_best_fqn(cands: List[ClassInfo]) -> str:
    if not cands:
        return ""
    no_vo = [c for c in cands if ".vo." not in c.fqn]
    use = no_vo or cands
    use_sorted = sorted(use, key=lambda c: (len(c.fqn.split('.')), c.fqn))
    return use_sorted[0].fqn

def _strip_comments_and_strings(java: str) -> str:
    java = re.sub(r"//.*?$", "", java, flags=re.MULTILINE)
    java = re.sub(r"/\*.*?\*/", "", java, flags=re.DOTALL)
    java = re.sub(r'"(?:\\.|[^"\\])*"', '""', java)
    java = re.sub(r"'(?:\\.|[^'\\])'", "''", java)
    return java

def _declared_type_names(java: str, fallback_stem: str = "") -> Set[str]:
    names = set(_DECLARED_TYPE_RE.findall(java or ""))
    top = _get_top_type_name(java, fallback_stem or "")
    if top:
        names.add(top)
    return names

def _same_declared_package(pkg: str, fqn: str) -> bool:
    if not pkg or not fqn or fqn.endswith('.*'):
        return False
    fqn_pkg = '.'.join(fqn.split('.')[:-1])
    return fqn_pkg == pkg


def _infer_missing_imports(java: str, class_index: Dict[str, List[ClassInfo]], pkg: str) -> List[str]:
    declared = _declared_type_names(java)
    cleaned = _strip_comments_and_strings(java)
    existing = set(_IMPORT_RE.findall(java))
    existing_simple = {imp.split('.')[-1] for imp in existing if not imp.endswith('.*')}

    needed: List[str] = []
    seen: Set[str] = set()
    for simple in _CAP_TOKEN_RE.findall(cleaned):
        if simple in declared or simple in JAVA_LANG_TYPES or simple in existing_simple:
            continue

        chosen = ""
        if simple in class_index:
            best = _choose_best_fqn(class_index[simple])
            if best and not _same_declared_package(pkg, best):
                chosen = best
        elif simple in STANDARD_IMPORTS:
            chosen = STANDARD_IMPORTS[simple]

        if chosen and chosen not in existing and chosen not in seen:
            seen.add(chosen)
            needed.append(chosen)
    return needed

def fix_imports_in_java_text(java: str, class_index: Dict[str, List[ClassInfo]]) -> Tuple[str, bool]:
    if not java:
        return java, False

    original = java
    java = re.sub(r"import\s+egovframework\.rte\.fdl\.cmmn\.EgovAbstractServiceImpl\s*;",
                  "import org.egovframe.rte.fdl.cmmn.EgovAbstractServiceImpl;", java)
    java = re.sub(r"import\s+egovframework\.[\w\.]*cmm[\w\.]*EgovAbstractServiceImpl\s*;",
                  "import org.egovframe.rte.fdl.cmmn.EgovAbstractServiceImpl;", java)

    pkg = _get_package(java)
    imports = _IMPORT_RE.findall(java)

    by_simple: Dict[str, List[str]] = {}
    for imp in imports:
        if imp.endswith(".*"):
            by_simple.setdefault(imp, []).append(imp)
            continue
        simple = imp.split(".")[-1]
        by_simple.setdefault(simple, []).append(imp)

    replace_map: Dict[str, str] = {}
    remove_set: Set[str] = set()
    for simple, imps in by_simple.items():
        if simple.endswith(".*") or simple == ".*":
            continue
        uniq = list(dict.fromkeys(imps))
        if len(uniq) <= 1:
            one = uniq[0] if uniq else None
            if one and simple in class_index:
                best = _choose_best_fqn(class_index[simple])
                if best and best != one:
                    replace_map[one] = best
            continue
        best = ""
        if simple in class_index:
            best = _choose_best_fqn(class_index[simple])
        if best:
            for imp in uniq:
                if imp != best:
                    replace_map[imp] = best
        else:
            keep = uniq[0]
            for imp in uniq[1:]:
                remove_set.add(imp)

    new_imports: List[str] = []
    seen: Set[str] = set()
    for old in imports:
        if old in remove_set:
            continue
        new = replace_map.get(old, old)
        if _same_declared_package(pkg, new):
            continue
        if new not in seen:
            seen.add(new)
            new_imports.append(new)

    for missing in _infer_missing_imports(java, class_index, pkg):
        if missing not in seen and not _same_declared_package(pkg, missing):
            seen.add(missing)
            new_imports.append(missing)

    # sort imports for stability
    new_imports = sorted(new_imports)

    if new_imports:
        new_block = "\n".join(f"import {i};" for i in new_imports)
    else:
        new_block = ""

    first = None
    last = None
    for m in _IMPORT_RE.finditer(java):
        if first is None:
            first = m
        last = m

    if first and last:
        start = first.start()
        end = last.end()
        prefix = java[:start].rstrip() + "\n\n"
        suffix = java[end:].lstrip()
        new_text = prefix + (new_block + "\n\n" if new_block else "") + suffix
    else:
        pkg_m = _PKG_RE.search(java)
        if pkg_m:
            insert_at = pkg_m.end()
            before = java[:insert_at].rstrip()
            after = java[insert_at:].lstrip()
            new_text = before + "\n\n" + (new_block + "\n\n" if new_block else "") + after
        else:
            new_text = (new_block + "\n\n" if new_block else "") + java.lstrip()

    return new_text, new_text != original

def fix_project_java_imports(project_root: Path) -> List[Path]:
    src = project_root / "src/main/java"
    index = build_class_index(src)
    changed: List[Path] = []
    if not src.exists():
        return changed
    for f in src.rglob("*.java"):
        if not f.is_file():
            continue
        text = _read_text(f)
        new_text, ok = fix_imports_in_java_text(text, index)
        if ok and new_text != text:
            f.write_text(new_text, encoding="utf-8")
            changed.append(f)
    return changed
