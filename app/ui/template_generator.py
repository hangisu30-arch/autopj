# path: app/ui/template_generator.py
from __future__ import annotations

from typing import List, Dict, Any
from pathlib import Path
import json

from app.ui.state import ProjectConfig


MAVEN_WRAPPER_VERSION = "3.9.9"
MAVEN_WRAPPER_ZIP_URL = f"https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/{MAVEN_WRAPPER_VERSION}/apache-maven-{MAVEN_WRAPPER_VERSION}-bin.zip"
MAVEN_WRAPPER_TGZ_URL = f"https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/{MAVEN_WRAPPER_VERSION}/apache-maven-{MAVEN_WRAPPER_VERSION}-bin.tar.gz"


_JAVA_KEYWORDS = {"abstract","assert","boolean","break","byte","case","catch","char","class","const","continue","default","do","double","else","enum","extends","final","finally","float","for","goto","if","implements","import","instanceof","int","interface","long","native","new","package","private","protected","public","return","short","static","strictfp","super","switch","synchronized","this","throw","throws","transient","try","void","volatile","while","true","false","null","record","sealed","permits","var","yield"}

def _sanitize_package_segment(s: str) -> str:
    raw = "".join(ch for ch in (s or "").strip() if ch.isalnum() or ch == "_")
    if not raw:
        return "app"
    seg = raw[0].lower() + raw[1:]
    while seg and not (seg[0].isalpha() or seg[0] == "_"):
        seg = seg[1:]
    seg = seg or "app"
    if seg in _JAVA_KEYWORDS:
        return f"{seg}_"
    return seg


def _guess_base_package(cfg: ProjectConfig) -> str:
    pn = _sanitize_package_segment(cfg.project_name)
    return f"egovframework.{pn}"


def _uses_maven_backend(cfg: ProjectConfig) -> bool:
    backend = (cfg.backend_key or "egov_spring").strip().lower()
    return backend in {"egov_spring", "spring", "spring_boot", "egov", "java_spring"}


def managed_template_paths(cfg: ProjectConfig) -> List[str]:
    paths: List[str] = ["src/main/resources/application.properties"]
    if _uses_maven_backend(cfg):
        paths = [
            "pom.xml",
            "mvnw",
            "mvnw.cmd",
            ".mvn/wrapper/maven-wrapper.properties",
            *paths,
        ]
    return paths


def render_maven_wrapper_properties() -> str:
    return f"""distributionBase=PROJECT
zipStoreBase=PROJECT
distributionPath=.mvn/wrapper
zipStorePath=.mvn/wrapper
distributionUrl={MAVEN_WRAPPER_ZIP_URL}
"""


def render_mvnw() -> str:
    return f'''#!/bin/sh
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


def render_mvnw_cmd() -> str:
    return r"""@ECHO OFF
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






def _load_default_db_conf() -> Dict[str, str]:
    """Load bundled execution_core/config.json DB defaults when UI fields are empty."""
    try:
        cfg_path = Path(__file__).resolve().parents[2] / "execution_core" / "config.json"
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        db = data.get("database") or data.get("db") or {}
        return {
            "host": str(db.get("host") or "localhost").strip() or "localhost",
            "port": str(db.get("port") or 3306).strip() or "3306",
            "database": str(db.get("database") or db.get("name") or "").strip(),
            "username": str(db.get("username") or db.get("user") or "").strip(),
            "password": str(db.get("password") or "").strip(),
        }
    except Exception:
        return {
            "host": "localhost",
            "port": "3306",
            "database": "",
            "username": "",
            "password": "",
        }


def render_application_properties(cfg: ProjectConfig) -> str:
    """Render src/main/resources/application.properties content based on cfg.database_key + cfg.frontend_key.
    NOTE: DB host/port UI inputs are not present; defaults to localhost with standard ports.
    """
    db = (cfg.database_key or "sqlite").lower().strip()
    fe = (cfg.frontend_key or "jsp").lower().strip()
    defaults = _load_default_db_conf()
    db_name = (cfg.db_name or defaults.get("database") or cfg.project_name or "").strip() or "autotest01"
    user = (cfg.db_login_id or defaults.get("username") or "").strip()
    pw = (cfg.db_password or defaults.get("password") or "").strip()
    db_host = (defaults.get("host") or "localhost").strip() or "localhost"
    db_port = (defaults.get("port") or "3306").strip() or "3306"

    base_pkg = _guess_base_package(cfg)

    if db == "mysql":
        driver = "com.mysql.cj.jdbc.Driver"
        url = f"jdbc:mysql://{db_host}:{db_port}/{db_name}?useUnicode=true&useSSL=false&allowPublicKeyRetrieval=true&characterEncoding=UTF-8&serverTimezone=Asia/Seoul"
    elif db == "postgresql":
        driver = "org.postgresql.Driver"
        url = f"jdbc:postgresql://localhost:5432/{db_name}"
    elif db == "oracle":
        driver = "oracle.jdbc.OracleDriver"
        url = "jdbc:oracle:thin:@//localhost:1521/ORCLPDB1"
    else:
        driver = "org.h2.Driver"
        url = f"jdbc:h2:file:./.autopj-h2/{db_name};MODE=MySQL;DB_CLOSE_ON_EXIT=FALSE;DB_CLOSE_DELAY=-1"

    lines: List[str] = []
    lines.append("# path: src/main/resources/application.properties")
    lines.append("")
    lines.append("# =========================")
    lines.append("# Server")
    lines.append("# =========================")
    lines.append("server.port=8080")
    lines.append("spring.mvc.pathmatch.matching-strategy=ant_path_matcher")
    lines.append("")
    if fe == "jsp":
        lines.append("# =========================")
        lines.append("# JSP View Resolver")
        lines.append("# =========================")
        lines.append("spring.mvc.view.prefix=/WEB-INF/views/")
        lines.append("spring.mvc.view.suffix=.jsp")
        lines.append("")
    else:
        lines.append("# =========================")
        lines.append("# API Server (React/Vue/Nexacro)")
        lines.append("# =========================")
        lines.append("# (선택) CORS는 보통 Java Config(WebMvcConfigurer)로 설정합니다.")
        lines.append("# React dev: http://localhost:3000 / Vite: 5173 / Vue: 8081")
        lines.append("")
    lines.append("# =========================")
    lines.append(f"# DataSource ({db})")
    lines.append("# =========================")
    lines.append(f"spring.datasource.driver-class-name={driver}")
    if db == "oracle":
        lines.append("# Oracle URL 예시 (SERVICE_NAME 방식) — 아래 한 줄을 사용")
        lines.append(f"spring.datasource.url={url}")
        lines.append("# Oracle URL 예시 (SID 방식) — 필요하면 위 줄을 주석처리하고 아래를 사용")
        lines.append("# spring.datasource.url=jdbc:oracle:thin:@localhost:1521:ORCL")
    else:
        lines.append(f"spring.datasource.url={url}")
    lines.append(f"spring.datasource.username={user}")
    lines.append(f"spring.datasource.password={pw}")
    if not user:
        lines.append("# TODO: DB username을 UI에 입력하거나 execution_core/config.json에 설정하세요.")
    if not pw:
        lines.append("# TODO: DB password를 UI에 입력하거나 execution_core/config.json에 설정하세요.")
    lines.append("")
    lines.append("# HikariCP (선택)")
    if db in ("sqlite", "h2"):
        lines.append("spring.datasource.hikari.maximum-pool-size=1")
        lines.append("spring.datasource.hikari.minimum-idle=1")
    else:
        lines.append("spring.datasource.hikari.maximum-pool-size=10")
        lines.append("spring.datasource.hikari.minimum-idle=2")
    lines.append("spring.datasource.hikari.connection-timeout=30000")
    lines.append("")
    lines.append("# =========================")
    lines.append("# MyBatis (전자정부에서 흔함)")
    lines.append("# =========================")
    lines.append("mybatis.mapper-locations=classpath*:egovframework/mapper/**/*.xml")
    lines.append(f"mybatis.type-aliases-package={base_pkg}")
    lines.append("mybatis.configuration.map-underscore-to-camel-case=true")
    lines.append("# mybatis.config-location=classpath:/mybatis-config.xml  (선택)")
    lines.append("")
    lines.append("# =========================")
    lines.append("# Logging")
    lines.append("# =========================")
    lines.append("logging.level.root=INFO")
    lines.append("logging.level.egovframework=DEBUG")
    lines.append("logging.level.org.mybatis=DEBUG")
    lines.append("")
    return "\n".join(lines)


def render_pom_xml(cfg: ProjectConfig) -> str:
    """Render pom.xml based on UI selections (DB + Frontend)."""
    db = (cfg.database_key or "mysql").lower().strip()
    fe = (cfg.frontend_key or "jsp").lower().strip()

    pn = (cfg.project_name or "").strip() or "autopj"
    group_id = pn
    artifact_id = pn
    version = "1.0.0"
    packaging = "jar"

    def dep(group_id: str, artifact_id: str, version_: str | None = None,
            scope: str | None = None, optional: bool | None = None,
            exclusions: list[tuple[str, str]] | None = None) -> str:
        ex = ""
        if exclusions:
            ex_lines = []
            for g, a in exclusions:
                ex_lines.append("        <exclusion>")
                ex_lines.append(f"          <groupId>{g}</groupId>")
                ex_lines.append(f"          <artifactId>{a}</artifactId>")
                ex_lines.append("        </exclusion>")
            ex = "\n      <exclusions>\n" + "\n".join(ex_lines) + "\n      </exclusions>"
        v = f"\n      <version>{version_}</version>" if version_ else ""
        sc = f"\n      <scope>{scope}</scope>" if scope else ""
        opt = f"\n      <optional>{'true' if optional else 'false'}</optional>" if optional is not None else ""
        return f"""    <dependency>
      <groupId>{group_id}</groupId>
      <artifactId>{artifact_id}</artifactId>{v}{sc}{opt}{ex}
    </dependency>"""

    deps: list[str] = []
    deps.append(dep(
        "org.springframework.boot", "spring-boot-starter-web",
        exclusions=[("org.springframework.boot", "spring-boot-starter-logging")]
    ))
    deps.append(dep("org.springframework.boot", "spring-boot-starter-validation"))
    deps.append(dep("org.springframework.boot", "spring-boot-devtools", optional=True))
    deps.append(dep(
        "org.egovframe.rte", "org.egovframe.rte.ptl.mvc",
        version_="${org.egovframe.rte.version}",
        exclusions=[("commons-logging", "commons-logging")]
    ))
    deps.append(dep("org.egovframe.rte", "org.egovframe.rte.psl.dataaccess", version_="${org.egovframe.rte.version}"))
    deps.append(dep("org.egovframe.rte", "org.egovframe.rte.fdl.idgnr", version_="${org.egovframe.rte.version}"))
    deps.append(dep("org.egovframe.rte", "org.egovframe.rte.fdl.property", version_="${org.egovframe.rte.version}"))
    deps.append(dep("org.springframework.boot", "spring-boot-starter-jdbc"))

    if db == "mysql":
        deps.append(dep("com.mysql", "mysql-connector-j", version_="${mysql.connector.version}", scope="runtime"))
    elif db == "postgresql":
        deps.append(dep("org.postgresql", "postgresql", version_="${postgresql.jdbc.version}", scope="runtime"))
    elif db == "oracle":
        deps.append(dep("com.oracle.database.jdbc", "ojdbc11", version_="${oracle.jdbc.version}", scope="runtime"))
    elif db in ("sqlite", "h2"):
        deps.append(dep("com.h2database", "h2", scope="runtime"))

    if fe == "jsp":
        deps.append(dep("org.apache.tomcat.embed", "tomcat-embed-jasper"))
        deps.append(dep("javax.servlet", "jstl"))

    deps.append(dep("org.projectlombok", "lombok", version_="${lombok.version}", optional=True))
    deps.append(dep("org.springframework.boot", "spring-boot-starter-test", scope="test"))

    pom = f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- path: pom.xml -->
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">

  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.egovframe.boot</groupId>
    <artifactId>org.egovframe.boot.starter.parent</artifactId>
    <version>4.3.0</version>
    <relativePath/>
  </parent>

  <groupId>{group_id}</groupId>
  <artifactId>{artifact_id}</artifactId>
  <version>{version}</version>
  <packaging>{packaging}</packaging>

  <properties>
    <java.version>11</java.version>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <mysql.connector.version>8.3.0</mysql.connector.version>
    <postgresql.jdbc.version>42.7.3</postgresql.jdbc.version>
    <oracle.jdbc.version>23.3.0.23.09</oracle.jdbc.version>
    <lombok.version>1.18.34</lombok.version>
    <org.egovframe.rte.version>4.3.0</org.egovframe.rte.version>
  </properties>

  <repositories>
    <repository>
      <id>egovframe</id>
      <url>https://maven.egovframe.go.kr/maven/</url>
    </repository>
  </repositories>

  <dependencies>
{chr(10).join(deps)}
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>

</project>
"""

    try:
        import xml.etree.ElementTree as _ET
        _ET.fromstring(pom)
    except Exception as e:
        raise RuntimeError(f"Generated pom.xml is not valid XML: {e}")

    return pom


def template_file_ops(cfg: ProjectConfig) -> List[Dict[str, Any]]:
    """Return template-managed files such as pom.xml, Maven wrapper, and application.properties."""
    ops: List[Dict[str, Any]] = []
    if _uses_maven_backend(cfg):
        ops.append({
            "path": "pom.xml",
            "purpose": "Maven build config (template, based on DB/frontend)",
            "content": render_pom_xml(cfg),
        })
        ops.append({
            "path": "mvnw",
            "purpose": "POSIX Maven wrapper bootstrap script",
            "content": render_mvnw(),
        })
        ops.append({
            "path": "mvnw.cmd",
            "purpose": "Windows Maven wrapper bootstrap script",
            "content": render_mvnw_cmd(),
        })
        ops.append({
            "path": ".mvn/wrapper/maven-wrapper.properties",
            "purpose": "Maven wrapper distribution metadata",
            "content": render_maven_wrapper_properties(),
        })
    ops.append({
        "path": "src/main/resources/application.properties",
        "purpose": "Spring Boot config (template, based on DB/frontend)",
        "content": render_application_properties(cfg),
    })
    return ops
