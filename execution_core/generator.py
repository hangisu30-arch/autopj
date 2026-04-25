from __future__ import annotations
from pathlib import Path
import re
from .ollama_client import call_ollama
from .logger import log
from .builtin_crud import infer_entity_from_plan, infer_schema_from_plan, builtin_file, ddl, canonicalize_db_ops, _approval_view
from .feature_rules import classify_feature_kind, is_auth_kind, is_read_only_kind, is_schedule_kind

class GenerationError(Exception):
    pass

_GARBAGE = [
    re.compile(r"begin[^\n]{0,80}sentence", re.IGNORECASE),
    re.compile(r"^Sure,.*?$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^I'm sorry.*?$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"```"),
]

def _strip_garbage(s: str) -> str:
    t = s or ""
    for p in _GARBAGE:
        t = p.sub("", t)
    return t.strip()

def _java_pkg_from_path(abs_path: Path, base_package: str) -> str:
    # Determine expected package based on folder under src/main/java/{base_package}
    # abs_path like .../src/main/java/<pkg>/service/impl/X.java
    rel = str(abs_path).replace("\\","/").split("/src/main/java/")[-1]
    # remove filename
    parts = rel.split("/")
    if len(parts) <= 1:
        return base_package
    pkg_parts = parts[:-1]
    return ".".join(pkg_parts)

def _ensure_package(java: str, pkg: str) -> str:
    if re.search(r"^\s*package\s+[a-zA-Z0-9_\.]+\s*;", java, re.MULTILINE):
        java = re.sub(r"^\s*package\s+[a-zA-Z0-9_\.]+\s*;", f"package {pkg};", java, count=1, flags=re.MULTILINE)
        return java
    return f"package {pkg};\n\n{java.lstrip()}"


def _module_base_from_java_package(pkg: str) -> str:
    for suffix in ('.service.impl', '.service.mapper', '.service.vo', '.service', '.web', '.config'):
        if pkg.endswith(suffix):
            return pkg[:-len(suffix)]
    return pkg


def _rewrite_project_imports(java: str, pkg: str, base_package: str) -> str:
    module_base = _module_base_from_java_package(pkg)

    def _rewrite(m: re.Match) -> str:
        layer = m.group(1)
        name = m.group(2)
        if layer == 'config':
            return f'import {base_package}.config.{name};'
        return f'import {module_base}.{layer}.{name};'

    return re.sub(
        r'import\s+[A-Za-z_][\w\.]*\.(service(?:\.impl|\.mapper|\.vo)?|web|config)\.([A-Za-z_][\w]*)\s*;',
        _rewrite,
        java,
    )

def _force_type_name(java: str, name: str) -> str:
    # Replace the first public class/interface/enum name
    m = re.search(r"\bpublic\s+(class|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)\b", java)
    if not m:
        return java
    old = m.group(2)
    if old == name:
        return java
    java = java.replace(f"public {m.group(1)} {old}", f"public {m.group(1)} {name}", 1)
    # Constructor rename
    java = re.sub(rf"\b{re.escape(old)}\s*\(", f"{name}(", java)
    return java

def _looks_like_jsp(s: str) -> bool:
    t = (s or "").lower()
    return "<%@ page" in t and "<html" in t

def _looks_like_mapper_xml(s: str) -> bool:
    t = (s or "").lower()
    return "<mapper" in t and "namespace" in t


def _looks_like_legacy_ibatis_xml(s: str) -> bool:
    """Detect iBATIS/sqlMap style XML that must NOT be generated in MyBatis-only mode."""
    t = (s or "").lower()
    return (
        "<sqlmap" in t
        or "<beans" in t
        or "sqlmapclient" in t
        or "sqlmapclienttemplate" in t
        or "org.springframework.orm.ibatis" in t
        or "ibatis" in t
    )


def _java_simple_name(logical_path: str) -> str:
    name = (logical_path or "").replace("\\", "/").split("/")[-1]
    return name[:-5] if name.endswith(".java") else name


def _vo_names_in_java(content: str) -> list[str]:
    names = set(re.findall(r"\b([A-Z][A-Za-z0-9_]*VO)\b", content or ""))
    return sorted(names)


def _missing_imports_for_names(content: str, names: list[str], pkg_fragment: str) -> list[str]:
    missing = []
    for name in names:
        pat = rf"^\s*import\s+egovframework\.[A-Za-z0-9_.]+\.{re.escape(pkg_fragment)}\.{re.escape(name)}\s*;"
        if not re.search(pat, content or "", re.MULTILINE):
            missing.append(name)
    return missing


def _missing_list_import(content: str) -> bool:
    return "List<" in (content or "") and not re.search(r"^\s*import\s+java\.util\.List\s*;", content or "", re.MULTILINE)


def _has_mybatis_sql_annotations(content: str) -> bool:
    return bool(re.search(r"@(Select|Insert|Update|Delete|Results|Result|Options|SelectProvider|InsertProvider|UpdateProvider|DeleteProvider)\b", content or ""))


def _invalid_jsp_controller_binding(content: str) -> str:
    for match in re.finditer(r"@ModelAttribute(?:\([^)]*\))?\s+([A-Z][A-Za-z0-9_]*)\s+[a-zA-Z_][A-Za-z0-9_]*", content or ""):
        type_name = match.group(1)
        if not type_name.endswith("VO"):
            return type_name
    return ""


def _mybatis_config_invalid_reason(content: str) -> str:
    text = content or ""
    if "@Configuration" not in text:
        return "missing @Configuration"
    if "@MapperScan" not in text:
        return "missing @MapperScan"
    if "SqlSessionFactoryBean" not in text:
        return "missing SqlSessionFactoryBean"
    if "DataSource" not in text:
        return "missing DataSource"
    if "setMapperLocations" not in text:
        return "missing setMapperLocations"
    if re.search(r'@MapperScan\s*\([^)]*basePackages\s*=\s*"[^"]*\*[^"]*"', text):
        return "wildcard mapper scan is forbidden"
    return ""

def _controller_mapping_count(content: str) -> int:
    return len(re.findall(r"@(?:Get|Post|Put|Delete|Patch|Request)Mapping\s*\(", content or ""))


def _looks_like_sql_in_controller(content: str) -> bool:
    low = (content or "").lower()
    sql_tokens = [" select ", " insert ", " update ", " delete ", " from ", " where "]
    return any(token in f" {low} " for token in sql_tokens)


def _jsp_controller_guard_reason(logical_path: str, frontend: str, content: str) -> str:
    if frontend != "jsp" or not logical_path.startswith("java/controller/") or not logical_path.endswith("Controller.java"):
        return ""
    chars = len(content or "")
    if chars > 4500:
        return f"jsp controller too long: chars={chars} > 4500"
    mapping_count = _controller_mapping_count(content)
    if mapping_count > 5:
        return f"jsp controller too many handlers: count={mapping_count} > 5"
    if _looks_like_sql_in_controller(content):
        return "jsp controller contains sql-like text"
    return ""


def validate_content(logical_path: str, content: str):
    if not content or not content.strip():
        raise GenerationError(f"{logical_path}: empty content")

    if "..." == content.strip():
        raise GenerationError(f"{logical_path}: stub content detected")

    if logical_path.endswith(".jsp"):
        if "<table" in content.lower():
            raise GenerationError(f"{logical_path}: <table> is forbidden (use ul/li)")
        if re.search(r"(href|action)\s*=\s*[\"']([^\"']+)\.jsp(?:\?[^\"']*)?[\"']", content, re.IGNORECASE):
            raise GenerationError(f"{logical_path}: direct JSP links/forms are forbidden; route through controller mappings")
        if not _looks_like_jsp(content):
            raise GenerationError(f"{logical_path}: not valid JSP")

    if logical_path.endswith("Mapper.xml"):
        if _looks_like_legacy_ibatis_xml(content):
            raise GenerationError(f"{logical_path}: legacy iBATIS/sqlMap XML detected (MyBatis-only mode)")
        if not _looks_like_mapper_xml(content):
            raise GenerationError(f"{logical_path}: not valid MyBatis mapper XML")
        if not re.search(r'<!DOCTYPE\s+mapper', content, re.IGNORECASE):
            raise GenerationError(f"{logical_path}: mapper xml must declare MyBatis mapper DOCTYPE")

    if logical_path.endswith(".java"):
        low = (content or "").lower()
        if not re.search(r"^\s*package\s+egovframework\.[A-Za-z0-9_\.]+\s*;", content, re.MULTILINE):
            raise GenerationError(f"{logical_path}: package must start with egovframework.<project>")
        if "leaveatrace" in low:
            raise GenerationError(f"{logical_path}: references legacy bean 'leaveaTrace'")
        if "egovabstractserviceimpl" in low:
            raise GenerationError(f"{logical_path}: extends/uses EgovAbstractServiceImpl (requires leaveaTrace)")
        if re.search(r'@Resource\s*\(\s*name\s*=\s*"[A-Za-z0-9_]+Mapper"\s*\)', content):
            raise GenerationError(f"{logical_path}: name-based mapper injection is forbidden; use constructor injection")
        controller_guard_reason = _jsp_controller_guard_reason(logical_path, "jsp", content)
        if controller_guard_reason:
            raise GenerationError(f"{logical_path}: {controller_guard_reason}")
        feature_kind = classify_feature_kind({"path": logical_path, "content": content})
        if "class " not in content and "interface " not in content and "enum " not in content:
            raise GenerationError(f"{logical_path}: not valid Java type")

        simple_name = _java_simple_name(logical_path)
        if simple_name == "MyBatisConfig":
            reason = _mybatis_config_invalid_reason(content)
            if reason:
                raise GenerationError(f"{logical_path}: invalid MyBatisConfig ({reason})")
        elif simple_name.endswith("Service"):
            if _missing_list_import(content):
                raise GenerationError(f"{logical_path}: service missing java.util.List import")
            vo_missing = _missing_imports_for_names(content, _vo_names_in_java(content), "service.vo")
            if vo_missing:
                raise GenerationError(f"{logical_path}: service missing VO import(s): {', '.join(vo_missing)}")
        elif simple_name.endswith("ServiceImpl"):
            if _missing_list_import(content):
                raise GenerationError(f"{logical_path}: service impl missing java.util.List import")
            vo_missing = _missing_imports_for_names(content, _vo_names_in_java(content), "service.vo")
            if vo_missing:
                raise GenerationError(f"{logical_path}: service impl missing VO import(s): {', '.join(vo_missing)}")
            mapper_name = re.sub(r"ServiceImpl$", "Mapper", simple_name)
            if mapper_name in content and not re.search(rf"^\s*import\s+egovframework\.[A-Za-z0-9_.]+\.service\.mapper\.{re.escape(mapper_name)}\s*;", content, re.MULTILINE):
                raise GenerationError(f"{logical_path}: service impl missing mapper import: {mapper_name}")
        elif simple_name.endswith("Mapper"):
            if _has_mybatis_sql_annotations(content):
                raise GenerationError(f"{logical_path}: mapper interface must stay in XML-only mode (SQL annotations forbidden)")
            if "@Mapper" not in content:
                raise GenerationError(f"{logical_path}: mapper interface missing @Mapper")
        elif simple_name.endswith("Controller"):
            invalid_type = _invalid_jsp_controller_binding(content)
            if invalid_type:
                raise GenerationError(f"{logical_path}: controller must bind VO types only, found {invalid_type}")
        elif simple_name == "EgovBootApplication":
            if re.search(r"^\s*package\s+egovframework\.example\s*;", content, re.MULTILINE) and "scanBasePackages" not in content:
                raise GenerationError(f"{logical_path}: boot application package mismatches generated modules; add scanBasePackages")

def _project_segment(base_package: str) -> str:
    parts = [p for p in (base_package or '').split('.') if p]
    if len(parts) >= 2 and parts[0] == 'egovframework':
        return parts[1]
    return parts[-1] if parts else 'app'


def _is_generic_entity_var(ev: str) -> bool:
    return (ev or '').lower() in {"ui", "screen", "page", "view", "app", "main", "home", "form"}


def _semantic_module_from_task(task: dict, entity_var: str, base_package: str) -> str:
    ignored = {
        'java', 'jsp', 'xml', 'controller', 'service', 'impl', 'mapper', 'vo', 'config', 'web', 'package', 'import',
        'list', 'detail', 'form', 'save', 'delete', 'update', 'insert', 'select', 'index',
        'sample', 'example', 'default', 'common', 'screen', 'page', 'view', 'views', 'ui', 'app',
        'main', 'home', 'crud', 'feature', 'module', 'mybatis', 'schema', 'sql', 'resources', 'create', 'define', 'implement', 'build', 'make', 'write', 'generate'
    }
    blob = ' '.join(str(task.get(k) or '') for k in ('purpose', 'path', 'description', 'name'))
    project_seg = _project_segment(base_package).lower()
    entity_var = (entity_var or '').lower()
    if entity_var and not _is_generic_entity_var(entity_var):
        return entity_var
    for token in re.findall(r'[A-Za-z][A-Za-z0-9_]*', blob):
        low = token.lower()
        if low in ignored or low == project_seg or low == entity_var:
            continue
        if low.endswith(("controller", "service", "mapper", "vo", "impl", "config")):
            continue
        return low
    return entity_var

def _normalize_react_logical_path(p: str) -> str:
    p = (p or "").replace("\\", "/").strip()
    if not p:
        return ""
    if p.startswith("frontend/react/"):
        p = p[len("frontend/react/"):]

    m = re.match(r"^src/pages/([a-zA-Z0-9_\-/]+)/([A-Z][A-Za-z0-9_]*)(List|Detail|Form|Login)\.jsx$", p)
    if m:
        folder = m.group(1)
        base_name = m.group(2)
        kind = m.group(3)
        if kind == "Login":
            return "src/pages/login/LoginPage.jsx"
        return f"src/pages/{folder}/{base_name}{kind}Page.jsx"

    m = re.match(r"^src/api/(.+)Api\.js$", p)
    if m:
        return f"src/api/services/{m.group(1)}.js"
    m = re.match(r"^src/api/services/(.+)Api\.js$", p)
    if m:
        return f"src/api/services/{m.group(1)}.js"
    if p.startswith("src/api/") and p.endswith(".js") and "/" not in p[len("src/api/"):] and Path(p).name != "client.js":
        return f"src/api/services/{Path(p).stem}.js"

    return p


def _canonical_tasks_for_schema(schema, frontend: str = "jsp") -> list:
    E = schema.entity
    ev = schema.entity_var
    frontend = (frontend or "jsp").strip().lower()
    tasks = [
        {"path": f"java/service/vo/{E}VO.java", "purpose": f"{E} VO (in service.vo package)"},
        {"path": f"java/service/mapper/{E}Mapper.java", "purpose": f"{E} MyBatis mapper interface (in service.mapper package)"},
        {"path": f"mapper/{ev}/{E}Mapper.xml", "purpose": f"{E} MyBatis mapper xml"},
        {"path": f"java/service/{E}Service.java", "purpose": f"{E} service interface"},
        {"path": f"java/service/impl/{E}ServiceImpl.java", "purpose": f"{E} service implementation"},
        {"path": f"java/controller/{E}Controller.java", "purpose": f"{E} controller"},
        {"path": "java/config/MyBatisConfig.java", "purpose": "MyBatis mapper scan configuration"},
    ]

    if frontend == "react":
        tasks.extend([
            {"path": "src/api/client.js", "purpose": "React API client wrapper"},
            {"path": "src/constants/routes.js", "purpose": "React route path constants"},
            {"path": "src/routes/index.jsx", "purpose": "React route registry"},
        ])
        if is_auth_kind(schema.feature_kind):
            tasks.extend([
                {"path": "src/pages/login/LoginPage.jsx", "purpose": "React login page"},
                {"path": "src/api/services/auth.js", "purpose": "React auth API service"},
            ])
            return tasks
        tasks.extend([
            {"path": f"src/pages/{ev}/{E}ListPage.jsx", "purpose": f"{E} React list page"},
            {"path": f"src/pages/{ev}/{E}DetailPage.jsx", "purpose": f"{E} React detail page"},
            {"path": f"src/api/services/{ev}.js", "purpose": f"{E} React API service"},
        ])
        if not is_read_only_kind(schema.feature_kind):
            tasks.append({"path": f"src/pages/{ev}/{E}FormPage.jsx", "purpose": f"{E} React form page"})
        return tasks

    if frontend == "vue":
        if is_auth_kind(schema.feature_kind):
            tasks.extend([
                {"path": f"frontend/vue/src/views/{ev}/{E}Login.vue", "purpose": f"{E} Vue login view"},
                {"path": f"frontend/vue/src/api/{ev}Api.js", "purpose": f"{E} Vue API helper"},
            ])
            return tasks
        tasks.extend([
            {"path": f"frontend/vue/src/views/{ev}/{E}List.vue", "purpose": f"{E} Vue list view"},
            {"path": f"frontend/vue/src/views/{ev}/{E}Detail.vue", "purpose": f"{E} Vue detail view"},
            {"path": f"frontend/vue/src/api/{ev}Api.js", "purpose": f"{E} Vue API helper"},
        ])
        if not is_read_only_kind(schema.feature_kind):
            tasks.append({"path": f"frontend/vue/src/views/{ev}/{E}Form.vue", "purpose": f"{E} Vue form view"})
        return tasks

    if frontend == "nexacro":
        if is_auth_kind(schema.feature_kind):
            tasks.extend([
                {"path": f"frontend/nexacro/{ev}/{E}Login.xfdl", "purpose": f"{E} Nexacro login form"},
                {"path": f"frontend/nexacro/{ev}/{E}Service.xjs", "purpose": f"{E} Nexacro service script"},
            ])
            return tasks
        tasks.extend([
            {"path": f"frontend/nexacro/{ev}/{E}List.xfdl", "purpose": f"{E} Nexacro list form"},
            {"path": f"frontend/nexacro/{ev}/{E}Detail.xfdl", "purpose": f"{E} Nexacro detail form"},
            {"path": f"frontend/nexacro/{ev}/{E}Service.xjs", "purpose": f"{E} Nexacro service script"},
        ])
        if not is_read_only_kind(schema.feature_kind):
            tasks.append({"path": f"frontend/nexacro/{ev}/{E}Form.xfdl", "purpose": f"{E} Nexacro form"})
        return tasks

    if is_auth_kind(schema.feature_kind):
        tasks.extend([
            {"path": f"java/service/impl/{E}DAO.java", "purpose": f"{E} login DAO"},
            {"path": "java/config/AuthLoginInterceptor.java", "purpose": "login session interceptor"},
            {"path": "java/config/WebMvcConfig.java", "purpose": "web mvc interceptor configuration"},
            {"path": "jsp/login/login.jsp", "purpose": f"{E} login view"},
            {"path": "jsp/login/main.jsp", "purpose": f"{E} login main view"},
            {"path": "jsp/common/header.jsp", "purpose": "shared JSP header"},
            {"path": "index.jsp", "purpose": "home redirect"},
        ])
        if getattr(schema, 'routes', None) and schema.routes.get('list') and getattr(schema, 'views', None) and schema.views.get('list'):
            tasks.extend([
                {"path": f"jsp/{ev}List.jsp", "purpose": f"{E} management list view"},
                {"path": f"jsp/{ev}Detail.jsp", "purpose": f"{E} management detail view"},
                {"path": f"jsp/{ev}Form.jsp", "purpose": f"{E} management form view"},
            ])
        if getattr(schema, "approval_required", False):
            tasks.append({"path": f"jsp/{_approval_view(schema, 'list')}.jsp", "purpose": f"{E} approval pending view"})
        if getattr(schema, "unified_auth", False):
            tasks.extend([
                {"path": "java/service/IntegratedAuthService.java", "purpose": "integrated authentication service interface"},
                {"path": "java/service/impl/IntegratedAuthServiceImpl.java", "purpose": "integrated authentication service implementation"},
                {"path": "jsp/login/integrationGuide.jsp", "purpose": "integrated authentication guide view"},
            ])
        if getattr(schema, "cert_login", False):
            tasks.extend([
                {"path": "java/service/CertLoginService.java", "purpose": "certificate login service interface"},
                {"path": "java/service/impl/CertLoginServiceImpl.java", "purpose": "certificate login service implementation"},
                {"path": "java/controller/CertLoginController.java", "purpose": "certificate login controller"},
                {"path": "jsp/login/certLogin.jsp", "purpose": "certificate login view"},
            ])
        if getattr(schema, "jwt_login", False):
            tasks.extend([
                {"path": "java/config/JwtTokenProvider.java", "purpose": "JWT token provider"},
                {"path": "java/controller/JwtLoginController.java", "purpose": "JWT login controller"},
                {"path": "jsp/login/jwtLogin.jsp", "purpose": "JWT login view"},
            ])
        return tasks
    if is_schedule_kind(schema.feature_kind):
        tasks.extend([
            {"path": f"jsp/{ev}Calendar.jsp", "purpose": f"{E} monthly calendar main view"},
            {"path": f"jsp/{ev}Detail.jsp", "purpose": f"{E} detail view"},
            {"path": f"jsp/{ev}Form.jsp", "purpose": f"{E} form view"},
            {"path": "jsp/common/header.jsp", "purpose": "shared JSP header"},
            {"path": "index.jsp", "purpose": "home redirect"},
        ])
        return tasks
    if is_read_only_kind(schema.feature_kind):
        tasks.extend([
            {"path": f"jsp/{ev}List.jsp", "purpose": f"{E} list view (ul/li only)"},
            {"path": f"jsp/{ev}Detail.jsp", "purpose": f"{E} detail view"},
            {"path": "jsp/common/header.jsp", "purpose": "shared JSP header"},
            {"path": "index.jsp", "purpose": "home redirect"},
        ])
        return tasks
    tasks.extend([
        {"path": f"jsp/{ev}List.jsp", "purpose": f"{E} list view (ul/li only)"},
        {"path": f"jsp/{ev}Detail.jsp", "purpose": f"{E} detail view"},
        {"path": f"jsp/{ev}Form.jsp", "purpose": f"{E} form view"},
        {"path": "jsp/common/header.jsp", "purpose": "shared JSP header"},
        {"path": "index.jsp", "purpose": "home redirect"},
    ])
    return tasks

def _task_dependency_priority(path: str) -> int:
    p = (path or '').replace('\\', '/').strip()
    name = p.split('/')[-1]
    lower = p.lower()
    if name == 'pom.xml':
        return 0
    if lower.endswith('/mybatisconfig.java'):
        return 5
    if name.endswith('VO.java'):
        return 10
    if name.endswith('Mapper.java'):
        return 20
    if name.endswith('Mapper.xml') or (lower.startswith('mapper/') and name.endswith('.xml')):
        return 30
    if name.endswith('Service.java'):
        return 40
    if name.endswith('ServiceImpl.java'):
        return 50
    if name.endswith('DAO.java'):
        return 55
    if name.endswith('Controller.java') or name.endswith('RestController.java'):
        return 60
    if name.endswith('Interceptor.java') or name == 'WebMvcConfig.java':
        return 62
    if lower.endswith('/header.jsp') or lower.endswith('/common/header.jsp'):
        return 65
    if lower.endswith('.jsp') or lower.endswith('.html'):
        return 70
    if '/api/' in lower:
        return 80
    if '/router/' in lower or '/routes/' in lower or '/stores/' in lower or '/constants/' in lower:
        return 85
    if '/pages/' in lower or '/views/' in lower or '/components/' in lower:
        return 90
    return 100


def normalize_tasks(plan: dict) -> list:
    tasks = plan.get("tasks") or []
    if not isinstance(tasks, list):
        tasks = []
    norm = []
    def _to_logical(p: str) -> str:
        p = (p or "").replace("\\", "/").strip()
        if not p:
            return ""
        # normalize common typos
        p = p.replace("java/serviceImpl/", "java/service/impl/")
        p = _normalize_react_logical_path(p)
        # convert real-path style -> logical style so builtin templates apply first
        if p.startswith("src/main/java/"):
            tail = p.split("src/main/java/", 1)[1]
            if "/web/" in tail and tail.endswith("Controller.java"):
                return "java/controller/" + tail.split("/")[-1]
            if "/service/impl/" in tail and tail.endswith("ServiceImpl.java"):
                return "java/service/impl/" + tail.split("/")[-1]
            if "/service/" in tail and tail.endswith("Service.java"):
                return "java/service/" + tail.split("/")[-1]
            if tail.endswith("VO.java"):
                return "java/service/vo/" + tail.split("/")[-1]
            if tail.endswith("Mapper.java"):
                return "java/service/mapper/" + tail.split("/")[-1]
            if "/config/" in tail and tail.endswith("MyBatisConfig.java"):
                return "java/config/MyBatisConfig.java"
            return p
        if p.startswith("src/main/resources/"):
            tail = p.split("src/main/resources/", 1)[1]
            if "mapper/" in tail:
                idx = tail.find("mapper/")
                return "mapper/" + tail[idx+len("mapper/"):]
            if "egovframework/mapper/" in tail:
                idx = tail.find("egovframework/mapper/")
                return "mapper/" + tail[idx+len("egovframework/mapper/"):]
            if "egovframework/sqlmap/" in tail:
                idx = tail.find("egovframework/sqlmap/")
                return "mapper/" + tail[idx+len("egovframework/sqlmap/"):]
            return "resources/" + tail
        if "src/main/webapp/WEB-INF/views/" in p:
            tail = p.split("src/main/webapp/WEB-INF/views/", 1)[1]
            return "jsp/" + tail
        if p.endswith("/src/main/webapp/index.jsp") or p.endswith("src/main/webapp/index.jsp"):
            return "index.jsp"
        return p

    for t in tasks:
        if not isinstance(t, dict):
            continue
        p0 = (t.get("path") or "")
        p = _to_logical(p0)
        if not p:
            continue
        norm.append({**t, "path": p})

    # If plan used legacy logical mapper path (java/service/*Mapper.java), normalize to java/service/mapper/*Mapper.java
    for t in norm:
        p = (t.get("path") or "")
        if p.startswith("java/service/") and p.endswith("Mapper.java") and "/mapper/" not in p:
            t["path"] = "java/service/mapper/" + p.split("/")[-1]

    # Determine entity and schema early (even if plan is incomplete)
    schema = infer_schema_from_plan({"tasks": norm, "db_ops": plan.get("db_ops") or [], "requirements_text": plan.get("requirements_text") or "", "schema_text": plan.get("schema_text") or ""})
    E = schema.entity
    ev = schema.entity_var
    M = f"{E}Mapper"

    # Drop/normalize legacy iBATIS sqlMap mapper filenames into the canonical MyBatis mapper.
    # Example: mapper/<entity>/<Entity>_SQL_mysql.xml -> mapper/<entity>/<Entity>Mapper.xml
    legacy_sql_pat = re.compile(r"_SQL(_(mysql|oracle|postgresql))?\.xml$", re.IGNORECASE)
    for t in norm:
        p = (t.get("path") or "").replace("\\", "/")
        name = p.split("/")[-1]
        if p.startswith("mapper/") and legacy_sql_pat.search(name):
            t["path"] = f"mapper/{ev}/{M}.xml"

    # Canonical tasks depend on the inferred feature type.
    canonical = _canonical_tasks_for_schema(schema, plan.get("frontend") or "jsp")

    existing = set(t.get("path") for t in norm if isinstance(t, dict))

    # Prefer canonical tasks: put them first, and drop any other task that targets the same path.
    dedup = []
    seen = set()

    for c in canonical:
        dedup.append(c)
        seen.add(c["path"])

    extras = []
    for t in norm:
        p = t.get("path")
        if not p or p in seen:
            continue
        extras.append(t)
        seen.add(p)

    extras.sort(key=lambda item: (_task_dependency_priority(item.get("path") or ""), (item.get("path") or "").lower()))
    dedup.extend(extras)

    plan["tasks"] = dedup
    return dedup

def _react_scaffold_files(schema: object) -> dict[str, str]:
    entity = getattr(schema, "entity", "App") or "App"
    return {
        "package.json": """{
  "name": "frontend-react",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18",
    "react-dom": "^18",
    "react-router-dom": "^6"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4",
    "vite": "^5"
  }
}
""",
        "vite.config.js": """import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
  },
});
""",
        "index.html": f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{entity} React App</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
""",
        "jsconfig.json": """{
  "compilerOptions": {
    "baseUrl": "src"
  },
  "include": ["src"]
}
""",
        ".env.development": "VITE_API_BASE_URL=http://localhost:8080\n",
        ".env.production": "VITE_API_BASE_URL=/\n",
        "src/main.jsx": """import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./css/base.css";
import "./css/layout.css";
import "./css/component.css";
import "./css/page.css";
import "./css/responsive.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
""",
        "src/App.jsx": """import { RouterProvider } from "react-router-dom";
import router from "./routes";

export default function App() {
  return <RouterProvider router={router} />;
}
""",
        "src/css/base.css": """:root {
  font-family: Arial, Helvetica, sans-serif;
  line-height: 1.5;
  color: #1f2937;
  background: #f3f4f6;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
}

button,
input {
  font: inherit;
}
""",
        "src/css/layout.css": """.page-shell {
  min-height: 100vh;
  padding: 32px 20px;
}

.page-card {
  max-width: 1080px;
  margin: 0 auto;
  padding: 24px;
  border-radius: 16px;
  background: #ffffff;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
}
""",
        "src/css/component.css": """button {
  border: 0;
  border-radius: 10px;
  padding: 10px 14px;
  background: #2563eb;
  color: #ffffff;
  cursor: pointer;
}

button:disabled {
  opacity: 0.65;
  cursor: default;
}

.error-text {
  color: #dc2626;
}
""",
        "src/css/page.css": """.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}
""",
        "src/css/responsive.css": """@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
  }
}
""",
    }


def _ensure_react_scaffold(profile, schema, written: list[str]) -> None:
    files = _react_scaffold_files(schema)
    for logical_path, content in files.items():
        real_path = profile.resolve_path(logical_path)
        if real_path.exists() and not profile.context.overwrite:
            continue
        real_path.parent.mkdir(parents=True, exist_ok=True)
        if not profile.context.dry_run:
            real_path.write_text(content, encoding="utf-8")
            log(f"SUCCESS (react scaffold): {real_path}")
        else:
            log(f"DRY-RUN (react scaffold): {real_path}")
        written.append(str(real_path))


def ensure_db_ops(plan: dict, schema) -> None:
    ops = plan.get("db_ops") or []
    if not isinstance(ops, list):
        ops = []
    plan["db_ops"] = canonicalize_db_ops(ops, schema)

def generate_files(plan: dict, profile):
    written = []
    failed = []
    skipped = []

    tasks = normalize_tasks(plan)
    if not tasks:
        raise GenerationError("Plan does not contain tasks")

    # deterministic schema fallback
    schema = infer_schema_from_plan(plan)
    ensure_db_ops(plan, schema)

    frontend = (plan.get("frontend") or "").strip().lower()
    if frontend == "react":
        _ensure_react_scaffold(profile, schema, written)

    for task in tasks:
        logical_path = task.get("path")
        if not logical_path:
            continue
        logical_path = logical_path.replace("\\","/")

        module_seg = _semantic_module_from_task(task, schema.entity_var, profile.context.base_package)
        effective_base = profile.context.base_package
        if module_seg and (module_seg != schema.entity_var or _is_generic_entity_var(schema.entity_var)) and not effective_base.endswith("." + module_seg):
            effective_base = f"{effective_base}.{module_seg}"

        log(f"Generating: {logical_path} -> {effective_base}")
        if hasattr(profile, "resolve_path_for_base"):
            real_path: Path = profile.resolve_path_for_base(logical_path, effective_base)
        else:
            real_path: Path = profile.resolve_path(logical_path)

        if real_path.exists() and not profile.context.overwrite:
            log(f"SKIPPED (exists): {real_path}")
            skipped.append(str(real_path))
            continue

        real_path.parent.mkdir(parents=True, exist_ok=True)

        # 1) Builtin deterministic for core CRUD
        content = builtin_file(logical_path, effective_base, schema)
        if content is not None:
            content = profile.post_process(real_path, content)
            if not profile.context.dry_run:
                real_path.write_text(content, encoding="utf-8")
                log(f"SUCCESS (builtin): {real_path}")
            else:
                log(f"DRY-RUN (builtin): {real_path}")
            written.append(str(real_path))
            continue

        # 2) LLM for others with retries
        prompt = profile.build_prompt(task)
        last_err = ""
        ok = False
        for attempt in range(3):
            raw = call_ollama(prompt, profile.context.config)
            raw = _strip_garbage(raw)

            # post-process
            if logical_path.endswith(".java"):
                pkg = _java_pkg_from_path(real_path, profile.context.base_package)
                raw = _ensure_package(raw, pkg)
                raw = _rewrite_project_imports(raw, pkg, profile.context.base_package)
                raw = _force_type_name(raw, real_path.stem)

            raw = profile.post_process(real_path, raw)

            guard_reason = _jsp_controller_guard_reason(logical_path, frontend, raw)
            if guard_reason:
                fallback = builtin_file(logical_path, effective_base, schema)
                if fallback is not None:
                    log(f"JSP controller guard fallback: {logical_path} -> {guard_reason}")
                    raw = profile.post_process(real_path, fallback)

            try:
                validate_content(logical_path, raw)
            except Exception as e:
                last_err = str(e)
                log(f"RETRY {attempt+1}/3: {logical_path} -> {last_err}")
                # tighten prompt
                prompt = prompt + "\n\nFIX: " + last_err + "\nOutput only the correct file content."
                continue

            # write
            if not profile.context.dry_run:
                real_path.write_text(raw, encoding="utf-8")
                log(f"SUCCESS: {real_path}")
            else:
                log(f"DRY-RUN: file not written -> {real_path}")
            written.append(str(real_path))
            ok = True
            break

        if not ok:
            log(f"FAILED: {logical_path}: {last_err}")
            failed.append(f"{logical_path}: {last_err}")

    return {"written": written, "failed": failed, "skipped": skipped}
