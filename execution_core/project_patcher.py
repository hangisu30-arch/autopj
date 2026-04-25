from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import stat
import re

MAVEN_WRAPPER_VERSION = "3.9.9"
MAVEN_WRAPPER_ZIP_URL = f"https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/{MAVEN_WRAPPER_VERSION}/apache-maven-{MAVEN_WRAPPER_VERSION}-bin.zip"
MAVEN_WRAPPER_TGZ_URL = f"https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/{MAVEN_WRAPPER_VERSION}/apache-maven-{MAVEN_WRAPPER_VERSION}-bin.tar.gz"

_CREATE_TABLE_RE = re.compile(r'create\s+table\s+(?:if\s+not\s+exists\s+)?[`"]?([A-Za-z_][\w]*)[`"]?', re.IGNORECASE)


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

def _write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _write_executable_text(p: Path, s: str) -> None:
    _write_text(p, s)
    try:
        mode = p.stat().st_mode
        p.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass

def _split_sql_statements(sql: str) -> List[str]:
    body = str(sql or '')
    if not body.strip():
        return []
    statements: List[str] = []
    current: List[str] = []
    in_single = False
    in_double = False
    prev = ''
    for ch in body:
        if ch == "'" and not in_double and prev != "\\":
            in_single = not in_single
        elif ch == '"' and not in_single and prev != "\\":
            in_double = not in_double
        if ch == ';' and not in_single and not in_double:
            stmt = ''.join(current).strip()
            if stmt:
                statements.append(stmt + ';')
            current = []
        else:
            current.append(ch)
        prev = ch
    tail = ''.join(current).strip()
    if tail:
        statements.append(tail if tail.endswith(';') else tail + ';')
    return statements


def _statement_table_name(sql: str) -> str:
    m = _CREATE_TABLE_RE.search(str(sql or ''))
    return (m.group(1).strip().lower() if m else '')


def _dedupe_create_table_statements(sql: str) -> str:
    merged: List[str] = []
    seen_tables: Dict[str, int] = {}
    for stmt in _split_sql_statements(sql):
        normalized = stmt.strip()
        if not normalized:
            continue
        table_name = _statement_table_name(normalized)
        if table_name:
            idx = seen_tables.get(table_name)
            if idx is not None:
                merged[idx] = normalized if normalized.endswith(';') else normalized + ';'
                continue
            seen_tables[table_name] = len(merged)
        merged.append(normalized if normalized.endswith(';') else normalized + ';')
    rendered = '\n\n'.join(merged).strip()
    return rendered + ('\n' if rendered else '')


def _set_prop(text: str, key: str, value: str) -> str:
    # replace if exists, else append
    lines = text.splitlines()
    out = []
    found = False
    for line in lines:
        if re.match(rf"^\s*{re.escape(key)}\s*=", line):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        if out and out[-1].strip() != "":
            out.append("")
        out.append(f"{key}={value}")
    return "\n".join(out) + ("\n" if not text.endswith("\n") else "")


def _remove_prop(text: str, key: str) -> str:
    lines = text.splitlines()
    out = []
    for line in lines:
        if re.match(rf"^\s*{re.escape(key)}\s*=", line):
            continue
        out.append(line)
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def _normalize_h2_url(url: str) -> str:
    raw = (url or '').strip()
    if not raw.lower().startswith('jdbc:h2:'):
        return raw
    required = {
        'MODE=MySQL': 'MODE=MySQL',
        'DB_CLOSE_ON_EXIT=FALSE': 'DB_CLOSE_ON_EXIT=FALSE',
        'DB_CLOSE_DELAY=-1': 'DB_CLOSE_DELAY=-1',
    }
    if ';' not in raw:
        base, params = raw, []
    else:
        base, tail = raw.split(';', 1)
        params = [part.strip() for part in tail.split(';') if part.strip()]
    existing_upper = {part.upper() for part in params}
    for upper, value in required.items():
        if upper not in existing_upper:
            params.append(value)
    return base + (';' + ';'.join(params) if params else '')


def _get_prop(text: str, key: str) -> str:
    for line in text.splitlines():
        m = re.match(rf"^\s*{re.escape(key)}\s*=\s*(.*)$", line)
        if m:
            return m.group(1).strip()
    return ''


def _find_boot_applications(project_root: Path) -> List[Tuple[Path, str, str]]:
    """Return all @SpringBootApplication classes as (source_path, package_name, class_name)."""
    src = project_root / "src/main/java"
    if not src.exists():
        return []
    found: List[Tuple[Path, str, str]] = []
    for java_file in sorted(src.rglob("*.java")):
        t = _read_text(java_file)
        if "@SpringBootApplication" not in t:
            continue
        pkg_m = re.search(r"^\s*package\s+([a-zA-Z0-9_\.]+)\s*;", t, re.MULTILINE)
        cls_m = re.search(r"public\s+class\s+([A-Za-z0-9_]+)", t)
        found.append((java_file, (pkg_m.group(1).strip() if pkg_m else ""), (cls_m.group(1).strip() if cls_m else "EgovBootApplication")))
    return found


def _find_boot_application(project_root: Path) -> Tuple[Optional[Path], str, str]:
    found = _find_boot_applications(project_root)
    return found[0] if found else (None, "", "")


def _collect_scan_base_packages(project_root: Path, base_package: str) -> List[str]:
    base = (base_package or '').strip()
    roots: List[str] = []
    if base:
        roots.append(base)
    java_root = project_root / "src/main/java"
    if not java_root.exists():
        return roots or ([base] if base else [])
    seen = set(roots)
    for java_file in sorted(java_root.rglob("*.java")):
        body = _read_text(java_file)
        pkg_m = re.search(r"^\s*package\s+([a-zA-Z0-9_\.]+)\s*;", body, re.MULTILINE)
        pkg = (pkg_m.group(1).strip() if pkg_m else "")
        if not pkg:
            continue
        candidate = pkg
        if base and (pkg == base or pkg.startswith(base + '.')):
            candidate = base
        elif pkg.startswith('egovframework.'):
            parts = [part for part in pkg.split('.') if part]
            candidate = '.'.join(parts[:2]) if len(parts) >= 2 else pkg
        elif '.' in pkg:
            parts = [part for part in pkg.split('.') if part]
            candidate = '.'.join(parts[:2]) if len(parts) >= 2 else parts[0]
        if candidate and candidate not in seen:
            seen.add(candidate)
            roots.append(candidate)
    return roots or ([base] if base else [])


def _render_boot_application_source(base_package: str, class_name: str, scan_packages: List[str]) -> str:
    packages = [pkg for pkg in scan_packages if pkg]
    annotation = '@SpringBootApplication'
    if packages:
        joined = ', '.join(f'"{pkg}"' for pkg in packages)
        annotation = f'@SpringBootApplication(scanBasePackages = {{{joined}}})'
    return (
        f"package {base_package};\n\n"
        "import org.springframework.boot.SpringApplication;\n"
        "import org.springframework.boot.autoconfigure.SpringBootApplication;\n\n"
        f"{annotation}\n"
        f"public class {class_name} {{\n"
        "    public static void main(String[] args) {\n"
        f"        SpringApplication.run({class_name}.class, args);\n"
        "    }\n"
        "}\n"
    )


def patch_boot_application(project_root: Path, base_package: str, class_name: str = "EgovBootApplication") -> Path:
    """Ensure exactly one canonical Spring Boot entry class exists under src/main/java/{base_package}."""
    src_root = project_root / "src/main/java"
    src_root.mkdir(parents=True, exist_ok=True)

    effective_base_package = (base_package or '').strip() or 'egovframework.app'
    chosen_class = (class_name or '').strip() or 'EgovBootApplication'
    target = src_root / Path(*effective_base_package.split('.')) / f"{chosen_class}.java"
    existing_apps = _find_boot_applications(project_root)

    t = _render_boot_application_source(
        effective_base_package,
        chosen_class,
        _collect_scan_base_packages(project_root, effective_base_package),
    )
    _write_text(target, t)

    for stale_path, stale_pkg, stale_class_name in existing_apps:
        if stale_path == target or not stale_path.exists():
            continue
        try:
            stale_path.unlink()
        except Exception:
            pass
        stale_class = project_root / "target/classes" / Path(*stale_pkg.split('.')) / f"{stale_class_name}.class"
        try:
            if stale_class.exists():
                stale_class.unlink()
        except Exception:
            pass

    for stale_pkg in {pkg for _, pkg, _ in existing_apps if pkg}:
        stale_class = project_root / "target/classes" / Path(*stale_pkg.split('.')) / f"{chosen_class}.class"
        target_class = project_root / "target/classes" / Path(*effective_base_package.split('.')) / f"{chosen_class}.class"
        if stale_class != target_class and stale_class.exists():
            try:
                stale_class.unlink()
            except Exception:
                pass

    return target


def patch_application_properties(project_root: Path, base_package: str, frontend: str = "jsp") -> Path:
    res_dir = project_root / "src/main/resources"
    props = res_dir / "application.properties"
    yml = res_dir / "application.yml"

    if props.exists():
        txt = _read_text(props)
        path = props
    elif yml.exists():
        # we won't rewrite YAML to avoid breaking; create properties alongside
        txt = ""
        path = props
    else:
        txt = ""
        path = props

    frontend = (frontend or "jsp").strip().lower()

    # View resolver only for JSP frontend
    if frontend == "jsp":
        txt = _set_prop(txt, "spring.mvc.view.prefix", "/WEB-INF/views/")
        txt = _set_prop(txt, "spring.mvc.view.suffix", ".jsp")
    else:
        txt = _remove_prop(txt, "spring.mvc.view.prefix")
        txt = _remove_prop(txt, "spring.mvc.view.suffix")

    # Avoid Thymeleaf warnings if dependency exists but templates folder is not used
    txt = _set_prop(txt, "spring.thymeleaf.check-template-location", "false")
    txt = _set_prop(txt, "spring.thymeleaf.enabled", "false")

    # Ensure schema.sql runs against local MySQL too (table auto-create on startup)
    txt = _set_prop(txt, "spring.sql.init.mode", "never")
    txt = _set_prop(txt, "spring.sql.init.encoding", "UTF-8")
    txt = _set_prop(txt, "spring.sql.init.schema-locations", "optional:classpath:schema.sql,optional:classpath:login-schema.sql")
    txt = _set_prop(txt, "spring.sql.init.data-locations", "optional:classpath:data.sql,optional:classpath:login-data.sql")
    txt = _set_prop(txt, "spring.sql.init.continue-on-error", "false")


    # MyBatis XML mapper locations (we generate under /mapper)
    txt = _set_prop(txt, "mybatis.mapper-locations", "classpath*:egovframework/mapper/**/*.xml")
    txt = _set_prop(txt, "mybatis.type-aliases-package", f"{base_package}")
    txt = _set_prop(txt, "mybatis.configuration.map-underscore-to-camel-case", "true")

    current_url = _get_prop(txt, "spring.datasource.url")
    if current_url.lower().startswith("jdbc:h2:"):
        txt = _set_prop(txt, "spring.datasource.url", _normalize_h2_url(current_url))
        txt = _set_prop(txt, "spring.datasource.hikari.maximum-pool-size", "1")
        txt = _set_prop(txt, "spring.datasource.hikari.minimum-idle", "1")

    _write_text(path, txt)
    return path

def detect_boot_base_package(project_root: Path) -> str:
    src = project_root / "src/main/java"
    if not src.exists():
        return ""
    for p in src.rglob("*.java"):
        t = _read_text(p)
        if "@SpringBootApplication" in t:
            m = re.search(r"^\s*package\s+([a-zA-Z0-9_\.]+)\s*;", t, re.MULTILINE)
            if m:
                return m.group(1).strip()
    return ""


def patch_datasource_properties(project_root: Path, db_conf: dict) -> Path:
    """If db config is provided, write spring.datasource.* so Spring uses the same DB."""
    res_dir = project_root / "src/main/resources"
    props = res_dir / "application.properties"
    yml = res_dir / "application.yml"

    if props.exists():
        txt = _read_text(props)
        path = props
    elif yml.exists():
        txt = ""
        path = props
    else:
        txt = ""
        path = props

    host = (db_conf.get("host") or "").strip()
    port = int(db_conf.get("port", 3306) or 3306)
    user = (db_conf.get("username") or db_conf.get("user") or db_conf.get("db.user") or db_conf.get("db.username") or "").strip()
    pwd = (db_conf.get("password") or db_conf.get("db.password") or db_conf.get("db.pw") or "").strip()
    dbname = (db_conf.get("database") or db_conf.get("name") or db_conf.get("db.name") or db_conf.get("db.database") or db_conf.get("db.dbname") or "").strip()

    # Only patch if essential fields exist
    if host and user and dbname:
        url = f"jdbc:mysql://{host}:{port}/{dbname}?createDatabaseIfNotExist=true&useSSL=false&allowPublicKeyRetrieval=true&characterEncoding=UTF-8&serverTimezone=Asia/Seoul"
        txt = _set_prop(txt, "spring.datasource.url", url)
        txt = _set_prop(txt, "spring.datasource.username", user)
        txt = _set_prop(txt, "spring.datasource.password", pwd)
        txt = _set_prop(txt, "spring.datasource.driver-class-name", "com.mysql.cj.jdbc.Driver")
        _write_text(path, txt)

    return path


def _sync_schema_sql_variants(project_root: Path, canonical_sql: str) -> None:
    canonical = (canonical_sql or "").strip() + "\n"
    res_dir = project_root / "src/main/resources"
    db_dir = res_dir / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    for rel in ("db/schema.sql", "db/schema-mysql.sql"):
        _write_text(res_dir / rel, canonical)


def write_schema_sql(project_root: Path, sql: str) -> Path:
    """Write canonical schema.sql and keep common variant paths in sync."""
    res_dir = project_root / "src/main/resources"
    res_dir.mkdir(parents=True, exist_ok=True)
    canonical = (sql or "").strip() + "\n"
    p = res_dir / "schema.sql"
    _write_text(p, canonical)
    _sync_schema_sql_variants(project_root, canonical)
    return p

def write_database_initializer(project_root: Path, base_package: str) -> Path:
    """Write a Spring Boot initializer that executes bundled SQL resources on startup.
    This is more reliable across JSP/React/Vue/Nexacro projects than relying only on spring.sql.init.*.
    """
    pkg = f"{base_package}.config"
    src_dir = project_root / "src/main/java" / Path(*pkg.split('.'))
    src_dir.mkdir(parents=True, exist_ok=True)
    p = src_dir / "DatabaseInitializer.java"
    content = f"""package {pkg};

import java.util.ArrayList;
import java.util.List;

import javax.sql.DataSource;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.jdbc.datasource.init.ResourceDatabasePopulator;

@Configuration
public class DatabaseInitializer {{

    @Bean
    public ApplicationRunner databaseInitializerRunner(DataSource dataSource) {{
        return args -> {{
            List<Resource> resources = new ArrayList<>();
            for (String resourceName : new String[] {{"schema.sql", "data.sql", "login-schema.sql", "login-data.sql"}}) {{
                ClassPathResource resource = new ClassPathResource(resourceName);
                if (resource.exists()) {{
                    resources.add(resource);
                }}
            }}
            if (resources.isEmpty()) {{
                return;
            }}
            ResourceDatabasePopulator populator = new ResourceDatabasePopulator();
            populator.setSqlScriptEncoding("UTF-8");
            populator.setContinueOnError(false);
            for (Resource resource : resources) {{
                populator.addScript(resource);
            }}
            populator.execute(dataSource);
        }};
    }}
}}
"""
    _write_text(p, content)
    return p


def _normalize_sql_text(sql: str) -> str:
    lines = []
    for raw in (sql or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            continue
        lines.append(line)
    text = "\n".join(lines).strip()
    if text and not text.endswith(";"):
        text += ";"
    return text


def write_schema_sql_from_db_ops(project_root: Path, db_ops: list) -> Path:
    """Write schema.sql from plan db_ops so Spring Boot can auto-create tables on startup."""
    stmts = []
    for op in db_ops or []:
        if not isinstance(op, dict):
            continue
        sql = _normalize_sql_text(op.get("sql") or "")
        if sql:
            stmts.append(sql)
    body = "\n\n".join(stmts).strip()
    return write_schema_sql(project_root, body)


def patch_pom_mysql_driver(project_root: Path) -> bool:
    """Ensure MySQL JDBC driver dependency exists in pom.xml."""
    pom = project_root / "pom.xml"
    if not pom.exists():
        return False
    txt = _read_text(pom)
    if "mysql-connector-j" in txt or "mysql:mysql-connector-java" in txt:
        return False

    dep = """    <dependency>
      <groupId>com.mysql</groupId>
      <artifactId>mysql-connector-j</artifactId>
      <scope>runtime</scope>
    </dependency>
"""

    # Insert inside <dependencies> ... </dependencies>
    m = re.search(r"<dependencies>([\s\S]*?)</dependencies>", txt)
    if m:
        body = m.group(1)
        new_body = body + "\n" + dep
        txt2 = txt[:m.start(1)] + new_body + txt[m.end(1):]
        _write_text(pom, txt2)
        return True

    # If no dependencies tag, add one before </project>
    m2 = re.search(r"</project>", txt)
    if m2:
        insert = "\n  <dependencies>\n" + dep + "  </dependencies>\n"
        txt2 = txt[:m2.start()] + insert + txt[m2.start():]
        _write_text(pom, txt2)
        return True

    return False


def _insert_dependency(pom_text: str, dep_xml: str) -> str:
    m = re.search(r"<dependencies>([\s\S]*?)</dependencies>", pom_text)
    if m:
        body = m.group(1)
        new_body = body + "\n" + dep_xml
        return pom_text[:m.start(1)] + new_body + pom_text[m.end(1):]
    m2 = re.search(r"</project>", pom_text)
    if m2:
        insert = "\n  <dependencies>\n" + dep_xml + "  </dependencies>\n"
        return pom_text[:m2.start()] + insert + pom_text[m2.start():]
    return pom_text

def patch_pom_jsp_support(project_root: Path) -> bool:
    """Ensure JSP rendering dependencies exist for Spring Boot embedded Tomcat."""
    pom = project_root / "pom.xml"
    if not pom.exists():
        return False
    txt = _read_text(pom)

    changed = False

    if "tomcat-embed-jasper" not in txt:
        dep = """    <dependency>
      <groupId>org.apache.tomcat.embed</groupId>
      <artifactId>tomcat-embed-jasper</artifactId>
    </dependency>
"""
        txt = _insert_dependency(txt, dep)
        changed = True

    if "javax.servlet:jstl" not in txt and "<artifactId>jstl</artifactId>" not in txt:
        dep = """    <dependency>
      <groupId>javax.servlet</groupId>
      <artifactId>jstl</artifactId>
      <version>1.2</version>
    </dependency>
"""
        txt = _insert_dependency(txt, dep)
        changed = True

    if changed:
        _write_text(pom, txt)
    return changed



def ensure_maven_wrapper(project_root: Path) -> List[Path]:
    """Create self-bootstrapping Maven wrapper files so generated projects work without a global mvn install."""
    created: List[Path] = []
    mvnw = project_root / "mvnw"
    mvnw_cmd = project_root / "mvnw.cmd"
    props = project_root / ".mvn/wrapper/maven-wrapper.properties"

    mvnw_text = f'''#!/bin/sh
set -e

BASE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
WRAPPER_DIR="$BASE_DIR/.mvn/wrapper"
ARCHIVE="$WRAPPER_DIR/apache-maven-{MAVEN_WRAPPER_VERSION}-bin.tar.gz"
DIST_DIR="$WRAPPER_DIR/apache-maven-{MAVEN_WRAPPER_VERSION}"
MVN_BIN="$DIST_DIR/bin/mvn"
DIST_URL="${{MVNW_REPOURL:-{MAVEN_WRAPPER_TGZ_URL}}}"

if [ ! -x "$MVN_BIN" ]; then
  mkdir -p "$WRAPPER_DIR"
  if [ ! -f "$ARCHIVE" ]; then
    if command -v curl >/dev/null 2>&1; then
      curl -fsSL "$DIST_URL" -o "$ARCHIVE"
    elif command -v wget >/dev/null 2>&1; then
      wget -q -O "$ARCHIVE" "$DIST_URL"
    else
      echo "[mvnw] curl 또는 wget 이 필요합니다." >&2
      exit 1
    fi
  fi
  rm -rf "$DIST_DIR"
  tar -xzf "$ARCHIVE" -C "$WRAPPER_DIR"
fi

exec "$MVN_BIN" "$@"
'''

    mvnw_cmd_text = r"""@ECHO OFF
SETLOCAL

set "BASE_DIR=%~dp0"
set "WRAPPER_DIR=%BASE_DIR%.mvn\wrapper"
set "ARCHIVE=%WRAPPER_DIR%\apache-maven-{version}-bin.zip"
set "DIST_DIR=%WRAPPER_DIR%\apache-maven-{version}"
set "MVN_CMD=%DIST_DIR%\bin\mvn.cmd"
set "DIST_URL={url}"
if NOT "%MVNW_REPOURL%"=="" set "DIST_URL=%MVNW_REPOURL%"

if not exist "%MVN_CMD%" (
  if not exist "%WRAPPER_DIR%" mkdir "%WRAPPER_DIR%"
  if not exist "%ARCHIVE%" (
    where curl >NUL 2>NUL
    if %ERRORLEVEL%==0 (
      curl -fsSL "%DIST_URL%" -o "%ARCHIVE%"
      if errorlevel 1 goto :download_failed
    ) else (
      set "MVNW_DIST_URL=%DIST_URL%"
      set "MVNW_ARCHIVE=%ARCHIVE%"
      powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; $url=$env:MVNW_DIST_URL; $out=$env:MVNW_ARCHIVE; Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $out"
      if errorlevel 1 goto :download_failed
    )
  )
  if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"
  set "MVNW_ARCHIVE=%ARCHIVE%"
  set "MVNW_WRAPPER_DIR=%WRAPPER_DIR%"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$archive=$env:MVNW_ARCHIVE; $dest=$env:MVNW_WRAPPER_DIR; Expand-Archive -Path $archive -DestinationPath $dest -Force"
  if errorlevel 1 goto :extract_failed
)

call "%MVN_CMD%" %*
exit /b %ERRORLEVEL%

:download_failed
echo [mvnw.cmd] Maven 배포본 다운로드에 실패했습니다.>&2
exit /b 1

:extract_failed
echo [mvnw.cmd] Maven 배포본 압축 해제에 실패했습니다.>&2
exit /b 1
""".format(version=MAVEN_WRAPPER_VERSION, url=MAVEN_WRAPPER_ZIP_URL)



    props_text = f'''distributionBase=PROJECT
zipStoreBase=PROJECT
distributionPath=.mvn/wrapper
zipStorePath=.mvn/wrapper
distributionUrl={MAVEN_WRAPPER_ZIP_URL}
'''

    _write_executable_text(mvnw, mvnw_text)
    created.append(mvnw)
    _write_text(mvnw_cmd, mvnw_cmd_text)
    created.append(mvnw_cmd)
    _write_text(props, props_text)
    created.append(props)
    return created
