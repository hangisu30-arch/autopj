from __future__ import annotations
import re
import json
import textwrap
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from app.ui.state import ProjectConfig
from app.ui.java_import_fixer import fix_project_java_imports
from app.ui.ui_sanitize_common import allows_auth_sensitive_in_account_form
from app.io.react_builtin_repair import cleanup_leaked_backend_artifacts, ensure_react_backend_crud, ensure_react_frontend_crud
from app.io.vue_builtin_repair import ensure_vue_frontend_crud
# execution_core (embedded)
from execution_core.project_patcher import detect_boot_base_package, patch_application_properties, patch_boot_application, write_schema_sql, write_database_initializer, ensure_maven_wrapper
from execution_core.builtin_crud import builtin_file, schema_for, ddl, infer_schema_from_file_ops, extract_explicit_requirement_schemas, _snake, _java_type_from_sql_type, _camel_from_snake, _is_valid_java_identifier, _is_valid_column_identifier, _is_css_noise_fragment
from app.engine.analysis.schema_parser import SchemaParser
from execution_core.feature_rules import FEATURE_KIND_AUTH, FEATURE_KIND_CRUD, LOGIN_FIELD_CANDIDATES, choose_auth_fields, is_auth_kind
from execution_core.generator import _canonical_tasks_for_schema


_CREATE_TABLE_RE = re.compile(r'create\s+table\s+(?:if\s+not\s+exists\s+)?[`"]?([A-Za-z_][\w]*)[`"]?', re.IGNORECASE)
_DROP_TABLE_RE = re.compile(r'drop\s+table\s+(?:if\s+exists\s+)?[`"]?([A-Za-z_][\w]*)[`"]?', re.IGNORECASE)


def _strip_sql_comments(sql: str) -> str:
    body = str(sql or '')
    body = re.sub(r'/\*.*?\*/', '', body, flags=re.DOTALL)
    body = re.sub(r'(?m)^\s*--.*$', '', body)
    return body


def _split_sql_statements(sql: str) -> List[str]:
    body = _strip_sql_comments(sql)
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


def _drop_statement_table_name(sql: str) -> str:
    m = _DROP_TABLE_RE.search(str(sql or ''))
    return (m.group(1).strip().lower() if m else '')


def _normalize_create_statement(sql: str) -> str:
    normalized = str(sql or '').strip()
    return normalized if normalized.endswith(';') else normalized + ';'


def _normalize_recreate_sql_statements(statements: List[str]) -> List[str]:
    normalized_rows: List[Tuple[str, str, str]] = []
    create_tables = {name for name in (_statement_table_name(stmt) for stmt in (statements or [])) if name}
    for stmt in statements or []:
        raw = str(stmt or '').strip()
        if not raw:
            continue
        create_name = _statement_table_name(raw)
        if create_name:
            normalized_rows.append(('create', create_name, _normalize_create_statement(raw)))
            continue
        drop_name = _drop_statement_table_name(raw)
        if drop_name and drop_name in create_tables:
            continue
        normalized_rows.append(('other', '', raw if raw.endswith(';') else raw + ';'))

    output: List[str] = []
    emitted_drop: set[str] = set()
    for kind, table_name, stmt in normalized_rows:
        if kind == 'create':
            if table_name and table_name not in emitted_drop:
                output.append(f"DROP TABLE IF EXISTS `{table_name}`;")
                emitted_drop.add(table_name)
            output.append(stmt)
        else:
            output.append(stmt)
    return output


def _merge_sql_statements(preferred: List[str], existing: List[str]) -> List[str]:
    merged: List[str] = []
    seen_tables: Dict[str, int] = {}

    def append_stmt(stmt: str) -> None:
        normalized = stmt.strip()
        if not normalized:
            return
        table_name = _statement_table_name(normalized)
        if table_name:
            idx = seen_tables.get(table_name)
            if idx is not None:
                merged[idx] = normalized if normalized.endswith(';') else normalized + ';'
                return
            seen_tables[table_name] = len(merged)
        if normalized not in merged:
            merged.append(normalized if normalized.endswith(';') else normalized + ';')

    for stmt in existing or []:
        append_stmt(stmt)
    for stmt in preferred or []:
        append_stmt(stmt)
    return merged


def _schema_sql_path(project_root: Path, filename: str = 'schema.sql') -> Path:
    return project_root / 'src/main/resources' / filename


def _load_sql_statements_from_project(project_root: Path, filename: str = 'schema.sql') -> List[str]:
    path = _schema_sql_path(project_root, filename)
    if not path.exists():
        return []
    return _split_sql_statements(path.read_text(encoding='utf-8'))


def _expected_table_names_from_sql(statements: List[str]) -> List[str]:
    names: List[str] = []
    for stmt in statements or []:
        table_name = _statement_table_name(stmt)
        if table_name and table_name not in names:
            names.append(table_name)
    return names


def _existing_tables_in_mysql(cur: Any, database: str) -> List[str]:
    cur.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = %s",
        (database,),
    )
    return [str(row[0]).strip().lower() for row in (cur.fetchall() or []) if row and row[0]]
_REACT_APP_ROOT_FILES = {
    "package.json",
    "vite.config.js",
    "index.html",
    "jsconfig.json",
    ".env.development",
    ".env.production",
}
_REACT_APP_DIR_PREFIXES = (
    "src/api/",
    "src/components/",
    "src/config/",
    "src/constants/",
    "src/css/",
    "src/hooks/",
    "src/pages/",
    "src/routes/",
    "src/utils/",
    "public/",
)
_VUE_APP_ROOT_FILES = {
    "package.json",
    "vite.config.js",
    "index.html",
    "jsconfig.json",
    ".env.development",
    ".env.production",
}
_VUE_APP_DIR_PREFIXES = (
    "src/api/",
    "src/assets/",
    "src/components/",
    "src/constants/",
    "src/router/",
    "src/stores/",
    "src/views/",
    "public/",
)
_BACKEND_SRC_PREFIXES = (
    "src/main/java/",
    "src/main/resources/",
    "src/main/webapp/",
)
_REACT_RUNTIME_BASELINE = {
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
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "./build",
  },
});
""",
    "index.html": """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>App</title>
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
    ".env.development": "VITE_API_BASE_URL=\n",
    ".env.production": "VITE_API_BASE_URL=\n",
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
    "src/routes/index.jsx": """import { createBrowserRouter } from "react-router-dom";
import ROUTES from "../constants/routes";
import MainPage from "../pages/main/MainPage";
const router = createBrowserRouter([
  {
    path: ROUTES.MAIN,
    element: <MainPage />,
  },
]);
export default router;
""",
    "src/constants/routes.js": """const ROUTES = {
  MAIN: "/",
};
export default ROUTES;
""",
    "src/pages/main/MainPage.jsx": """export default function MainPage() {
  return (
    <div className="page-shell">
      <div className="page-card">
        <h1>Main</h1>
      </div>
    </div>
  );
}
""",
    "src/api/client.js": """export async function apiRequest(path, options = {}) {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || "";
  const response = await fetch(`${baseUrl}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
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
_VUE_RUNTIME_BASELINE = {
    "package.json": """{
  "name": "frontend-vue",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "vue": "^3",
    "vue-router": "^4"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5",
    "vite": "^5"
  }
}
""",
    "vite.config.js": """import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import path from "node:path";
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "./dist",
  },
});
""",
    "jsconfig.json": """{
  "compilerOptions": {
    "baseUrl": "src",
    "paths": {
      "@/*": ["*"]
    }
  },
  "include": ["src/**/*"]
}
""",
    ".env.development": "VITE_API_BASE_URL=\n",
    ".env.production": "VITE_API_BASE_URL=\n",
    "index.html": """<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>App</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
""",
    "src/main.js": """import { createApp } from "vue";
import App from "./App.vue";
import router from "./router";
createApp(App).use(router).mount("#app");
""",
    "src/App.vue": """<template>
  <router-view />
</template>
""",
    "src/router/index.js": """import { createRouter, createWebHistory } from "vue-router";
import ROUTES from "../constants/routes";
const routes = [
  {
    path: ROUTES.MAIN,
    redirect: ROUTES.MEMBER_LIST,
  },
];
const router = createRouter({{
  history: createWebHistory(),
  routes,
}});
export default router;
""",
    "src/constants/routes.js": """const ROUTES = {
  MAIN: "/",
  MEMBER_LIST: "/member/list",
  MEMBER_CREATE: "/member/create",
  MEMBER_DETAIL: (memberId = ":memberId") => `/member/detail/${memberId}`,
  MEMBER_EDIT: (memberId = ":memberId") => `/member/edit/${memberId}`,
};
export default ROUTES;
""",
    "src/api/client.js": """const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").trim();
export async function apiRequest(path, options = {}) {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  const text = await response.text();
  return text ? JSON.parse(text) : null;
}
""",
    "src/stores/index.js": """export {};
""",
}
def _react_scaffold_real_path(project_root: Path, rel_path: str) -> Path:
    return project_root / "frontend" / "react" / Path(rel_path)
def _looks_like_valid_react_scaffold(rel_path: str, content: str) -> bool:
    body = (content or "").strip()
    if not body:
        return False
    if body.lower() == "empty content":
        return False
    if rel_path in {"package.json", "jsconfig.json"}:
        try:
            obj = json.loads(body)
        except Exception:
            return False
        if not isinstance(obj, dict):
            return False
        if rel_path == "package.json":
            scripts = obj.get("scripts") or {}
            deps = obj.get("dependencies") or {}
            dev_deps = obj.get("devDependencies") or {}
            return (
                isinstance(scripts, dict)
                and scripts.get("dev") == "vite"
                and scripts.get("build") == "vite build"
                and scripts.get("preview") == "vite preview"
                and isinstance(deps, dict)
                and "vue" in deps
                and "vue-router" in deps
                and isinstance(dev_deps, dict)
                and "vite" in dev_deps
                and "@vitejs/plugin-vue" in dev_deps
            )
        return True
    if rel_path == "index.html":
        return '<div id="root"></div>' in body and '/src/main.jsx' in body
    if rel_path == "vite.config.js":
        return ('defineConfig' in body and '@vitejs/plugin-react' in body and '/api' in body and 'localhost:8080' in body and '5173' in body)
    if rel_path == "src/main.jsx":
        return 'ReactDOM.createRoot' in body and 'App' in body
    if rel_path == "src/App.jsx":
        return 'RouterProvider' in body or 'export default function App' in body
    if rel_path == "src/routes/index.jsx":
        return 'createBrowserRouter' in body and 'export default router' in body
    if rel_path == "src/constants/routes.js":
        return 'const ROUTES' in body and 'export default ROUTES' in body
    if rel_path == "src/pages/main/MainPage.jsx":
        return 'export default function MainPage' in body
    if rel_path == "src/api/client.js":
        return 'fetch(' in body and 'export async function apiRequest' in body
    if rel_path.startswith('src/css/'):
        return True
    if rel_path == 'jsconfig.json':
        return 'baseUrl' in body and '@/*' in body
    if rel_path in {'.env.development', '.env.production'}:
        return 'VITE_API_BASE_URL=' in body
    return True
def _ensure_react_runtime_baseline(project_root: Path, overwrite: bool = False) -> Dict[str, str]:
    report: Dict[str, str] = {}
    for rel_path, content in _REACT_RUNTIME_BASELINE.items():
        target = _react_scaffold_real_path(project_root, rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            existing = target.read_text(encoding='utf-8', errors='ignore')
            if _looks_like_valid_react_scaffold(rel_path, existing):
                report[rel_path] = 'kept'
                continue
        target.write_text(content, encoding='utf-8')
        report[rel_path] = 'written'
    return report
def _should_protect_react_runtime_file(rel_path: str, content: str) -> bool:
    if rel_path.startswith('frontend/react/'):
        rel_path = rel_path[len('frontend/react/'):]
    if rel_path not in _REACT_RUNTIME_BASELINE:
        return False
    return not _looks_like_valid_react_scaffold(rel_path, content)
def _is_react_app_relative_path(rel_path: str) -> bool:
    p = (rel_path or "").replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if not p:
        return False
    if p.startswith("frontend/react/"):
        p = p[len("frontend/react/"):]
    if p in _REACT_APP_ROOT_FILES:
        return True
    if p.startswith(_BACKEND_SRC_PREFIXES):
        return False
    return p.startswith(_REACT_APP_DIR_PREFIXES)
def _map_frontend_rel_path(rel_path: str, frontend_key: str) -> str:
    p = (rel_path or "").replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    frontend = (frontend_key or "").strip().lower()
    if not p:
        return p
    if frontend == "react":
        if p.startswith("frontend/react/"):
            return p
        if _is_react_app_relative_path(p):
            return f"frontend/react/{p}"
        return p
    if frontend == "vue":
        if p.startswith("frontend/vue/"):
            return p
        if _is_vue_app_relative_path(p):
            return f"frontend/vue/{p}"
        return p
    return p
def _vue_scaffold_real_path(project_root: Path, rel_path: str) -> Path:
    return project_root / "frontend" / "vue" / Path(rel_path)
def _looks_like_valid_vue_scaffold(rel_path: str, content: str) -> bool:
    body = (content or "").strip()
    if not body:
        return False
    if body.lower() == "empty content":
        return False
    if rel_path in {"package.json", "jsconfig.json"}:
        try:
            obj = json.loads(body)
        except Exception:
            return False
        if not isinstance(obj, dict):
            return False
        if rel_path == "package.json":
            scripts = obj.get("scripts") or {}
            deps = obj.get("dependencies") or {}
            dev_deps = obj.get("devDependencies") or {}
            return (
                isinstance(scripts, dict)
                and scripts.get("dev") == "vite"
                and scripts.get("build") == "vite build"
                and scripts.get("preview") == "vite preview"
                and isinstance(deps, dict)
                and "vue" in deps
                and "vue-router" in deps
                and isinstance(dev_deps, dict)
                and "vite" in dev_deps
                and "@vitejs/plugin-vue" in dev_deps
            )
        return True
    if rel_path == "index.html":
        return '<div id="app"></div>' in body and '/src/main.js' in body and ('type="module"' in body or "type='module'" in body)
    if rel_path == "vite.config.js":
        return 'defineConfig' in body and '@vitejs/plugin-vue' in body and '/api' in body and 'localhost:8080' in body and '5173' in body
    if rel_path == "src/main.js":
        return 'createApp' in body and 'App.vue' in body and '.use(router)' in body and 'pinia' not in body.lower() and 'createpinia' not in body.lower()
    if rel_path == "src/App.vue":
        return '<router-view' in body and 'Home' not in body and 'About' not in body and 'HelloWorld' not in body and 'TheWelcome' not in body
    if rel_path == "src/router/index.js":
        return 'createRouter' in body and 'createWebHistory' in body and 'export default' in body and ('/list' in body or 'redirect:' in body)
    if rel_path == "src/constants/routes.js":
        return 'const ROUTES' in body and 'MEMBER_LIST' in body and 'export default ROUTES' in body
    if rel_path == "src/api/client.js":
        return 'fetch(' in body and 'apiRequest' in body
    if rel_path.startswith('src/views/') and rel_path.endswith('.vue'):
        return '<template>' in body and '<script setup>' in body
    if rel_path == 'jsconfig.json':
        return 'baseUrl' in body and '@/*' in body
    if rel_path in {'.env.development', '.env.production'}:
        return 'VITE_API_BASE_URL=' in body
    return True
def _vue_baseline_entity_and_schema(preferred_entity: str | None, schema_map: Dict[str, Any] | None) -> Tuple[str, Any]:
    if schema_map:
        if preferred_entity and preferred_entity in schema_map:
            return preferred_entity, schema_map[preferred_entity]
        for entity, schema in schema_map.items():
            if schema is not None:
                return entity, schema
    entity = (preferred_entity or "Member").strip() or "Member"
    schema = schema_for(entity)
    return entity, schema
def _build_vue_runtime_baseline(preferred_entity: str | None = None, schema_map: Dict[str, Any] | None = None) -> Dict[str, str]:
    baseline = dict(_VUE_RUNTIME_BASELINE)
    entity, schema = _vue_baseline_entity_and_schema(preferred_entity, schema_map)
    ev = getattr(schema, "entity_var", None) or (entity[:1].lower() + entity[1:])
    id_prop = getattr(schema, "id_prop", "id") or "id"
    route_key = ev.upper()
    baseline["src/constants/routes.js"] = f"""const ROUTES = {{
  MAIN: "/",
  {route_key}_LIST: "/{ev}/list",
  {route_key}_CREATE: "/{ev}/create",
  {route_key}_DETAIL: ({id_prop} = ":{id_prop}") => `/{ev}/detail/${{{id_prop}}}` ,
  {route_key}_EDIT: ({id_prop} = ":{id_prop}") => `/{ev}/edit/${{{id_prop}}}` ,
}};
export default ROUTES;
"""
    baseline["src/router/index.js"] = f"""import {{ createRouter, createWebHistory }} from "vue-router";
import ROUTES from "@/constants/routes";
import {entity}List from "@/views/{ev}/{entity}List.vue";
import {entity}Detail from "@/views/{ev}/{entity}Detail.vue";
import {entity}Form from "@/views/{ev}/{entity}Form.vue";
const routes = [
  {{ path: ROUTES.MAIN, redirect: ROUTES.{route_key}_LIST }},
  {{ path: ROUTES.{route_key}_LIST, name: "{ev}-list", component: {entity}List }},
  {{ path: "/{ev}/create", name: "{ev}-create", component: {entity}Form }},
  {{ path: "/{ev}/detail/:{id_prop}", name: "{ev}-detail", component: {entity}Detail, props: true }},
  {{ path: "/{ev}/edit/:{id_prop}", name: "{ev}-edit", component: {entity}Form, props: true }},
];
const router = createRouter({{
  history: createWebHistory(),
  routes,
}});
export default router;
"""
    baseline["src/App.vue"] = f"""<template>
  <div>
    <nav style="display:flex;gap:12px;padding:12px 16px;background:#222;">
      <router-link style="color:#fff" :to="ROUTES.{route_key}_LIST">{entity} List</router-link>
      <router-link style="color:#fff" :to="ROUTES.{route_key}_CREATE">{entity} Create</router-link>
    </nav>
    <router-view />
  </div>
</template>
<script setup>
import ROUTES from "@/constants/routes";
</script>
"""
    return baseline
def _ensure_vue_runtime_baseline(project_root: Path, preferred_entity: str | None = None, schema_map: Dict[str, Any] | None = None, overwrite: bool = False) -> Dict[str, str]:
    report: Dict[str, str] = {}
    for rel_path, content in _build_vue_runtime_baseline(preferred_entity, schema_map).items():
        target = _vue_scaffold_real_path(project_root, rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not overwrite:
            existing = target.read_text(encoding='utf-8', errors='ignore')
            if _looks_like_valid_vue_scaffold(rel_path, existing):
                report[rel_path] = "kept"
                continue
        target.write_text(content, encoding='utf-8')
        report[rel_path] = "written"
    return report
def _should_protect_vue_runtime_file(rel_path: str, content: str) -> bool:
    if rel_path.startswith('frontend/vue/'):
        rel_path = rel_path[len('frontend/vue/'):]
    if rel_path not in _VUE_RUNTIME_BASELINE:
        return False
    return not _looks_like_valid_vue_scaffold(rel_path, content)
def _is_vue_app_relative_path(rel_path: str) -> bool:
    p = (rel_path or '').replace('\\', '/')
    while p.startswith('./'):
        p = p[2:]
    if not p:
        return False
    if p.startswith('frontend/vue/'):
        p = p[len('frontend/vue/'):]
    if p in _VUE_APP_ROOT_FILES:
        return True
    if p.startswith(_BACKEND_SRC_PREFIXES):
        return False
    return p.startswith(_VUE_APP_DIR_PREFIXES)
try:
    from execution_core.project_patcher import patch_pom_mysql_driver  # type: ignore
except Exception:
    patch_pom_mysql_driver = None  # type: ignore
try:
    from execution_core.project_patcher import patch_pom_jsp_support  # type: ignore
except Exception:
    patch_pom_jsp_support = None  # type: ignore
try:
    from execution_core.project_patcher import patch_datasource_properties  # type: ignore
except Exception:
    patch_datasource_properties = None  # type: ignore
def _load_bundled_db_conf() -> Dict[str, Any]:
    try:
        cfg_path = Path(__file__).resolve().parents[2] / "execution_core" / "config.json"
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        return data.get("database") or data.get("db") or {}
    except Exception:
        return {}
def _mysql_config_from_cfg(cfg: ProjectConfig) -> Dict[str, Any]:
    # UI 입력값 우선, 비어 있으면 bundled execution_core/config.json 기본값 사용
    bundled = _load_bundled_db_conf()
    return {
        "host": bundled.get("host") or "localhost",
        "port": bundled.get("port") or 3306,
        "user": (cfg.db_login_id or bundled.get("username") or bundled.get("user") or ""),
        "password": (cfg.db_password or bundled.get("password") or ""),
        "database": (cfg.db_name or bundled.get("database") or bundled.get("name") or ""),
    }
_JAVA_KEYWORDS = {"abstract","assert","boolean","break","byte","case","catch","char","class","const","continue","default","do","double","else","enum","extends","final","finally","float","for","goto","if","implements","import","instanceof","int","interface","long","native","new","package","private","protected","public","return","short","static","strictfp","super","switch","synchronized","this","throw","throws","transient","try","void","volatile","while","true","false","null","record","sealed","permits","var","yield"}

def _sanitize_package_segment(s: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9_]+", "", (s or "").strip())
    if not raw:
        return "app"
    seg = raw[0].lower() + raw[1:]
    seg = re.sub(r"^[^a-zA-Z_]+", "", seg)
    seg = seg or "app"
    if seg in _JAVA_KEYWORDS:
        return f"{seg}_"
    return seg

def _strip_logical_tb_prefix(name: str) -> str:
    raw = re.sub(r"[^A-Za-z0-9_]+", "", str(name or "").strip())
    if not raw:
        return ""
    low = raw.lower()
    if low in {"tb", "tb_"}:
        return ""
    if low.startswith("tb_") and len(raw) > 3:
        raw = raw[3:]
    elif low.startswith("tb") and len(raw) > 2:
        raw = raw[2:]
    raw = re.sub(r"^_+", "", raw)
    return raw or ""

def _normalize_module_hint_token(token: str) -> str:
    low = str(token or '').strip().lower()
    if not low:
        return ''
    if low in {'tb', 'tb_'}:
        return ''
    if low.startswith('tb_'):
        low = low[3:]
    low = re.sub(r'^_+', '', low)
    if not low or low in {'comment', 'comments', 'varchar', 'datetime', 'table', 'column', 'columns'}:
        return ''
    return low


def _ensure_tb_table_name(name: str) -> str:
    low = re.sub(r'[^a-z0-9_]+', '_', str(name or '').strip().lower()).strip('_')
    if not low:
        return 'tb_item'
    if low in {'tb', 'tb_'}:
        return 'tb_item'
    if low.startswith('tb_'):
        return low
    return f'tb_{low}'
def _entity_var_from_name(entity: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", entity or "").strip()
    if not cleaned:
        return "item"
    if cleaned.isupper():
        return cleaned.lower()
    m = re.match(r"^([A-Z]{2,})([A-Z][a-z].*)$", cleaned)
    if m:
        return m.group(1).lower() + m.group(2)
    return cleaned[:1].lower() + cleaned[1:]
def _project_segment_from_base(base_package: str) -> str:
    parts = [p for p in (base_package or '').split('.') if p]
    if not parts:
        return 'app'
    if len(parts) >= 2 and parts[0] == 'egovframework':
        return parts[1]
    return parts[-1]
def _is_generic_entity_var(ev: str) -> bool:
    return (ev or "").lower() in {"ui", "screen", "page", "view", "app", "main", "home", "form", "item", "entity", "domain", "record", "data"}
def _semantic_module_tokens(*texts: str) -> List[str]:
    layer_tokens = {
        'src', 'main', 'java', 'resources', 'webapp', 'webinf', 'web', 'views', 'view', 'jsp',
        'controller', 'service', 'impl', 'mapper', 'vo', 'config', 'xml', 'sql', 'schema', 'db',
        'save', 'delete', 'update', 'insert', 'select', 'list', 'detail', 'form', 'index', 'mybatis',
        'egovframework', 'com', 'org', 'http', 'https', 'localhost', 'do', 'path', 'target', 'classes', 'package', 'import'
    }
    generic_tokens = {
        'ui', 'screen', 'page', 'pages', 'view', 'views', 'main', 'home', 'app', 'crud', 'manage',
        'manager', 'module', 'feature', 'template', 'sample', 'example', 'default', 'common', 'test', 'create', 'define', 'implement', 'build', 'make', 'write', 'generate'
    }
    out: List[str] = []
    seen = set()
    for text in texts:
        if not text:
            continue
        for token in re.findall(r'[A-Za-z][A-Za-z0-9_]*', str(text)):
            low = _normalize_module_hint_token(token)
            if not low or low in layer_tokens or low in generic_tokens:
                continue
            if low not in seen:
                seen.add(low)
                out.append(low)
    return out
def _infer_module_segment(base_package: str, rel_path: str = '', content: str = '', extra_text: str = '') -> str:
    rel = (rel_path or '').replace('\\', '/')
    filename = Path(rel).name
    filename_entity = _entity_from_filename(filename)
    filename_entity_var = _entity_var_from_name(filename_entity) if filename_entity else ''
    project_seg = _project_segment_from_base(base_package)
    tokens = _semantic_module_tokens(extra_text, content, rel)
    filtered: List[str] = []
    for token in tokens:
        if token == project_seg.lower():
            continue
        if filename_entity_var and token == filename_entity_var.lower():
            continue
        if token.endswith(("controller", "service", "mapper", "vo", "impl", "config")):
            continue
        filtered.append(token)
    if filename_entity_var and not _is_generic_entity_var(filename_entity_var):
        return _sanitize_package_segment(filename_entity_var)
    if filtered:
        return _sanitize_package_segment(filtered[0])
    if filename_entity_var:
        return _sanitize_package_segment(filename_entity_var)
    return ''
def _resolve_base_package(project_root: Path, cfg: ProjectConfig) -> str:
    _ = detect_boot_base_package(project_root)
    preferred_name = _sanitize_package_segment(cfg.project_name or project_root.name)
    return f"egovframework.{preferred_name}"
_CRUD_SUFFIXES: Tuple[str, ...] = (
    'ServiceImpl.java',
    'Service.java',
    'Mapper.java',
    'VO.java',
    'RestController.java',
    'Controller.java',
    'Mapper.xml',
    'List.jsp',
    'Detail.jsp',
    'Form.jsp',
    '_SQL_mysql.xml',
    '_SQL_oracle.xml',
    '_SQL_postgresql.xml',
    '_SQL.xml',
)
def _split_crud_filename(filename: str) -> Tuple[str, str]:
    name = (filename or '').strip()
    for suf in _CRUD_SUFFIXES:
        if name.endswith(suf) and len(name) > len(suf):
            return name[:-len(suf)], suf
    return '', ''
def _entity_weight_for_suffix(suffix: str) -> int:
    if suffix in ('VO.java', 'Service.java', 'ServiceImpl.java', 'Mapper.java', 'Mapper.xml', '_SQL.xml', '_SQL_mysql.xml', '_SQL_oracle.xml', '_SQL_postgresql.xml'):
        return 3
    if suffix in ('Controller.java', 'List.jsp', 'Detail.jsp', 'Form.jsp'):
        return 1
    return 1
def _preferred_crud_entity(file_ops: List[Dict[str, Any]]) -> str:
    scores: Dict[str, int] = {}
    for item in file_ops or []:
        path = (item.get('path') or '').replace('\\', '/')
        entity, suffix = _split_crud_filename(Path(path).name)
        if not entity:
            continue
        logical = _strip_logical_tb_prefix(entity) or entity
        scores[logical] = scores.get(logical, 0) + _entity_weight_for_suffix(suffix)
    if not scores:
        return ''
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0].lower()))[0][0]

def _rewrite_filename_to_preferred_entity(filename: str, preferred_entity: str) -> str:
    entity, suffix = _split_crud_filename(filename)
    if not entity or not preferred_entity:
        return filename
    logical_entity = _strip_logical_tb_prefix(entity) or entity
    logical_preferred = _strip_logical_tb_prefix(preferred_entity) or preferred_entity
    if logical_entity == logical_preferred:
        return logical_preferred + suffix
    if entity == preferred_entity:
        return filename
    if entity.lower() == preferred_entity.lower():
        return logical_preferred + suffix
    return filename
def _ensure_mybatis_config(project_root: Path, base_package: str) -> Path:
    pkg_path = base_package.replace(".", "/")
    p = project_root / f"src/main/java/{pkg_path}/config/MyBatisConfig.java"
    p.parent.mkdir(parents=True, exist_ok=True)
    content = f"""package {base_package}.config;
import javax.sql.DataSource;
import org.apache.ibatis.session.SqlSessionFactory;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.mybatis.spring.annotation.MapperScan;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
@Configuration
@MapperScan(basePackages = "{base_package}", annotationClass = org.apache.ibatis.annotations.Mapper.class, sqlSessionFactoryRef = "sqlSessionFactory")
public class MyBatisConfig {{
    @Bean
    public SqlSessionFactory sqlSessionFactory(DataSource dataSource, ApplicationContext applicationContext) throws Exception {{
        SqlSessionFactoryBean factoryBean = new SqlSessionFactoryBean();
        factoryBean.setDataSource(dataSource);
        Resource[] mapperResources = applicationContext.getResources("classpath*:egovframework/mapper/**/*.xml");
        factoryBean.setMapperLocations(mapperResources);
        factoryBean.setTypeAliasesPackage("{base_package}");
        org.apache.ibatis.session.Configuration configuration = new org.apache.ibatis.session.Configuration();
        configuration.setMapUnderscoreToCamelCase(true);
        factoryBean.setConfiguration(configuration);
        return factoryBean.getObject();
    }}
    @Bean
    public SqlSessionTemplate sqlSessionTemplate(SqlSessionFactory sqlSessionFactory) {{
        return new SqlSessionTemplate(sqlSessionFactory);
    }}
}}
"""
    p.write_text(content, encoding="utf-8")
    return p
def _strip_first_path_comment(content: str) -> str:
    s = content or ""
    lines = s.splitlines()
    if not lines:
        return s
    first = lines[0].lstrip()
    if first.startswith("// path:") or first.startswith("<!-- path:") or first.startswith("# path:") or first.startswith("-- path:") or first.startswith("/* path:"):
        return "\n".join(lines[1:]).lstrip("\n")
    return s
def _canonical_crud_logical_path(filename: str) -> str:
    name = (filename or "").strip()
    entity, suffix = _split_crud_filename(name)
    entity = _strip_logical_tb_prefix(entity) or entity
    if not entity:
        return ""
    if suffix == "VO.java":
        return f"java/service/vo/{entity}{suffix}"
    if suffix == "Mapper.java":
        return f"java/service/mapper/{entity}{suffix}"
    if suffix == "ServiceImpl.java":
        return f"java/service/impl/{entity}{suffix}"
    if suffix == "Service.java":
        return f"java/service/{entity}{suffix}"
    if suffix in ("Controller.java", "RestController.java"):
        return f"java/controller/{entity}{suffix}"
    if suffix in ("List.jsp", "Detail.jsp", "Form.jsp"):
        ev = _entity_var_from_name(entity)
        return f"jsp/{ev}/{ev}{suffix}"
    # Treat legacy iBATIS sqlMap mapper filenames as the canonical MyBatis mapper.
    # This prevents invalid XML (beans/sqlMap/SqlMapClientTemplate) from being written and then loaded by
    # mybatis mapper-locations (classpath*:egovframework/mapper/**/*.xml).
    if suffix in ("Mapper.xml", "_SQL.xml", "_SQL_mysql.xml", "_SQL_oracle.xml", "_SQL_postgresql.xml"):
        return f"mapper/{entity.lower()}/{entity}Mapper.xml"
    return ""
def _entity_from_filename(filename: str) -> str:
    entity, _ = _split_crud_filename(filename)
    return _strip_logical_tb_prefix(entity) or entity


def _entity_alias_tokens(entity: str) -> List[str]:
    raw = str(entity or '').strip().lower()
    if not raw:
        return []
    tokens: List[str] = []
    for cand in (raw, _entity_var_from_name(entity).lower(), _snake(entity).lower()):
        cand = re.sub(r'[^a-z0-9_]+', '', cand)
        if cand and cand not in tokens:
            tokens.append(cand)
    if raw.endswith('ies'):
        singular = raw[:-3] + 'y'
        plural = raw
    elif raw.endswith('s') and not raw.endswith('ss'):
        singular = raw[:-1]
        plural = raw
    else:
        singular = raw
        plural = raw + 's'
    for cand in (singular, plural):
        cand = re.sub(r'[^a-z0-9_]+', '', cand)
        if cand and cand not in tokens:
            tokens.append(cand)
    return tokens


def _op_matches_entity(item: Dict[str, Any], entity: str) -> bool:
    path = (item.get("path") or "").replace("\\", "/")
    purpose = item.get("purpose") or ""
    content = item.get("content") or ""
    entity_name = (entity or "").strip()
    if not entity_name:
        return False
    aliases = _entity_alias_tokens(entity_name)
    if not aliases:
        return False
    stem_entity = _entity_from_filename(Path(path).name).lower()
    if stem_entity in aliases:
        return True
    path_low = path.lower()
    for alias in aliases:
        if f"/{alias}/" in path_low:
            return True
    blob = f"{path}\n{purpose}\n{content}".lower()
    for alias in aliases:
        if re.search(rf"\b{re.escape(alias)}\b", blob):
            return True
    return False

def _schema_columns(schema: Any) -> set[str]:
    return {str(col or '').strip().lower() for _prop, col, _jt in (getattr(schema, 'fields', []) or []) if str(col or '').strip()}


def _schema_supports_login_contract(schema: Any) -> bool:
    cols = _schema_columns(schema)
    return 'login_id' in cols and ('login_password' in cols or 'password' in cols)


def _schemas_can_share_table(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return False
    left_cols = _schema_columns(left)
    right_cols = _schema_columns(right)
    if not left_cols or not right_cols:
        return False
    if left_cols == right_cols:
        return True
    if _schema_supports_login_contract(left) and _schema_supports_login_contract(right):
        overlap = len(left_cols & right_cols)
        return overlap >= min(len(left_cols), len(right_cols), 2)
    return False


def _copy_schema_with_feature_kind(schema: Any, *, entity_name: str, feature_kind: str, unified_auth: bool = False, cert_login: bool = False, jwt_login: bool = False) -> Any:
    if schema is None:
        return None
    cloned = schema_for(
        entity_name,
        inferred_fields=list(getattr(schema, 'fields', []) or []),
        table=str(getattr(schema, 'table', '') or '').strip() or None,
        feature_kind=feature_kind,
        strict_fields=True,
        unified_auth=unified_auth,
        cert_login=cert_login,
        jwt_login=jwt_login,
        field_comments=dict(getattr(schema, 'field_comments', {}) or {}),
        field_db_types=dict(getattr(schema, 'field_db_types', {}) or {}),
        field_nullable=dict(getattr(schema, 'field_nullable', {}) or {}),
        field_unique=dict(getattr(schema, 'field_unique', {}) or {}),
        field_auto_increment=dict(getattr(schema, 'field_auto_increment', {}) or {}),
        field_defaults=dict(getattr(schema, 'field_defaults', {}) or {}),
        field_references=dict(getattr(schema, 'field_references', {}) or {}),
        table_comment=str(getattr(schema, 'table_comment', '') or '').strip(),
        db_vendor=str(getattr(schema, 'db_vendor', '') or '').strip() or None,
    )
    try:
        cloned.authority = str(getattr(schema, 'authority', '') or 'shared-auth')
    except Exception:
        pass
    return cloned


def _has_shared_auth_table_request(file_ops: List[Dict[str, Any]], cfg: ProjectConfig) -> bool:
    joined = '\n'.join(
        str(part or '')
        for item in (file_ops or [])
        for part in ((item or {}).get('path'), (item or {}).get('purpose'), (item or {}).get('content'))
        if str(part or '').strip()
    )
    if getattr(cfg, 'extra_requirements', None):
        joined += '\n' + str(cfg.extra_requirements or '')
    low = joined.lower()
    if not low.strip():
        return False
    shared_markers = (
        '같은 테이블', '동일 테이블', '하나의 테이블', '단일 테이블', '기존 로그인과 연동',
        '회원가입 후 로그인', '회원가입한 계정으로 로그인', '같은 컬럼 체계', '하나의 계정 체계',
        '통합된 계정 구조', 'same table', 'single table', 'shared table', 'reuse the same table',
    )
    return any(token in low for token in shared_markers)


def _find_shared_auth_schema_candidate(schema_map: Dict[str, Any]) -> Optional[Any]:
    ranked: List[Tuple[int, Any]] = []
    for entity, schema in (schema_map or {}).items():
        if schema is None:
            continue
        if is_auth_kind(getattr(schema, 'feature_kind', None) or ''):
            continue
        if not _schema_supports_login_contract(schema):
            continue
        score = 0
        authority = str(getattr(schema, 'authority', '') or '').lower()
        if authority in {'explicit', 'mapper', 'ddl'}:
            score += 10
        table_name = str(getattr(schema, 'table', '') or '').lower()
        if table_name.startswith('tb_'):
            score += 3
        if any(token in table_name for token in ('member', 'user', 'account')):
            score += 4
        entity_low = str(entity or '').lower()
        if entity_low in {'member', 'user', 'account'}:
            score += 4
        score += len(getattr(schema, 'fields', []) or [])
        ranked.append((score, schema))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def _normalize_schema_tables(schema_map: Dict[str, Any]) -> Dict[str, Any]:
    used_tables: Dict[str, Any] = {}
    normalized: Dict[str, Any] = {}
    for entity, schema in (schema_map or {}).items():
        if schema is None:
            normalized[entity] = schema
            continue
        entity_name = getattr(schema, 'entity', None) or entity
        raw_table = str(getattr(schema, 'table', '') or '').strip().lower()
        desired = _ensure_tb_table_name(re.sub(r'[^a-z0-9_]+', '_', raw_table) or _snake(entity_name))
        fallback = _ensure_tb_table_name(_snake(entity_name))
        owner_schema = used_tables.get(desired)
        if owner_schema is not None and not _schemas_can_share_table(owner_schema, schema) and getattr(owner_schema, 'entity', None) != entity_name:
            desired = fallback
        suffix = 2
        while desired in used_tables and not _schemas_can_share_table(used_tables.get(desired), schema) and getattr(used_tables.get(desired), 'entity', None) != entity_name:
            desired = f"{fallback}_{suffix}"
            suffix += 1
        if getattr(schema, 'table', None) != desired:
            try:
                schema.table = desired
            except Exception:
                pass
        used_tables.setdefault(desired, schema)
        normalized[entity] = schema
    return normalized
def _schema_field_specs_from_template(template: List[Tuple[str, str]]) -> List[Tuple[str, str, str]]:
    specs: List[Tuple[str, str, str]] = []
    for col, db_type in template:
        prop = _camel_from_snake(col)
        specs.append((prop, col, _java_type_from_sql_type(db_type, prop)))
    return specs
def _schema_has_business_drift(schema: Any, template: List[Tuple[str, str]]) -> bool:
    fields = list(getattr(schema, 'fields', []) or [])
    if not fields:
        return True
    authority = str(getattr(schema, 'authority', '') or '').strip().lower()
    if authority in {'explicit', 'mapper'}:
        return False
    current_table = str(getattr(schema, 'table', '') or '').strip().lower()
    current_id = str(getattr(schema, 'id_column', '') or '').strip().lower()
    current_cols = {str(col or '').lower() for _prop, col, _jt in fields if str(col or '').strip()}
    current_props = {str(prop or '').lower() for prop, _col, _jt in fields if str(prop or '').strip()}
    # Preserve non-generic schemas that already look domain-specific.
    if current_table not in {'', 'item', 'data', 'entity', 'record'} and current_id not in {'', 'id'} and len(current_cols) >= 3:
        return False
    template_cols = {col.lower() for col, _ in template}
    template_props = {_camel_from_snake(col).lower() for col, _ in template}
    for prop, col, _jt in fields:
        token = f"{prop} {col}".lower()
        if not _is_valid_java_identifier(prop) or not _is_valid_column_identifier(col) or _is_css_noise_fragment(token):
            return True
    overlap = len(template_cols & current_cols) + len(template_props & current_props)
    if overlap == 0:
        return True
    if len(current_cols) < 2:
        return True
    # Do not treat extra user-requested columns as drift. Only replace obviously generic/low-coverage schemas.
    min_overlap = max(1, min(2, len(template_cols) // 3 or 1))
    if overlap < min_overlap and len(current_cols) <= max(2, len(template_cols) // 3):
        return True
    return False
def _upgrade_schema_map_with_business_templates(schema_map: Dict[str, Any]) -> Dict[str, Any]:
    parser = SchemaParser()
    entity_keys = [str(k).lower() for k in (schema_map or {}).keys() if str(k).strip()]
    contextual = parser._contextual_templates(entity_keys) if entity_keys else {}
    upgraded: Dict[str, Any] = {}
    for entity, schema in (schema_map or {}).items():
        entity_low = str(entity or '').lower()
        template = contextual.get(entity_low) or parser.BUSINESS_DOMAIN_TEMPLATES.get(entity_low)
        if not template:
            upgraded[entity] = schema
            continue
        if schema is None or _schema_has_business_drift(schema, template):
            feature_kind = getattr(schema, 'feature_kind', None) or FEATURE_KIND_CRUD
            table_name = str(getattr(schema, 'table', '') or entity_low or _snake(entity))
            upgraded[entity] = schema_for(entity, _schema_field_specs_from_template(template), table=table_name, feature_kind=feature_kind)
        else:
            upgraded[entity] = schema
    return upgraded
def _schema_map_from_file_ops(file_ops: List[Dict[str, Any]], extra_requirements: str = "") -> Dict[str, Any]:
    source_ops = list(file_ops or [])
    extra_text = str(extra_requirements or '').strip()
    explicit_schema_map = extract_explicit_requirement_schemas(extra_text) if extra_text else {}
    if extra_text:
        source_ops = [{
            'path': 'requirements.txt',
            'purpose': 'user explicit schema requirements',
            'content': extra_text,
            'requirements_text': extra_text,
            'schema_text': extra_text,
        }] + source_ops
    inferred_entities = _infer_entities_from_ops(source_ops)
    entities: List[str] = []
    for entity in list(explicit_schema_map.keys()) + list(inferred_entities):
        token = str(entity or '').strip()
        if token and token not in entities:
            entities.append(token)
    schema_map: Dict[str, Any] = dict(explicit_schema_map)
    for entity in entities:
        scoped_ops = [item for item in source_ops if _op_matches_entity(item, entity)]
        try:
            inferred = infer_schema_from_file_ops(scoped_ops or source_ops, entity)
        except Exception:
            inferred = schema_for(entity)
        explicit = explicit_schema_map.get(entity)
        if explicit is not None and str(getattr(explicit, 'authority', '') or '').lower() == 'explicit':
            schema_map[entity] = explicit
            continue
        schema_map[entity] = inferred
    schema_map = _upgrade_schema_map_with_business_templates(schema_map)
    return _normalize_schema_tables(schema_map)


def _mysql_schema_sync_statements(schema: Any, existing_columns: Dict[str, Dict[str, Any]]) -> List[str]:
    table = str(getattr(schema, 'table', '') or '').strip()
    if not table:
        return []
    field_comments = {str(k or '').lower(): str(v or '').strip() for k, v in ((getattr(schema, 'field_comments', {}) or {}).items())}
    field_db_types = {str(k or '').lower(): str(v or '').strip() for k, v in ((getattr(schema, 'field_db_types', {}) or {}).items())}
    field_nullable = {str(k or '').lower(): bool(v) for k, v in ((getattr(schema, 'field_nullable', {}) or {}).items()) if v is not None}
    field_unique = {str(k or '').lower(): bool(v) for k, v in ((getattr(schema, 'field_unique', {}) or {}).items()) if v is not None}
    field_auto_increment = {str(k or '').lower(): bool(v) for k, v in ((getattr(schema, 'field_auto_increment', {}) or {}).items()) if v is not None}
    id_column = str(getattr(schema, 'id_column', '') or '').strip().lower()
    existing = {str(k or '').lower(): (v or {}) for k, v in (existing_columns or {}).items()}

    def _sql_type(prop: str, col: str, jt: str) -> str:
        explicit = field_db_types.get(col.lower())
        if explicit:
            return explicit
        try:
            from execution_core.builtin_crud import _ddl_default_sql_type  # type: ignore
            return str(_ddl_default_sql_type(prop, col, jt, schema) or 'VARCHAR(255)')
        except Exception:
            return 'VARCHAR(255)'

    def _comment(col: str) -> str:
        value = field_comments.get(col.lower(), '').strip()
        return value.replace("'", "''")

    def _definition(prop: str, col: str, jt: str) -> str:
        col_key = col.lower()
        parts = [f'`{col}`', _sql_type(prop, col, jt)]
        nullable = field_nullable.get(col_key, None)
        is_primary = col_key == id_column
        auto_increment = field_auto_increment.get(col_key, False)
        unique = field_unique.get(col_key, False)
        if auto_increment and 'AUTO_INCREMENT' not in parts[-1].upper():
            parts.append('AUTO_INCREMENT')
        if is_primary:
            parts.append('NOT NULL')
            parts.append('PRIMARY KEY')
        elif nullable is False:
            parts.append('NOT NULL')
        elif auto_increment:
            parts.append('NOT NULL')
        if unique and not is_primary:
            parts.append('UNIQUE')
        comment = _comment(col)
        if comment:
            parts.append(f"COMMENT '{comment}'")
        return ' '.join(parts)

    def _normalize_sql_type(value: str) -> str:
        return re.sub(r'\s+', '', str(value or '').strip().lower())

    statements: List[str] = []
    for prop, col, jt in (getattr(schema, 'fields', []) or []):
        col_key = str(col or '').strip().lower()
        if not col_key:
            continue
        desired_def = _definition(prop, col, jt)
        current = existing.get(col_key)
        if not current:
            statements.append(f'ALTER TABLE `{table}` ADD COLUMN {desired_def}')
            continue
        desired_type = _normalize_sql_type(_sql_type(prop, col, jt))
        current_type = _normalize_sql_type(current.get('column_type') or current.get('data_type') or '')
        desired_not_null = (' NOT NULL' in desired_def.upper())
        current_not_null = str(current.get('is_nullable') or '').strip().upper() == 'NO'
        desired_primary = (' PRIMARY KEY' in desired_def.upper())
        current_primary = str(current.get('column_key') or '').strip().upper() == 'PRI'
        desired_comment = _comment(col)
        current_comment = str(current.get('column_comment') or '').strip()
        desired_auto_increment = 'AUTO_INCREMENT' in desired_def.upper()
        current_auto_increment = 'AUTO_INCREMENT' in str(current.get('extra') or '').upper()
        desired_unique = (' UNIQUE' in desired_def.upper()) and not desired_primary
        current_unique = str(current.get('column_key') or '').strip().upper() == 'UNI'
        differs = any([
            desired_type != current_type,
            desired_not_null != current_not_null,
            desired_primary != current_primary,
            desired_comment != current_comment,
            desired_auto_increment != current_auto_increment,
            desired_unique != current_unique,
        ])
        if differs:
            statements.append(f'ALTER TABLE `{table}` MODIFY COLUMN {desired_def}')
    return statements


_INFRA_CONFIG_FILENAME_ALIASES = {
    'AuthenticInterceptor.java': 'AuthLoginInterceptor.java',
    'AuthInterceptor.java': 'AuthLoginInterceptor.java',
    'WebConfig.java': 'WebMvcConfig.java',
}
_INFRA_CONFIG_FILENAMES = {
    'AuthLoginInterceptor.java',
    'WebMvcConfig.java',
    'JwtTokenProvider.java',
    'LoginDatabaseInitializer.java',
    'MyBatisConfig.java',
}


def _looks_like_auth_artifact(item: Dict[str, Any]) -> bool:
    path = str((item or {}).get('path') or '').replace('\\', '/').lower()
    purpose = str((item or {}).get('purpose') or '').lower()
    content = str((item or {}).get('content') or '').lower()
    if not (path or purpose or content):
        return False
    filename = Path(path).name.lower() if path else ''
    auth_tokens = (
        'login', 'logout', 'signin', 'auth', 'authentication', 'session',
        'integratedauthservice', 'integrationguide', 'sso', '통합인증',
        'certlogin', 'certificate login', '공동인증서', 'jwtlogin', 'jwt token', '토큰 로그인',
    )
    if any(token in path for token in ('/login/', '/auth/')):
        return True
    if filename in {'logincontroller.java', 'loginservice.java', 'loginserviceimpl.java', 'loginvo.java', 'logindao.java', 'loginmapper.java', 'authlogininterceptor.java', 'authenticinterceptor.java', 'authinterceptor.java', 'webmvcconfig.java', 'jwttokenprovider.java', 'logindatabaseinitializer.java', 'webconfig.java'}:
        return True
    blob = "\n".join(part for part in (path, purpose, content) if part)
    return any(token in blob for token in auth_tokens)


def _auth_owner_entity(schema_map: Optional[Dict[str, Any]]) -> str:
    if not schema_map:
        return ''
    for entity in (schema_map or {}).keys():
        if str(entity or '').strip().lower() == 'login':
            return str(entity)
    for entity, schema in (schema_map or {}).items():
        if is_auth_kind(getattr(schema, 'feature_kind', None) or ''):
            return str(entity)
    return ''


def _canonicalize_auth_raw_path(raw_path: str, schema_map: Optional[Dict[str, Any]]) -> str:
    p = str(raw_path or '').replace('\\', '/').strip()
    if not p:
        return p
    owner = _auth_owner_entity(schema_map)
    if not owner:
        return p
    name = Path(p).name
    helper_map = {
        'LoginController.java': 'java/controller/LoginController.java',
        'LoginService.java': 'java/service/LoginService.java',
        'LoginServiceImpl.java': 'java/service/impl/LoginServiceImpl.java',
        'LoginVO.java': 'java/service/vo/LoginVO.java',
        'LoginDAO.java': 'java/service/impl/LoginDAO.java',
        'LoginMapper.java': 'java/service/mapper/LoginMapper.java',
        'LoginMapper.xml': 'mapper/login/LoginMapper.xml',
        'IntegratedAuthService.java': 'java/service/IntegratedAuthService.java',
        'IntegratedAuthServiceImpl.java': 'java/service/impl/IntegratedAuthServiceImpl.java',
        'CertLoginService.java': 'java/service/CertLoginService.java',
        'CertLoginServiceImpl.java': 'java/service/impl/CertLoginServiceImpl.java',
        'CertLoginController.java': 'java/controller/CertLoginController.java',
        'JwtLoginController.java': 'java/controller/JwtLoginController.java',
        'JwtTokenProvider.java': 'java/config/JwtTokenProvider.java',
        'WebMvcConfig.java': 'java/config/WebMvcConfig.java',
        'AuthLoginInterceptor.java': 'java/config/AuthLoginInterceptor.java',
        'AuthenticInterceptor.java': 'java/config/AuthLoginInterceptor.java',
        'AuthInterceptor.java': 'java/config/AuthLoginInterceptor.java',
        'LoginDatabaseInitializer.java': 'java/config/LoginDatabaseInitializer.java',
        'WebConfig.java': 'java/config/WebMvcConfig.java',
        'login.jsp': 'jsp/login/login.jsp',
        'main.jsp': 'jsp/login/main.jsp',
        'integrationGuide.jsp': 'jsp/login/integrationGuide.jsp',
        'certLogin.jsp': 'jsp/login/certLogin.jsp',
        'jwtLogin.jsp': 'jsp/login/jwtLogin.jsp',
    }
    if name == 'IntegratedAuthController.java':
        return ''
    if name in {'AuthenticInterceptorMapper.xml', 'AuthLoginInterceptorMapper.xml', 'AuthInterceptorMapper.xml'}:
        return ''
    if any(name == f'{stem}{suffix}' for stem in ('AuthenticInterceptor', 'AuthInterceptor', 'AuthLoginInterceptor', 'WebConfig', 'WebMvcConfig') for suffix in ('Service.java', 'ServiceImpl.java', 'Mapper.java', 'Mapper.xml', 'VO.java', 'Controller.java')):
        return ''
    if name in helper_map:
        return helper_map[name]
    return p




def _canonical_auth_target_map(base_package: str, schema_map: Optional[Dict[str, Any]]) -> Dict[str, str]:
    owner = _auth_owner_entity(schema_map) or 'Login'
    auth_module = _entity_var_from_name(owner)
    auth_module_base = f"{base_package}.{auth_module}" if auth_module and not (base_package or '').endswith(f'.{auth_module}') else (base_package or 'egovframework.app')
    logicals = {
        'LoginController.java': 'java/controller/LoginController.java',
        'LoginService.java': 'java/service/LoginService.java',
        'LoginServiceImpl.java': 'java/service/impl/LoginServiceImpl.java',
        'LoginVO.java': 'java/service/vo/LoginVO.java',
        'LoginDAO.java': 'java/service/impl/LoginDAO.java',
        'LoginMapper.java': 'java/service/mapper/LoginMapper.java',
        'LoginMapper.xml': 'mapper/login/LoginMapper.xml',
        'IntegratedAuthService.java': 'java/service/IntegratedAuthService.java',
        'IntegratedAuthServiceImpl.java': 'java/service/impl/IntegratedAuthServiceImpl.java',
        'CertLoginService.java': 'java/service/CertLoginService.java',
        'CertLoginServiceImpl.java': 'java/service/impl/CertLoginServiceImpl.java',
        'CertLoginController.java': 'java/controller/CertLoginController.java',
        'JwtLoginController.java': 'java/controller/JwtLoginController.java',
        'JwtTokenProvider.java': 'java/config/JwtTokenProvider.java',
        'WebMvcConfig.java': 'java/config/WebMvcConfig.java',
        'AuthLoginInterceptor.java': 'java/config/AuthLoginInterceptor.java',
        'AuthenticInterceptor.java': 'java/config/AuthLoginInterceptor.java',
        'AuthInterceptor.java': 'java/config/AuthLoginInterceptor.java',
        'LoginDatabaseInitializer.java': 'java/config/LoginDatabaseInitializer.java',
        'WebConfig.java': 'java/config/WebMvcConfig.java',
        'login.jsp': 'jsp/login/login.jsp',
        'main.jsp': 'jsp/login/main.jsp',
        'integrationGuide.jsp': 'jsp/login/integrationGuide.jsp',
        'certLogin.jsp': 'jsp/login/certLogin.jsp',
        'jwtLogin.jsp': 'jsp/login/jwtLogin.jsp',
    }
    return {name: _normalize_out_path(logical, base_package, owner, '', '') for name, logical in logicals.items()}


def _is_valid_auth_helper_content(rel_path: str, content: str) -> bool:
    rel = str(rel_path or '').replace('\\', '/').strip()
    name = Path(rel).name
    body = str(content or '')
    if not body.strip():
        return False
    if name.endswith('.jsp'):
        return True
    expected_type = Path(name).stem
    if name.endswith('.xml'):
        return '<mapper' in body.lower()
    m = re.search(r'public\s+(?:class|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)', body)
    if not m or m.group(1) != expected_type:
        return False
    lowered = body.lower()
    if '/user/' in rel or '.user.' in lowered:
        return False
    if name == 'CertLoginService.java' and 'authenticateCertificate(' not in body:
        return False
    if name == 'CertLoginServiceImpl.java' and 'implements CertLoginService' not in body:
        return False
    if name == 'IntegratedAuthService.java' and 'resolveIntegratedUser(' not in body:
        return False
    if name == 'IntegratedAuthServiceImpl.java' and 'implements IntegratedAuthService' not in body:
        return False
    if name == 'LoginService.java' and 'authenticate(' not in body:
        return False
    return True


def _purge_misplaced_auth_artifacts(project_root: Path, base_package: str, schema_map: Optional[Dict[str, Any]]) -> List[str]:
    removed: List[str] = []
    canonical = _canonical_auth_target_map(base_package, schema_map)
    if not canonical:
        return removed
    helper_names = set(canonical.keys())
    auth_owner = _auth_owner_entity(schema_map) or 'Login'
    owner_module = _entity_var_from_name(auth_owner).lower()
    base_pkg_parts = [part.lower() for part in str(base_package or '').split('.') if part]
    auth_like_modules = {'login', 'auth', 'signin', 'session', 'integratedauth', 'certlogin', 'jwtlogin'}
    auth_like_file_tokens = ('login', 'auth', 'jwt', 'cert', 'token', 'session', 'signin', 'logout', 'integrated')
    auth_like_suffixes = ('Controller.java', 'Service.java', 'ServiceImpl.java', 'DAO.java', 'Mapper.java', 'VO.java', 'Mapper.xml')

    for root in (project_root / 'src/main/java', project_root / 'src/main/webapp', project_root / 'src/main/resources'):
        if not root.exists():
            continue
        for path in list(root.rglob('*')):
            if not path.is_file():
                continue
            rel = str(path.relative_to(project_root)).replace('\\', '/')
            name = path.name
            if name in helper_names:
                wanted = canonical.get(name)
                if wanted and rel != wanted:
                    try:
                        path.unlink()
                        removed.append(rel)
                    except Exception:
                        pass
                continue

            rel_low = rel.lower()
            parts = rel_low.split('/')
            module = ''
            if 'java' in parts:
                try:
                    idx = parts.index('java')
                    pkg_start = idx + 1
                    module_idx = pkg_start + len(base_pkg_parts)
                    if len(parts) > module_idx:
                        module = parts[module_idx]
                except Exception:
                    module = ''
            elif 'views' in parts:
                try:
                    idx = parts.index('views')
                    if len(parts) > idx + 1:
                        module = parts[idx + 1]
                except Exception:
                    module = ''
            is_authish_name = name.endswith(auth_like_suffixes) and any(tok in name.lower() for tok in auth_like_file_tokens)
            is_authish_path = any(seg in auth_like_modules for seg in parts)
            if not is_authish_name and not is_authish_path:
                continue
            if module and module == owner_module:
                continue
            if module and module not in auth_like_modules:
                continue
            try:
                path.unlink()
                removed.append(rel)
            except Exception:
                pass
    return removed

def _augment_schema_map_with_auth(schema_map: Dict[str, Any], file_ops: List[Dict[str, Any]], cfg: ProjectConfig) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(schema_map or {})
    auth_requested = bool(getattr(cfg, 'login_feature_enabled', False)) or any(_looks_like_auth_artifact(item) for item in (file_ops or []))
    if not auth_requested:
        return out

    entity_name = next((entity for entity in out.keys() if str(entity or '').strip().lower() == 'login'), None) or 'Login'

    requirement_parts = []
    if getattr(cfg, 'extra_requirements', None):
        requirement_parts.append(str(cfg.extra_requirements or ''))
    for item in (file_ops or []):
        if not isinstance(item, dict):
            continue
        for key in ('purpose', 'content', 'description', 'summary'):
            value = item.get(key)
            if str(value or '').strip():
                requirement_parts.append(str(value))
    joined = "\n".join(requirement_parts).lower()
    unified_auth = bool(getattr(cfg, 'auth_unified_auth', False))
    cert_login = bool(getattr(cfg, 'auth_cert_login', False))
    jwt_login = bool(getattr(cfg, 'auth_jwt_login', False))
    if cert_login or jwt_login:
        unified_auth = unified_auth or cert_login or jwt_login

    existing = out.get(entity_name)
    shared_candidate = _find_shared_auth_schema_candidate(out) if _has_shared_auth_table_request(file_ops, cfg) or bool(getattr(cfg, 'extra_requirements', '').strip()) else None
    if shared_candidate is not None:
        out[entity_name] = _copy_schema_with_feature_kind(
            shared_candidate,
            entity_name=entity_name,
            feature_kind=FEATURE_KIND_AUTH,
            unified_auth=unified_auth,
            cert_login=cert_login,
            jwt_login=jwt_login,
        )
    elif existing is not None and is_auth_kind(getattr(existing, 'feature_kind', None) or ''):
        out[entity_name] = _copy_schema_with_feature_kind(
            existing,
            entity_name=entity_name,
            feature_kind=FEATURE_KIND_AUTH,
            unified_auth=unified_auth,
            cert_login=cert_login,
            jwt_login=jwt_login,
        )
    else:
        out[entity_name] = schema_for(
            entity_name,
            feature_kind=FEATURE_KIND_AUTH,
            unified_auth=unified_auth,
            cert_login=cert_login,
            jwt_login=jwt_login,
        )
    helper_entities = {'integratedauth', 'certlogin', 'jwtlogin'}
    for helper in [name for name in list(out.keys()) if str(name or '').strip().lower() in helper_entities]:
        if helper != entity_name:
            out.pop(helper, None)
    for name in list(out.keys()):
        low = str(name or '').strip().lower()
        if low == str(entity_name).strip().lower():
            continue
        schema = out.get(name)
        if schema is None or not is_auth_kind(getattr(schema, 'feature_kind', None) or ''):
            continue
        out[name] = schema_for(
            str(name),
            inferred_fields=list(getattr(schema, 'fields', []) or []),
            table=str(getattr(schema, 'table', '') or low or _snake(str(name))),
            feature_kind=FEATURE_KIND_CRUD,
        )
    return _normalize_schema_tables(out)
def _should_force_jsp_crud_schema(entity: str, rel_path: str, content: str) -> bool:
    entity_low = (entity or '').strip().lower()
    rel_low = (rel_path or '').replace('\\', '/').lower()
    body_low = (content or '').lower()
    if entity_low in {'login', 'auth', 'signin', 'logout', 'session'}:
        return False
    if rel_low.endswith('/login.jsp') or '/auth/' in rel_low or '/login/' in rel_low or rel_low.endswith('logincontroller.java') or rel_low.endswith('authcontroller.java'):
        return False
    schedule_markers = ('/calendar.do', 'calendar.jsp', 'calendarpage', 'calendar view', 'selecteddateschedules', 'calendarcells', '일정', '캘린더', '달력')
    if entity_low in {'schedule', 'reservation', 'event'} or '/schedule/' in rel_low or any(tok in body_low for tok in schedule_markers):
        return False
    explicit_auth = any(tok in body_low for tok in ('/login.do', '/process.do', 'authenticate(', 'loginerror', 'session.setattribute("login'))
    explicit_crud = any(tok in body_low for tok in ('/list.do', '/detail.do', '/form.do', '/save.do', '/delete.do', 'selectlist', 'selectdetail', 'insert', 'update', 'delete'))
    if explicit_crud:
        return True
    if explicit_auth and rel_low.endswith(('controller.java', 'service.java', 'serviceimpl.java', 'mapper.java', 'mapper.xml', 'vo.java')):
        return True
    if explicit_auth and not explicit_crud:
        return False
    return True
def _module_base_package(base_package: str, rel_path: str, content: str = '', extra_text: str = '') -> str:
    rel = (rel_path or '').replace('\\', '/')
    module_seg = _infer_module_segment(base_package, rel, content, extra_text)
    if module_seg:
        return f"{base_package}.{module_seg}"
    entity = _entity_from_filename(Path(rel).name)
    if entity:
        ev = _entity_var_from_name(entity)
        if base_package.endswith("." + ev) or base_package == ev:
            return base_package
        return f"{base_package}.{ev}"
    return base_package
def _module_base_from_java_package(pkg: str) -> str:
    for suffix in ('.service.impl', '.service.mapper', '.service.vo', '.service', '.web', '.config'):
        if pkg.endswith(suffix):
            return pkg[:-len(suffix)]
    return pkg
def _expected_java_package(rel_path: str, base_package: str) -> str:
    rel = (rel_path or '').replace('\\', '/')
    if 'src/main/java/' not in rel:
        return base_package
    tail = rel.split('src/main/java/', 1)[1]
    parts = [part for part in tail.split('/') if part]
    if len(parts) <= 1:
        return base_package
    return '.'.join(parts[:-1])
def _enforce_java_package_and_imports(rel_path: str, content: str, base_package: str) -> str:
    body = content or ''
    expected_pkg = _expected_java_package(rel_path, base_package)
    if expected_pkg:
        if re.search(r'^\s*package\s+[A-Za-z0-9_\.]+\s*;', body, flags=re.MULTILINE):
            body = re.sub(r'^\s*package\s+[A-Za-z0-9_\.]+\s*;', f'package {expected_pkg};', body, count=1, flags=re.MULTILINE)
        else:
            body = f'package {expected_pkg};\n\n' + body.lstrip()
    module_base = _module_base_from_java_package(expected_pkg)
    def _rewrite_import(match: re.Match) -> str:
        layer = match.group(1)
        name = match.group(2)
        if layer == 'config':
            return f'import {base_package}.config.{name};'
        return f'import {module_base}.{layer}.{name};'
    body = re.sub(
        r'import\s+[A-Za-z_][\w\.]*\.(service(?:\.impl|\.mapper|\.vo)?|web|config)\.([A-Za-z_][\w]*)\s*;',
        _rewrite_import,
        body,
    )
    return body
def _find_schema_column(schema: Any, *candidates: str) -> str:
    candidate_set = {str(name or '').strip().lower() for name in candidates if str(name or '').strip()}
    if not candidate_set:
        return ''
    for _prop, col, _jt in (getattr(schema, 'fields', []) or []):
        col_name = str(col or '').strip()
        if col_name.lower() in candidate_set:
            return col_name
    return ''


def _set_simple_prop(text: str, key: str, value: str) -> str:
    body = text or ''
    pattern = rf'(?m)^\s*{re.escape(key)}\s*=.*(?:\n|$)'
    line = f"{key}={value}\n"
    if re.search(pattern, body):
        return re.sub(pattern, line, body, count=1)
    if body and not body.endswith('\n'):
        body += '\n'
    return body + line


def _write_auth_sql_file(project_root: Path, filename: str, sql: str) -> Optional[Path]:
    body = str(sql or '').strip()
    if not body:
        return None
    statements = _normalize_recreate_sql_statements(_split_sql_statements(body) or [body if body.endswith(';') else body + ';'])
    rendered = '\n\n'.join(statements).strip()
    res_dir = project_root / 'src/main/resources'
    res_dir.mkdir(parents=True, exist_ok=True)
    primary = res_dir / filename
    primary.write_text(rendered + '\n', encoding='utf-8')
    variant = res_dir / 'db' / filename
    variant.parent.mkdir(parents=True, exist_ok=True)
    variant.write_text(rendered + '\n', encoding='utf-8')
    return primary


def _append_sql_file(project_root: Path, filename: str, sql: str) -> Optional[Path]:
    body = str(sql or '').strip()
    if not body:
        return None
    res_dir = project_root / 'src/main/resources'
    res_dir.mkdir(parents=True, exist_ok=True)
    path = res_dir / filename
    existing = path.read_text(encoding='utf-8') if path.exists() else ''

    existing_statements = _split_sql_statements(existing)
    new_statements = _split_sql_statements(body)
    if not new_statements:
        new_statements = [body if body.endswith(';') else body + ';']

    merged_statements = _merge_sql_statements(new_statements, existing_statements)
    merged_statements = _normalize_recreate_sql_statements(merged_statements)
    path.write_text('\n\n'.join(merged_statements).strip() + '\n', encoding='utf-8')
    return path




def _write_auth_database_initializer(project_root: Path, base_package: str) -> Optional[Path]:
    pkg = f"{base_package}.config"
    src_dir = project_root / 'src/main/java' / Path(*pkg.split('.'))
    src_dir.mkdir(parents=True, exist_ok=True)
    path = src_dir / 'LoginDatabaseInitializer.java'
    lines = [
        'package __PKG__;',
        '',
        'import java.io.IOException;',
        'import java.nio.charset.StandardCharsets;',
        'import java.sql.Connection;',
        'import java.sql.DatabaseMetaData;',
        'import java.sql.ResultSet;',
        'import java.sql.SQLException;',
        'import java.sql.Statement;',
        'import java.util.ArrayList;',
        'import java.util.List;',
        'import java.util.Locale;',
        '',
        'import javax.sql.DataSource;',
        '',
        'import org.springframework.boot.ApplicationRunner;',
        'import org.springframework.context.annotation.Bean;',
        'import org.springframework.context.annotation.Configuration;',
        'import org.springframework.core.io.ClassPathResource;',
        'import org.springframework.core.io.Resource;',
        'import org.springframework.util.StreamUtils;',
        '',
        '@Configuration',
        'public class LoginDatabaseInitializer {',
        '    private static final char CHAR_NUL = (char) 0;',
        '    private static final char CHAR_NEWLINE = (char) 10;',
        '    private static final char CHAR_SINGLE_QUOTE = (char) 39;',
        '    private static final char CHAR_DOUBLE_QUOTE = (char) 34;',
        '    private static final char CHAR_BACKTICK = (char) 96;',
        '    private static final char CHAR_OPEN_PAREN = (char) 40;',
        '    private static final char CHAR_COMMA = (char) 44;',
        '    private static final char CHAR_SEMICOLON = (char) 59;',
        '    private static final char CHAR_DASH = (char) 45;',
        '    private static final char CHAR_SLASH = (char) 47;',
        '    private static final char CHAR_ASTERISK = (char) 42;',
        '',
        '    @Bean',
        '    public ApplicationRunner loginDatabaseInitializerRunner(DataSource dataSource) {',
        '        return args -> {',
        '            List<Resource> resources = new ArrayList<>();',
        '            for (String resourceName : new String[] {"schema.sql", "data.sql", "login-schema.sql", "login-data.sql"}) {',
        '                ClassPathResource resource = new ClassPathResource(resourceName);',
        '                if (resource.exists()) {',
        '                    resources.add(resource);',
        '                }',
        '            }',
        '            if (resources.isEmpty()) {',
        '                return;',
        '            }',
        '            try (Connection connection = dataSource.getConnection(); Statement statement = connection.createStatement()) {',
        '                for (Resource resource : resources) {',
        '                    executeResource(connection, statement, resource);',
        '                }',
        '            }',
        '        };',
        '    }',
        '',
        '    private void executeResource(Connection connection, Statement statement, Resource resource) throws IOException, SQLException {',
        '        String sql = StreamUtils.copyToString(resource.getInputStream(), StandardCharsets.UTF_8);',
        '        for (String raw : splitStatements(sql)) {',
        '            String stmt = raw == null ? "" : raw.trim();',
        '            if (stmt.isEmpty()) {',
        '                continue;',
        '            }',
        '            if (shouldSkipStatement(connection, stmt)) {',
        '                continue;',
        '            }',
        '            statement.execute(stmt);',
        '        }',
        '    }',
        '',
        '    private boolean shouldSkipStatement(Connection connection, String statement) throws SQLException {',
        '        AlterAddColumnInfo info = parseAlterAddColumn(statement);',
        '        if (info == null) {',
        '            return false;',
        '        }',
        '        return columnExists(connection, info.tableName, info.columnName);',
        '    }',
        '',
        '    private AlterAddColumnInfo parseAlterAddColumn(String statement) {',
        '        if (statement == null) {',
        '            return null;',
        '        }',
        '        String compact = statement.trim();',
        '        if (compact.isEmpty()) {',
        '            return null;',
        '        }',
        '        String upper = compact.toUpperCase(Locale.ROOT);',
        '        if (!upper.startsWith("ALTER TABLE ") || upper.indexOf(" ADD ") < 0) {',
        '            return null;',
        '        }',
        '        String afterAlter = compact.substring("ALTER TABLE ".length()).trim();',
        '        int addIndex = indexOfKeyword(afterAlter, "ADD");',
        '        if (addIndex < 0) {',
        '            return null;',
        '        }',
        '        String tablePart = afterAlter.substring(0, addIndex).trim();',
        '        String addPart = afterAlter.substring(addIndex + 3).trim();',
        '        if (addPart.toUpperCase(Locale.ROOT).startsWith("COLUMN ")) {',
        '            addPart = addPart.substring(7).trim();',
        '        }',
        '        String tableName = firstIdentifier(tablePart);',
        '        String columnName = firstIdentifier(addPart);',
        '        if (tableName.isEmpty() || columnName.isEmpty()) {',
        '            return null;',
        '        }',
        '        return new AlterAddColumnInfo(tableName, columnName);',
        '    }',
        '',
        '    private int indexOfKeyword(String text, String keyword) {',
        '        String upper = text.toUpperCase(Locale.ROOT);',
        '        String token = " " + keyword.toUpperCase(Locale.ROOT) + " ";',
        '        int idx = upper.indexOf(token);',
        '        if (idx >= 0) {',
        '            return idx + 1;',
        '        }',
        '        if (upper.startsWith(keyword.toUpperCase(Locale.ROOT) + " ")) {',
        '            return 0;',
        '        }',
        '        return -1;',
        '    }',
        '',
        '    private String firstIdentifier(String text) {',
        '        if (text == null) {',
        '            return "";',
        '        }',
        '        String trimmed = text.trim();',
        '        if (trimmed.isEmpty()) {',
        '            return "";',
        '        }',
        '        StringBuilder builder = new StringBuilder();',
        '        int quote = 0;',
        '        for (int i = 0; i < trimmed.length(); i++) {',
        '            char ch = trimmed.charAt(i);',
        '            if (quote != 0) {',
        '                if (ch == quote) {',
        '                    break;',
        '                }',
        '                builder.append(ch);',
        '                continue;',
        '            }',
        '            if (ch == CHAR_BACKTICK || ch == CHAR_DOUBLE_QUOTE) {',
        '                quote = ch;',
        '                continue;',
        '            }',
        '            if (Character.isWhitespace(ch) || ch == CHAR_OPEN_PAREN || ch == CHAR_COMMA || ch == CHAR_SEMICOLON) {',
        '                break;',
        '            }',
        '            builder.append(ch);',
        '        }',
        '        return builder.toString().trim();',
        '    }',
        '',
        '    private boolean columnExists(Connection connection, String tableName, String columnName) throws SQLException {',
        '        DatabaseMetaData metaData = connection.getMetaData();',
        '        String normalizedTable = normalizeLookupName(tableName, metaData.storesLowerCaseIdentifiers(), metaData.storesUpperCaseIdentifiers());',
        '        String normalizedColumn = normalizeLookupName(columnName, metaData.storesLowerCaseIdentifiers(), metaData.storesUpperCaseIdentifiers());',
        '        String schema = connection.getSchema();',
        '        String catalog = connection.getCatalog();',
        '        for (String schemaCandidate : schemaCandidates(schema, null)) {',
        '            if (matchesColumn(metaData, catalog, schemaCandidate, normalizedTable, normalizedColumn)) {',
        '                return true;',
        '            }',
        '            if (matchesColumn(metaData, null, schemaCandidate, normalizedTable, normalizedColumn)) {',
        '                return true;',
        '            }',
        '        }',
        '        for (String catalogCandidate : schemaCandidates(catalog, null)) {',
        '            if (matchesColumn(metaData, catalogCandidate, schema, normalizedTable, normalizedColumn)) {',
        '                return true;',
        '            }',
        '            if (matchesColumn(metaData, catalogCandidate, null, normalizedTable, normalizedColumn)) {',
        '                return true;',
        '            }',
        '        }',
        '        return matchesColumn(metaData, null, null, normalizedTable, normalizedColumn);',
        '    }',
        '',
        '    private boolean matchesColumn(DatabaseMetaData metaData, String catalog, String schema, String table, String column) throws SQLException {',
        '        try (ResultSet rs = metaData.getColumns(catalog, schema, table, column)) {',
        '            return rs.next();',
        '        }',
        '    }',
        '',
        '    private List<String> schemaCandidates(String primary, String secondary) {',
        '        List<String> values = new ArrayList<>();',
        '        if (primary != null && !primary.isBlank()) {',
        '            values.add(primary);',
        '        }',
        '        if (secondary != null && !secondary.isBlank() && !values.contains(secondary)) {',
        '            values.add(secondary);',
        '        }',
        '        values.add(null);',
        '        return values;',
        '    }',
        '',
        '    private String normalizeLookupName(String value, boolean lower, boolean upper) {',
        '        if (value == null) {',
        '            return null;',
        '        }',
        '        String trimmed = stripIdentifierQuotes(value);',
        '        if (trimmed.isEmpty()) {',
        '            return trimmed;',
        '        }',
        '        if (lower) {',
        '            return trimmed.toLowerCase(Locale.ROOT);',
        '        }',
        '        if (upper) {',
        '            return trimmed.toUpperCase(Locale.ROOT);',
        '        }',
        '        return trimmed;',
        '    }',
        '',
        '    private String stripIdentifierQuotes(String value) {',
        '        if (value == null) {',
        '            return "";',
        '        }',
        '        String trimmed = value.trim();',
        '        if (trimmed.isEmpty()) {',
        '            return trimmed;',
        '        }',
        '        return trimmed.replace(String.valueOf(CHAR_BACKTICK), "").replace(String.valueOf(CHAR_DOUBLE_QUOTE), "").trim();',
        '    }',
        '',
        '    private List<String> splitStatements(String sql) {',
        '        List<String> statements = new ArrayList<>();',
        '        if (sql == null || sql.isBlank()) {',
        '            return statements;',
        '        }',
        '        StringBuilder current = new StringBuilder();',
        '        boolean singleQuoted = false;',
        '        boolean doubleQuoted = false;',
        '        boolean lineComment = false;',
        '        boolean blockComment = false;',
        '        for (int i = 0; i < sql.length(); i++) {',
        '            char ch = sql.charAt(i);',
        '            int next = i + 1 < sql.length() ? sql.charAt(i + 1) : 0;',
        '            if (lineComment) {',
        '                if (ch == CHAR_NEWLINE) {',
        '                    lineComment = false;',
        '                }',
        '                continue;',
        '            }',
        '            if (blockComment) {',
        '                if (ch == CHAR_ASTERISK && next == CHAR_SLASH) {',
        '                    blockComment = false;',
        '                    i++;',
        '                }',
        '                continue;',
        '            }',
        '            if (!singleQuoted && !doubleQuoted) {',
        '                if (ch == CHAR_DASH && next == CHAR_DASH) {',
        '                    lineComment = true;',
        '                    i++;',
        '                    continue;',
        '                }',
        '                if (ch == CHAR_SLASH && next == CHAR_ASTERISK) {',
        '                    blockComment = true;',
        '                    i++;',
        '                    continue;',
        '                }',
        '            }',
        '            if (ch == CHAR_SINGLE_QUOTE && !doubleQuoted) {',
        '                singleQuoted = !singleQuoted;',
        '                current.append(ch);',
        '                continue;',
        '            }',
        '            if (ch == CHAR_DOUBLE_QUOTE && !singleQuoted) {',
        '                doubleQuoted = !doubleQuoted;',
        '                current.append(ch);',
        '                continue;',
        '            }',
        '            if (ch == CHAR_SEMICOLON && !singleQuoted && !doubleQuoted) {',
        '                String stmt = current.toString().trim();',
        '                if (!stmt.isEmpty()) {',
        '                    statements.add(stmt);',
        '                }',
        '                current.setLength(0);',
        '                continue;',
        '            }',
        '            current.append(ch);',
        '        }',
        '        String tail = current.toString().trim();',
        '        if (!tail.isEmpty()) {',
        '            statements.add(tail);',
        '        }',
        '        return statements;',
        '    }',
        '',
        '    private static final class AlterAddColumnInfo {',
        '        private final String tableName;',
        '        private final String columnName;',
        '',
        '        private AlterAddColumnInfo(String tableName, String columnName) {',
        '            this.tableName = tableName;',
        '            this.columnName = columnName;',
        '        }',
        '    }',
        '}',
    ]
    content = "\n".join(lines).replace("__PKG__", pkg) + "\n"
    path.write_text(content, encoding='utf-8')
    return path
def _patch_auth_sql_init_properties(project_root: Path) -> Optional[Path]:
    props = project_root / 'src/main/resources/application.properties'
    body = props.read_text(encoding='utf-8') if props.exists() else ''
    body = _set_simple_prop(body, 'spring.sql.init.mode', 'never')
    body = _set_simple_prop(body, 'spring.sql.init.encoding', 'UTF-8')
    body = _set_simple_prop(body, 'spring.sql.init.schema-locations', 'optional:classpath:schema.sql,optional:classpath:login-schema.sql')
    body = _set_simple_prop(body, 'spring.sql.init.data-locations', 'optional:classpath:data.sql,optional:classpath:login-data.sql')
    body = _set_simple_prop(body, 'spring.sql.init.continue-on-error', 'false')
    props.parent.mkdir(parents=True, exist_ok=True)
    props.write_text(body, encoding='utf-8')
    return props


def _first_auth_schema(schema_map: Dict[str, Any]) -> Optional[Any]:
    for _entity, schema in (schema_map or {}).items():
        if schema is not None and is_auth_kind(getattr(schema, 'feature_kind', None) or ''):
            return schema
    return None


def _write_auth_sql_artifacts(project_root: Path, schema_map: Dict[str, Any], base_package: str = '') -> Dict[str, str]:
    patched: Dict[str, str] = {}
    schema = _first_auth_schema(schema_map)
    if schema is None:
        return patched
    shared_table = any(
        other is not None and other is not schema and str(getattr(other, 'table', '') or '').strip().lower() == str(getattr(schema, 'table', '') or '').strip().lower()
        for other in (schema_map or {}).values()
    )
    if shared_table:
        return patched
    login_ddl = ddl(schema)
    schema_path = _write_auth_sql_file(project_root, 'login-schema.sql', login_ddl)
    if schema_path is not None:
        patched['login-schema.sql'] = str(schema_path)
    canonical_schema = _append_sql_file(project_root, 'schema.sql', login_ddl)
    if canonical_schema is not None:
        patched['schema.sql.auth'] = str(canonical_schema)
    seed_sql = _auth_seed_sql(schema)
    data_path = _write_auth_sql_file(project_root, 'login-data.sql', seed_sql)
    if data_path is not None:
        patched['login-data.sql'] = str(data_path)
    props_path = _patch_auth_sql_init_properties(project_root)
    if props_path is not None:
        patched['auth-sql-init.properties'] = str(props_path)
    if base_package:
        init_path = _write_auth_database_initializer(project_root, base_package)
        if init_path is not None:
            patched['LoginDatabaseInitializer'] = str(init_path)
    return patched


def _auth_seed_normalize_token(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '', str(value or '').strip().lower())


def _is_explicit_auth_identifier(field: tuple[str, str, str] | None) -> bool:
    if not field:
        return False
    prop = _auth_seed_normalize_token(str(field[0] or ''))
    col = _auth_seed_normalize_token(str(field[1] or ''))
    return prop in LOGIN_FIELD_CANDIDATES or col in LOGIN_FIELD_CANDIDATES


_AUTH_TABLE_HINTS = (
    'login', 'user', 'account', 'member', 'auth', 'signin', 'signup', 'credential', 'session', 'cert', 'jwt',
)
_BLOCKED_AUTH_SEED_TABLE_HINTS = (
    'schedule', 'calendar', 'reservation', 'booking', 'meeting', 'board', 'notice', 'post', 'article', 'content',
)


def _looks_auth_seed_target(schema: Any, auth_id: tuple[str, str, str] | None = None) -> bool:
    table = str(getattr(schema, 'table', '') or '').strip().lower()
    entity = str(getattr(schema, 'entity', '') or '').strip().lower()
    joined = f'{table} {entity}'.strip()
    if any(token in joined for token in _BLOCKED_AUTH_SEED_TABLE_HINTS):
        return False
    if any(token in joined for token in _AUTH_TABLE_HINTS):
        return True
    if _is_explicit_auth_identifier(auth_id):
        return True
    return False


def _auth_seed_sql(schema: Any) -> str:
    if not is_auth_kind(getattr(schema, 'feature_kind', None) or ''):
        return ''
    fields = list(getattr(schema, 'fields', []) or [])
    id_prop = str(getattr(schema, 'id_prop', '') or '')
    id_col = str(getattr(schema, 'id_column', '') or '')
    auth_id, auth_pw, normalized = choose_auth_fields(fields, id_prop, id_col)
    table = str(getattr(schema, 'table', '') or '').strip()
    if not table or not auth_id[1] or not auth_pw[1]:
        return ''
    if not _looks_auth_seed_target(schema, auth_id):
        return ''
    columns: List[str] = []
    values: List[str] = []

    def add_value(column: str, value_sql: str) -> None:
        if not column or column in columns:
            return
        columns.append(column)
        values.append(value_sql)

    # Prefer an explicit login column when the primary key is a separate required column.
    preferred_login_col = _find_schema_column(schema, 'login_id', 'loginid', 'loginId')
    auth_login_col = preferred_login_col or auth_id[1]

    # When the schema separates the login field (e.g. login_id) from the primary key
    # (e.g. user_id), the bootstrap seed must populate both. Otherwise startup can fail
    # with MySQL errors like: Field 'user_id' doesn't have a default value.
    if id_col and id_col != auth_login_col:
        add_value(id_col, "'admin'")

    add_value(auth_login_col, "'admin'")
    add_value(auth_pw[1], "'admin1234'")

    name_col = _find_schema_column(schema, 'user_name', 'member_name', 'login_name', 'name')
    email_col = _find_schema_column(schema, 'email')
    use_col = _find_schema_column(schema, 'use_yn')
    status_col = _find_schema_column(schema, 'status_cd', 'status_code', 'status')
    reg_col = _find_schema_column(schema, 'reg_dt', 'created_at')
    upd_col = _find_schema_column(schema, 'upd_dt', 'updated_at')

    add_value(name_col, "'관리자'")
    add_value(email_col, "'admin@local'")
    add_value(use_col, "'Y'")
    add_value(status_col, "'ACTIVE'")
    add_value(reg_col, 'CURRENT_TIMESTAMP')
    add_value(upd_col, 'CURRENT_TIMESTAMP')

    if not columns:
        return ''
    return (
        f"INSERT INTO {table} ({', '.join(columns)}) "
        f"SELECT {', '.join(values)} "
        f"WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE {auth_login_col} = 'admin');"
    )


def _write_schema_sql_from_schemas(project_root: Path, schema_map: Dict[str, Any]) -> Optional[Path]:
    ordered: List[Any] = []
    for _key, schema in (schema_map or {}).items():
        if schema is None:
            continue
        if not any(getattr(schema, 'entity', None) == getattr(existing, 'entity', None) for existing in ordered):
            ordered.append(schema)
    preferred: List[str] = []
    for schema in ordered:
        preferred.append(ddl(schema))
        seed_sql = _auth_seed_sql(schema)
        if seed_sql:
            preferred.append(seed_sql)
    existing = _load_sql_statements_from_project(project_root, 'schema.sql')
    generic_placeholder_tables = {'table', 'item', 'data', 'entity'}
    filtered_existing: List[str] = []
    for stmt in existing:
        tables = set(_expected_table_names_from_sql([stmt]))
        if tables and tables.issubset(generic_placeholder_tables):
            continue
        filtered_existing.append(stmt)
    merged = _merge_sql_statements(preferred, filtered_existing)
    merged = _normalize_recreate_sql_statements(merged)
    if not merged:
        return None
    return write_schema_sql(project_root, '\n\n'.join(merged))
def _canonical_crud_rel_path(base_package: str, logical_path: str, source_path: str = "", source_content: str = "", extra_text: str = "") -> str:
    module_base = _module_base_package(base_package, source_path or logical_path, source_content, extra_text)
    pkg_path = (module_base or "").replace(".", "/")
    lp = (logical_path or "").replace('\\', '/')
    if lp.startswith("jsp/"):
        return f"src/main/webapp/WEB-INF/views/{lp.replace('jsp/', '', 1)}"
    if lp.startswith("java/controller/"):
        return f"src/main/java/{pkg_path}/web/{Path(lp).name}"
    if lp.startswith("java/service/impl/"):
        return f"src/main/java/{pkg_path}/service/impl/{Path(lp).name}"
    if lp.startswith("java/service/mapper/"):
        return f"src/main/java/{pkg_path}/service/mapper/{Path(lp).name}"
    if lp.startswith("java/service/vo/"):
        return f"src/main/java/{pkg_path}/service/vo/{Path(lp).name}"
    if lp.startswith("java/service/"):
        return f"src/main/java/{pkg_path}/service/{Path(lp).name}"
    if lp.startswith("java/config/"):
        root_pkg = (base_package or "").replace(".", "/")
        return f"src/main/java/{root_pkg}/config/{Path(lp).name}"
    if lp.startswith("mapper/"):
        tail = lp.replace("mapper/", "", 1)
        return f"src/main/resources/egovframework/mapper/{tail}"
    return lp
def _normalize_out_path(path: str, base_package: str = "", preferred_entity: str = "", content: str = "", extra_text: str = "") -> str:
    p = (path or "").strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    if not p:
        return ""
    p = p.replace("/WEB-INF/jsp/", "/WEB-INF/views/")
    p = p.replace("/WEB-INF/jsp", "/WEB-INF/views")
    filename = p.split("/")[-1]
    if filename in _INFRA_CONFIG_FILENAME_ALIASES:
        canonical_name = _INFRA_CONFIG_FILENAME_ALIASES[filename]
        if p.startswith('src/main/java/') or p.startswith('java/') or '/' not in p:
            p = f'java/config/{canonical_name}'
        elif p.endswith('/' + filename):
            p = p[:-len(filename)] + canonical_name
        else:
            p = canonical_name
        filename = canonical_name
    elif filename in _INFRA_CONFIG_FILENAMES and (p.startswith('src/main/java/') or p.startswith('java/') or '/' not in p):
        p = f'java/config/{filename}'
    preferred_entity = _strip_logical_tb_prefix(preferred_entity) or preferred_entity
    rewritten_filename = _rewrite_filename_to_preferred_entity(filename, preferred_entity)
    if rewritten_filename != filename:
        p = f"{p.rsplit('/', 1)[0]}/{rewritten_filename}" if '/' in p else rewritten_filename
        filename = rewritten_filename
    root_pkg = (base_package or 'egovframework.app').replace('.', '/')
    preferred_module = _entity_var_from_name(preferred_entity) if preferred_entity else ''
    inferred_module = _infer_module_segment(base_package or 'egovframework.app', p, content, extra_text)
    module_seg = preferred_module or inferred_module
    if filename == 'EgovBootApplication.java' and base_package:
        return f"src/main/java/{root_pkg}/{filename}"
    if p.startswith("java/") and base_package:
        if p.startswith("java/config/"):
            return f"src/main/java/{root_pkg}/config/{filename}"
        if p.startswith("java/controller/"):
            pkg = f"{root_pkg}/{module_seg}/web".strip('/') if module_seg else f"{root_pkg}/web"
            return f"src/main/java/{pkg}/{filename}"
        if p.startswith("java/service/impl/"):
            pkg = f"{root_pkg}/{module_seg}/service/impl".strip('/') if module_seg else f"{root_pkg}/service/impl"
            return f"src/main/java/{pkg}/{filename}"
        if p.startswith("java/service/mapper/"):
            pkg = f"{root_pkg}/{module_seg}/service/mapper".strip('/') if module_seg else f"{root_pkg}/service/mapper"
            return f"src/main/java/{pkg}/{filename}"
        if p.startswith("java/service/vo/"):
            pkg = f"{root_pkg}/{module_seg}/service/vo".strip('/') if module_seg else f"{root_pkg}/service/vo"
            return f"src/main/java/{pkg}/{filename}"
        if p.startswith("java/service/"):
            pkg = f"{root_pkg}/{module_seg}/service".strip('/') if module_seg else f"{root_pkg}/service"
            return f"src/main/java/{pkg}/{filename}"
    if p.startswith("mapper/"):
        return f"src/main/resources/egovframework/{p}"
    if p.startswith("jsp/"):
        logical = _canonical_crud_logical_path(filename)
        if logical.startswith("jsp/"):
            return f"src/main/webapp/WEB-INF/views/{logical[len('jsp/') :]}"
        tail = p[len('jsp/') :]
        folder, _, name = tail.rpartition('/')
        logical_entity = _strip_logical_tb_prefix(folder.split('/')[-1]) if folder else ''
        logical_name = _strip_logical_tb_prefix(Path(name).stem) or Path(name).stem
        if logical_entity and name.lower().endswith('.jsp'):
            suffix = name[len(Path(name).stem):]
            lowered = logical_entity[:1].lower() + logical_entity[1:] if logical_entity else logical_entity
            return f"src/main/webapp/WEB-INF/views/{lowered}/{lowered}{suffix}"
        return f"src/main/webapp/WEB-INF/views/{tail}"
    if p == "index.jsp":
        return "src/main/webapp/index.jsp"
    logical = _canonical_crud_logical_path(filename)
    if logical and base_package:
        return _canonical_crud_rel_path(base_package, logical, source_path=p, source_content=content, extra_text=extra_text)
    if p.startswith("src/main/java/"):
        rest = p.split("src/main/java/", 1)[1]
        if "/" in rest:
            pkg_part, name = rest.rsplit("/", 1)
        else:
            pkg_part, name = "", rest
        if pkg_part and "/" not in pkg_part and "." in pkg_part:
            pkg_part = pkg_part.replace(".", "/")
        module_seg = _infer_module_segment(base_package or 'egovframework.app', p, content, extra_text)
        pkg_base = f"{root_pkg}/{module_seg}".strip('/') if module_seg else root_pkg
        if name.endswith("Controller.java"):
            pkg = f"{pkg_base}/web".strip('/')
        elif name.endswith("ServiceImpl.java"):
            pkg = f"{pkg_base}/service/impl".strip('/')
        elif name.endswith("Service.java"):
            pkg = f"{pkg_base}/service".strip('/')
        elif name.endswith("Mapper.java"):
            pkg = f"{pkg_base}/service/mapper".strip('/')
        elif name.endswith("VO.java"):
            pkg = f"{pkg_base}/service/vo".strip('/')
        elif name == "MyBatisConfig.java":
            pkg = f"{root_pkg}/config".strip('/')
        else:
            pkg = pkg_base
        return f"src/main/java/{pkg}/{name}" if pkg else f"src/main/java/{name}"
    if p.startswith("src/main/resources/") and (filename.endswith("Mapper.xml") or "_SQL" in filename) and base_package:
        logical = _canonical_crud_logical_path(filename)
        if logical:
            return _canonical_crud_rel_path(base_package, logical, source_path=p, source_content=content, extra_text=extra_text)
    return p
def _ensure_core_taglib(content: str) -> str:
    body = content or ""
    if 'uri="http://java.sun.com/jsp/jstl/core"' in body or "uri='http://java.sun.com/jsp/jstl/core'" in body:
        return body
    lines = body.splitlines()
    insert_at = 1 if lines and lines[0].lstrip().startswith('<%@ page') else 0
    lines.insert(insert_at, '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>')
    return "\n".join(lines)
def _rewrite_direct_jsp_links(content: str, schema: Optional[Any]) -> str:
    body = content or ""
    mapping: Dict[str, str] = {}
    if schema is not None:
        mapping.update({
            'list': schema.routes.get('list', ''),
            'detail': schema.routes.get('detail', ''),
            'form': schema.routes.get('form', ''),
            'save': schema.routes.get('save', ''),
            'delete': schema.routes.get('delete', ''),
            schema.views.get('list', '').lower(): schema.routes.get('list', ''),
            schema.views.get('detail', '').lower(): schema.routes.get('detail', ''),
            schema.views.get('form', '').lower(): schema.routes.get('form', ''),
        })
    attr_pat = re.compile(r"(?P<attr>href|action)\s*=\s*(?P<q>[\"'])(?P<target>[^\"']+?\.jsp(?:\?[^\"']*)?)(?P=q)", re.IGNORECASE)
    def _replace(match: re.Match) -> str:
        attr = match.group('attr')
        quote = match.group('q')
        target = match.group('target').strip()
        if '<c:url' in target or '${' in target:
            return match.group(0)
        clean_target = target.split('#', 1)[0]
        path_part, _, query = clean_target.partition('?')
        base_name = Path(path_part).stem
        low_name = base_name.lower()
        route = mapping.get(low_name, '')
        if not route:
            route = f"/view/{base_name}.do"
        value = f"<c:url value='{route}'/>"
        if query:
            value += '?' + query
        return f"{attr}={quote}{value}{quote}"
    rewritten = attr_pat.sub(_replace, body)
    if rewritten != body:
        rewritten = _ensure_core_taglib(rewritten)
    return rewritten
def _write_view_controller(project_root: Path, base_package: str) -> Path:
    pkg_path = base_package.replace('.', '/')
    p = project_root / f"src/main/java/{pkg_path}/web/ViewController.java"
    p.parent.mkdir(parents=True, exist_ok=True)
    content = (
        f"package {base_package}.web;\n\n"
        "import org.springframework.stereotype.Controller;\n"
        "import org.springframework.web.bind.annotation.GetMapping;\n"
        "import org.springframework.web.bind.annotation.PathVariable;\n\n"
        "@Controller\n"
        "public class ViewController {\n\n"
        "    @GetMapping(\"/view/{viewName}.do\")\n"
        "    public String view(@PathVariable String viewName) {\n"
        "        if (viewName == null || !viewName.matches(\"[A-Za-z0-9_]+\")) {\n"
        "            throw new IllegalArgumentException(\"Invalid view name\");\n"
        "        }\n"
        "        return viewName;\n"
        "    }\n"
        "}\n"
    )
    p.write_text(content, encoding='utf-8')
    return p
def _auth_alias_kind_for_rel_path(rel_path: str) -> str:
    rel = str(rel_path or '').replace('\\', '/').lower()
    basename = Path(rel).name
    stem = basename.rsplit('.', 1)[0]
    compact = re.sub(r'[^a-z0-9]+', '', stem)
    suffixes = ('list', 'detail', 'form', 'calendar', 'view', 'edit')
    suffix = next((item for item in suffixes if compact.endswith(item)), '')
    if not suffix:
        return ''
    base = compact[:-len(suffix)]
    joined = rel.replace('/', '')
    if any(tok in base for tok in ('login', 'signin')) or '/login/' in rel or '/auth/' in rel or 'login' in joined or 'signin' in joined:
        return 'login'
    if suffix in ('form', 'view', 'edit') and (any(tok in base for tok in ('signup', 'register', 'join')) or any(f'/{tok}/' in rel for tok in ('signup', 'register', 'join'))):
        return 'signup'
    return ''


def _repair_content_by_path(rel_path: str, content: str, base_package: str, preferred_entity: str = "", schema_map: Optional[Dict[str, Any]] = None) -> str:
    rel = (rel_path or "").replace('\\', '/')
    body = _strip_first_path_comment(content)
    filename = _rewrite_filename_to_preferred_entity(Path(rel).name, preferred_entity)
    logical = _canonical_crud_logical_path(filename)
    module_base = _module_base_package(base_package, rel)
    schema = None
    auth_helper_filenames = {
        'LoginController.java', 'LoginService.java', 'LoginServiceImpl.java', 'LoginVO.java', 'LoginDAO.java', 'LoginMapper.java', 'LoginMapper.xml',
        'IntegratedAuthService.java', 'IntegratedAuthServiceImpl.java', 'IntegratedAuthController.java',
        'CertLoginService.java', 'CertLoginServiceImpl.java', 'CertLoginController.java',
        'JwtLoginController.java', 'JwtTokenProvider.java', 'AuthLoginInterceptor.java', 'AuthenticInterceptor.java', 'AuthInterceptor.java', 'WebConfig.java', 'LoginDatabaseInitializer.java',
        'login.jsp', 'main.jsp', 'integrationGuide.jsp', 'certLogin.jsp', 'jwtLogin.jsp'
    }
    preferred_auth_schema = schema_map.get(preferred_entity) if (preferred_entity and schema_map) else None
    auth_alias_kind = _auth_alias_kind_for_rel_path(rel)
    if (preferred_auth_schema is None or not is_auth_kind(getattr(preferred_auth_schema, 'feature_kind', None) or '')) and schema_map:
        auth_owner = _auth_owner_entity(schema_map)
        if auth_owner:
            preferred_auth_schema = schema_map.get(auth_owner)
            if filename in auth_helper_filenames and auth_owner:
                preferred_entity = auth_owner
    if preferred_auth_schema is not None and is_auth_kind(getattr(preferred_auth_schema, 'feature_kind', None) or ''):
        preferred_module = _entity_var_from_name(preferred_entity or _auth_owner_entity(schema_map))
        auth_module_base = f"{base_package}.{preferred_module}" if preferred_module and not base_package.endswith(f'.{preferred_module}') else (base_package or 'egovframework.app')
        if auth_alias_kind == 'login':
            built = builtin_file('jsp/login/login.jsp', auth_module_base, preferred_auth_schema)
            if built:
                return built
        helper_logical = logical or rel.replace('src/main/java/', 'java/').replace('src/main/webapp/WEB-INF/views/', 'jsp/').replace('src/main/resources/', '')
        if filename in auth_helper_filenames:
            if filename == 'IntegratedAuthController.java':
                return ''
            built = builtin_file(helper_logical, auth_module_base, preferred_auth_schema)
            if built:
                body = built
                if filename.endswith('.java'):
                    body = re.sub(r"^\s*//\s*path:[^\n]*\n?", '', body, flags=re.IGNORECASE)
                    body = _enforce_java_package_and_imports(rel, body, base_package)
                return body
    if filename == "MyBatisConfig.java":
        cfg_schema = None
        if preferred_entity and schema_map:
            cfg_schema = schema_map.get(preferred_entity)
        if cfg_schema is None:
            cfg_schema = schema_for(preferred_entity or "Item")
        built = builtin_file("java/config/MyBatisConfig.java", base_package, cfg_schema)
        if built:
            body = built
    if logical:
        entity = _entity_from_filename(filename)
        if entity:
            if _should_force_jsp_crud_schema(entity, rel, body):
                base_schema = schema_map.get(entity) if schema_map else None
                table = getattr(base_schema, 'table', None) if base_schema is not None else None
                fields = list(getattr(base_schema, 'fields', []) or []) if base_schema is not None else []
                if not fields:
                    try:
                        fields = infer_schema_from_file_ops([{"path": rel_path, "content": content}], entity).fields
                    except Exception:
                        fields = []
                schema = schema_for(entity, inferred_fields=fields, table=table, feature_kind=FEATURE_KIND_CRUD)
            else:
                if schema_map:
                    schema = schema_map.get(entity)
                if schema is None:
                    try:
                        schema = infer_schema_from_file_ops([{"path": rel_path, "content": content}], entity)
                    except Exception:
                        schema = schema_for(entity)
            built = builtin_file(logical, module_base, schema)
            if built:
                body = built
    if rel.lower().endswith('.jsp'):
        body = _rewrite_direct_jsp_links(body, schema)
    if filename.endswith("Mapper.xml"):
        body = re.sub(r"^\s*<\?xml[^\n]*\?>\s*\n?", "", body, flags=re.IGNORECASE)
    if filename.endswith('.java'):
        body = re.sub(r"^\s*//\s*path:[^\n]*\n?", "", body, flags=re.IGNORECASE)
        body = re.sub(r'import\s+egovframework\.[\w\.]*cmm[\w\.]*EgovAbstractServiceImpl\s*;', 'import egovframework.rte.fdl.cmmn.EgovAbstractServiceImpl;', body)
        body = _enforce_java_package_and_imports(rel, body, base_package)
    return body


def _ensure_auth_bundle_files(project_root: Path, base_package: str, schema_map: Optional[Dict[str, Any]], cfg: ProjectConfig) -> List[str]:
    changed: List[str] = []
    if not schema_map:
        return changed
    extra_text = cfg.effective_extra_requirements() if hasattr(cfg, "effective_extra_requirements") else (cfg.extra_requirements or "")
    frontend_key = (cfg.frontend_key or "jsp").strip().lower() or "jsp"
    auth_owner = _auth_owner_entity(schema_map)
    for entity, schema in (schema_map or {}).items():
        if schema is None or not is_auth_kind(getattr(schema, 'feature_kind', None) or ''):
            continue
        if auth_owner and str(entity) != str(auth_owner):
            continue
        canonical_tasks = _canonical_tasks_for_schema(schema, frontend_key)
        for task in canonical_tasks:
            logical = str((task or {}).get('path') or '').replace('\\', '/').strip()
            if not logical:
                continue
            rel = _normalize_out_path(logical, base_package, entity, '', extra_text)
            rel = _map_frontend_rel_path(rel, cfg.frontend_key)
            if not rel:
                continue
            target = project_root / rel
            auth_module = _entity_var_from_name(entity)
            if auth_module:
                module_base = f"{base_package}.{auth_module}" if not base_package.endswith(f".{auth_module}") else base_package
            else:
                module_base = _module_base_package(base_package, rel, '', extra_text)
            built = builtin_file(logical, module_base, schema)
            if not built:
                continue
            built = _repair_content_by_path(rel, built, base_package, entity, schema_map)
            if target.exists():
                try:
                    existing = target.read_text(encoding='utf-8', errors='ignore')
                except Exception:
                    existing = ''
                if _is_valid_auth_helper_content(rel, existing):
                    continue
            try:
                status = _write_file(project_root, rel, built, overwrite=True)
                if status in {'created', 'overwritten'}:
                    changed.append(rel)
            except Exception:
                continue
    return changed

def _file_op_dependency_priority(rel_path: str) -> int:
    rel = (rel_path or '').replace('\\', '/').strip()
    name = Path(rel).name
    lower = rel.lower()
    if name == 'pom.xml':
        return 0
    if name in {'application.properties', 'application.yml', 'application.yaml'}:
        return 1
    if name == 'schema.sql':
        return 2
    if lower.endswith('/mybatisconfig.java'):
        return 5
    if name.endswith('VO.java'):
        return 10
    if name.endswith('Mapper.java'):
        return 20
    if name.endswith('Mapper.xml') or '/mapper/' in lower and name.endswith('.xml'):
        return 30
    if name.endswith('Service.java'):
        return 40
    if name.endswith('ServiceImpl.java'):
        return 50
    if name.endswith('Controller.java') or name.endswith('RestController.java'):
        return 60
    if lower.endswith('.jsp') or lower.endswith('.html'):
        return 70
    if lower.startswith('frontend/react/src/api/') or lower.startswith('frontend/vue/src/api/'):
        return 80
    if '/router/' in lower or '/routes/' in lower or '/stores/' in lower or '/constants/' in lower:
        return 85
    if '/pages/' in lower or '/views/' in lower or '/components/' in lower:
        return 90
    if lower.endswith('.css') or lower.endswith('.js') or lower.endswith('.jsx') or lower.endswith('.vue'):
        return 95
    return 100
def _sort_file_ops_for_dependency_order(file_ops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ordered = list(file_ops or [])
    ordered.sort(key=lambda item: (_file_op_dependency_priority(item.get('path', '')), (item.get('path') or '').replace('\\', '/').lower()))
    return ordered
_FRONTEND_COMPACTABLE_EXTENSIONS = ('.jsp', '.html', '.css', '.js', '.jsx', '.tsx', '.vue', '.xfdl', '.xjs')


def _is_frontend_compactable_path(rel_path: str) -> bool:
    rel = str(rel_path or '').replace('\\', '/').lower()
    if not rel.endswith(_FRONTEND_COMPACTABLE_EXTENSIONS):
        return False
    return (
        rel.startswith('src/main/webapp/')
        or rel.startswith('src/main/resources/static/')
        or rel.startswith('frontend/react/')
        or rel.startswith('frontend/vue/')
        or rel.startswith('frontend/nexacro/')
    )


def _dedupe_exact_lines(body: str, predicate) -> str:
    seen: set[str] = set()
    out: List[str] = []
    for line in (body or '').splitlines():
        key = line.strip()
        if predicate(key):
            if key in seen:
                continue
            seen.add(key)
        out.append(line.rstrip())
    return '\n'.join(out)


def _compact_frontend_content(rel_path: str, content: str) -> str:
    body = str(content or '').replace('\r\n', '\n').replace('\r', '\n')
    if not _is_frontend_compactable_path(rel_path):
        return body
    lower = str(rel_path or '').replace('\\', '/').lower()
    if lower.endswith(('.jsp', '.html', '.vue', '.jsx', '.tsx')):
        body = re.sub(r'\s*<span class="autopj-field__hint">.*?</span>', '', body, flags=re.DOTALL)
        body = re.sub(r'<p class="autopj-eyebrow">\s*</p>', '', body)
        body = re.sub(r'<div class="autopj-form-hero__meta">\s*</div>', '', body, flags=re.DOTALL)
        body = re.sub(r'<div class="action-bar">\s*</div>', '', body, flags=re.DOTALL)
        body = re.sub(
            r'<div class="autopj-form-section-header">\s*<div>\s*(<h3 class="autopj-section-title">.*?</h3>)\s*</div>\s*</div>',
            r'\1',
            body,
            flags=re.DOTALL,
        )
        body = re.sub(r'(?m)^\s*<p class="autopj-eyebrow">.*?</p>\s*\n?', '', body)
        body = _dedupe_exact_lines(
            body,
            lambda key: key.startswith('<%@ taglib') or key.startswith('<%@ include') or key.startswith('<link ') or key.startswith('<script ') or key.startswith('import '),
        )
    body = re.sub(r'(?m)[ \t]+$', '', body)
    body = re.sub(r'\n{3,}', '\n\n', body)
    return body.strip() + '\n'


def _write_file(project_root: Path, rel_path: str, content: str, overwrite: bool) -> str:
    target = project_root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    if existed and not overwrite:
        return "skipped"
    body = _compact_frontend_content(rel_path, content or "")
    target.write_text(body, encoding="utf-8")
    try:
        if target.name == "mvnw":
            import stat
            target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except Exception:
        pass
    return "overwritten" if existed else "created"
def _infer_entities_from_ops(file_ops: List[Dict[str, Any]]) -> List[str]:
    entities: List[str] = []
    strong_suffixes = {
        'VO.java', 'Service.java', 'ServiceImpl.java', 'Mapper.java', 'Mapper.xml',
        '_SQL.xml', '_SQL_mysql.xml', '_SQL_oracle.xml', '_SQL_postgresql.xml'
    }
    auth_helper_entities = {'IntegratedAuth', 'CertLogin', 'JwtLogin', 'JwtToken', 'AuthLoginInterceptor', 'AuthenticInterceptor', 'AuthInterceptor', 'WebConfig', 'WebMvcConfig', 'LoginDatabaseInitializer'}
    auth_helper_seen = False
    for it in file_ops or []:
        path = (it.get("path") or "").replace("\\", "/")
        filename = Path(path).name
        entity, suffix = _split_crud_filename(filename)
        if entity in auth_helper_entities:
            auth_helper_seen = True
            if 'Login' not in entities:
                entities.append('Login')
            continue
        if entity and suffix in strong_suffixes and entity not in entities:
            entities.append(entity)
            continue
        if path.lower().endswith("mapper.xml"):
            xml = it.get("content") or ""
            m = re.search(r'namespace="[^"]*\.([A-Za-z0-9_]+)Mapper"', xml)
            if m:
                cand = m.group(1)
                if cand in auth_helper_entities:
                    auth_helper_seen = True
                    if 'Login' not in entities:
                        entities.append('Login')
                    continue
                if cand and cand not in entities:
                    entities.append(cand)
    if auth_helper_seen and 'Login' not in entities:
        entities.insert(0, 'Login')
    return entities
def _ddl_for_entity(entity: str) -> str:
    return ddl(schema_for(entity))
def _write_schema_sql_from_entities(project_root: Path, entities: List[str]) -> Optional[Path]:
    uniq: List[str] = []
    for entity in entities or []:
        en = (entity or "").strip()
        if en and en not in uniq:
            uniq.append(en)
    if not uniq:
        return None
    ddls = [_ddl_for_entity(e) for e in uniq]
    return write_schema_sql(project_root, "\n\n".join(ddls))
def _apply_mysql_ddl(db: Dict[str, Any], ddls: List[str], project_root: Optional[Path] = None) -> str:
    try:
        import mysql.connector
    except Exception as e:
        return f"mysql.connector not available: {e}"
    host = db.get("host","localhost")
    port = int(db.get("port",3306) or 3306)
    user = db.get("user","")
    password = db.get("password","")
    database = db.get("database","")
    if not (user and database):
        return "skipped(no db creds)"

    preferred_statements = [stmt for stmt in (ddls or []) if str(stmt or '').strip()]
    schema_statements: List[str] = []
    if project_root is not None:
        schema_statements = _load_sql_statements_from_project(project_root, 'schema.sql')
    statements = _merge_sql_statements(preferred_statements, schema_statements)
    if not statements:
        return "skipped(no schema statements)"

    bootstrap = mysql.connector.connect(host=host, port=port, user=user, password=password)
    bootstrap_cur = bootstrap.cursor()
    bootstrap_cur.execute(f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci")
    bootstrap.commit()
    bootstrap_cur.close()
    bootstrap.close()

    statements = _normalize_recreate_sql_statements(statements)

    conn = mysql.connector.connect(host=host, port=port, user=user, password=password, database=database)
    cur = conn.cursor()
    expected_tables = _expected_table_names_from_sql(statements)
    if expected_tables:
        cur.execute('SET FOREIGN_KEY_CHECKS=0')
        for table_name in reversed(expected_tables):
            cur.execute(f"DROP TABLE IF EXISTS `{table_name}`")
        cur.execute('SET FOREIGN_KEY_CHECKS=1')
    for sql in statements:
        cur.execute(sql)
    conn.commit()

    expected_tables = _expected_table_names_from_sql(statements)
    if expected_tables:
        existing_tables = set(_existing_tables_in_mysql(cur, database))
        missing = [name for name in expected_tables if name not in existing_tables]
        if missing:
            cur.close()
            conn.close()
            return f"failed(missing_tables={','.join(sorted(missing))})"

    cur.close()
    conn.close()
    return f"ok(statements={len(statements)}, tables={','.join(_expected_table_names_from_sql(statements))})"


def _is_entry_only_nav_entity(name: str | None) -> bool:
    token = str(name or '').strip().lower()
    return token in {'index', 'home', 'main'}

def _is_entry_only_nav_route(url: str | None) -> bool:
    route = str(url or '').strip().lower()
    if not route:
        return True
    return route in {'/', '/index', '/index.do', '/home', '/home.do', '/main', '/main.do'} or route.startswith('/index/') or route.startswith('/home/') or route.startswith('/main/')

def _schema_feature_family(schema: Any) -> str:
    routes = getattr(schema, "routes", {}) or {}
    feature_kind = str(getattr(schema, "feature_kind", "") or "").strip().upper()
    if "login" in routes or "AUTH" in feature_kind:
        return "auth"
    if "calendar" in routes or "SCHEDULE" in feature_kind:
        return "calendar"
    if "DASHBOARD" in feature_kind or "REPORT" in feature_kind:
        return "dashboard"
    if "MASTER_DETAIL" in feature_kind:
        return "master_detail"
    if feature_kind in {"READONLY", "SEARCH"}:
        return "readonly"
    return "crud"
def _pick_main_route_from_schema_map(schema_map: Dict[str, Any]) -> str:
    if not schema_map:
        return "/"
    ordered = list((schema_map or {}).items())
    for entity, schema in ordered:
        entity_var = getattr(schema, 'entity_var', None) or (entity[:1].lower() + entity[1:] if entity else '')
        if _is_entry_only_nav_entity(entity) or _is_entry_only_nav_entity(entity_var):
            continue
        routes = getattr(schema, "routes", {}) or {}
        for key, value in routes.items():
            cand = str(value or "").strip()
            if not cand or '{' in cand or '}' in cand or _is_entry_only_nav_route(cand):
                continue
            if key == "calendar" or "/calendar.do" in cand.lower() or "calendar" in cand.lower():
                return cand
    for family in ("auth", "calendar", "dashboard", "readonly", "crud"):
        for entity, schema in ordered:
            entity_var = getattr(schema, 'entity_var', None) or (entity[:1].lower() + entity[1:] if entity else '')
            if _is_entry_only_nav_entity(entity) or _is_entry_only_nav_entity(entity_var):
                continue
            if _schema_feature_family(schema) != family:
                continue
            routes = getattr(schema, "routes", {}) or {}
            for key in ("login", "calendar", "dashboard", "list", "detail"):
                value = str(routes.get(key) or "").strip()
                if value and '{' not in value and '}' not in value and not _is_entry_only_nav_route(value):
                    return value
    for _entity, schema in ordered:
        routes = getattr(schema, "routes", {}) or {}
        for key in ("login", "calendar", "dashboard", "list", "detail", "main"):
            value = str(routes.get(key) or "").strip()
            if value and '{' not in value and '}' not in value:
                return value
    return "/"
def _build_autopj_theme_css() -> str:
    return """/* AUTOPJ THEME START */
:root {
  --autopj-bg: #f4f6fb;
  --autopj-surface: #ffffff;
  --autopj-surface-soft: #f8fafc;
  --autopj-border: #d8e1ef;
  --autopj-text: #1f2a37;
  --autopj-text-muted: #637287;
  --autopj-primary: #1f4fbf;
  --autopj-primary-soft: #eaf0ff;
  --autopj-accent: #f4a000;
  --autopj-danger: #dc2626;
  --autopj-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
  --autopj-radius-lg: 20px;
  --autopj-radius-md: 14px;
  --autopj-radius-sm: 10px;
  --autopj-topbar-height: 68px;
  --autopj-sidebar-width: 248px;
  --autopj-content-max: 1480px;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: Arial, Helvetica, sans-serif;
  color: var(--autopj-text);
  background: var(--autopj-bg);
  line-height: 1.5;
  overflow-x: hidden;
  padding-top: calc(var(--autopj-topbar-height) + 12px);
  padding-left: calc(var(--autopj-sidebar-width) + 20px);
}
body.autopj-nav-open { overflow: hidden; }
a { color: var(--autopj-primary); text-decoration: none; }
a:hover { text-decoration: underline; }
img { max-width: 100%; }
.autopj-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 30;
  background: linear-gradient(180deg, #1f4fbf 0%, #173a8f 100%);
  color: #fff;
  box-shadow: 0 8px 24px rgba(23, 58, 143, 0.2);
}
.autopj-header__inner {
  width: 100%;
  min-height: var(--autopj-topbar-height);
  padding: 14px 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.autopj-header__brand-wrap { display: flex; align-items: center; gap: 16px; min-width: 0; }
.autopj-header__brand {
  color: #fff;
  font-weight: 800;
  font-size: 20px;
  letter-spacing: .02em;
  white-space: nowrap;
}
.autopj-header__brand:hover { text-decoration: none; }
.autopj-header__project { color: rgba(255,255,255,.78); font-size: 13px; }
.autopj-header__nav { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.autopj-header__link {
  display: inline-flex;
  align-items: center;
  min-height: 38px;
  padding: 0 12px;
  border-radius: 999px;
  color: #fff;
  background: rgba(255,255,255,.12);
  border: 1px solid rgba(255,255,255,.16);
  font-weight: 700;
}
.autopj-header__link:hover { text-decoration: none; background: rgba(255,255,255,.2); }
.autopj-header__link.is-active { background: rgba(255,255,255,.22); border-color: rgba(255,255,255,.45); box-shadow: inset 0 0 0 1px rgba(255,255,255,.18); }
.autopj-nav-toggle {
  display: none;
  min-width: 44px;
  min-height: 44px;
  padding: 0 12px;
  border-radius: 14px;
  background: rgba(255,255,255,.14);
  border: 1px solid rgba(255,255,255,.18);
  color: #fff;
  font-size: 18px;
  font-weight: 800;
}
.autopj-nav-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  opacity: 0;
  pointer-events: none;
  transition: opacity .2s ease;
  z-index: 18;
}
body.autopj-nav-open .autopj-nav-overlay {
  opacity: 1;
  pointer-events: auto;
}
.autopj-leftnav {
  position: fixed;
  top: calc(var(--autopj-topbar-height) + 12px);
  left: 0;
  bottom: 0;
  width: var(--autopj-sidebar-width);
  padding: 18px 14px 24px;
  overflow-y: auto;
  z-index: 20;
}
.autopj-leftnav__panel {
  background: linear-gradient(180deg, #ffffff 0%, #f7faff 100%);
  border: 1px solid var(--autopj-border);
  border-radius: 22px;
  box-shadow: var(--autopj-shadow);
  padding: 18px 14px;
}
.autopj-leftnav__title { margin: 0 0 6px; font-size: 18px; font-weight: 800; }
.autopj-leftnav__subtitle { margin: 0 0 18px; color: var(--autopj-text-muted); font-size: 13px; }
.autopj-leftnav__section + .autopj-leftnav__section { margin-top: 14px; padding-top: 14px; border-top: 1px solid #e5eaf3; }
.autopj-leftnav__section-title { margin: 0 0 10px; color: var(--autopj-text-muted); font-size: 12px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.autopj-leftnav__menu { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.autopj-leftnav__link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 42px;
  padding: 10px 12px;
  border-radius: 14px;
  color: var(--autopj-text);
  background: #fff;
  border: 1px solid transparent;
  font-weight: 700;
}
.autopj-leftnav__link:hover { text-decoration: none; border-color: #ccdaff; background: #f4f8ff; }
.autopj-leftnav__link.is-active { color: var(--autopj-primary); border-color: #bfd0ff; background: #edf3ff; }
.autopj-leftnav__meta { font-size: 11px; color: var(--autopj-text-muted); }
.container,
.page-shell,
.calendar-shell,
.login-shell,
.dashboard-shell,
.master-detail-shell {
  width: min(100%, var(--autopj-content-max));
  margin: 0 auto;
  padding: 24px 20px 36px;
}
.page-card,
.panel,
.calendar-card,
.card,
.card-panel,
.login-card,
.summary-card,
.detail-card,
.list-card,
.form-card,
.filter-card,
.right-bottom-area {
  background: var(--autopj-surface);
  border: 1px solid var(--autopj-border);
  border-radius: var(--autopj-radius-lg);
  box-shadow: var(--autopj-shadow);
}
.header,
.page-header,
.toolbar,
.calendar-toolbar,
.list-toolbar,
.filter-row,
.action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.breadcrumb,
.breadcrumb ol {
  list-style: none;
  margin: 0 0 16px;
  padding: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--autopj-text-muted);
  font-size: 13px;
}
.breadcrumb-item + .breadcrumb-item::before {
  content: ">";
  margin-right: 8px;
  color: #94a3b8;
}
.btn,
button,
input[type="submit"],
input[type="button"] {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 38px;
  border: 1px solid transparent;
  border-radius: var(--autopj-radius-sm);
  padding: 0 14px;
  background: var(--autopj-primary);
  color: #fff;
  cursor: pointer;
  font-weight: 600;
}
.btn:hover,
button:hover,
input[type="submit"]:hover,
input[type="button"]:hover {
  filter: brightness(0.97);
  text-decoration: none;
}
.btn-secondary,
.btn-light,
.btn-outline,
.btn-default {
  background: var(--autopj-surface-soft);
  color: var(--autopj-text);
  border-color: var(--autopj-border);
}
input[type="text"],
input[type="password"],
input[type="date"],
input[type="number"],
select,
textarea,
.form-control {
  width: 100%;
  min-height: 40px;
  border: 1px solid var(--autopj-border);
  border-radius: 12px;
  padding: 10px 12px;
  background: #fff;
}
textarea { min-height: 120px; resize: vertical; }
.form-group, .field, .search-field { margin-bottom: 14px; }
label { display: inline-block; margin-bottom: 6px; font-weight: 600; color: var(--autopj-text); }
.autopj-eyebrow {
  margin: 0 0 8px;
  color: var(--autopj-primary);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.autopj-form-page { display: grid; gap: 18px; }
.autopj-form-hero { padding: 22px 24px; display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; flex-wrap: wrap; }
.autopj-form-title { margin: 0; font-size: 30px; line-height: 1.2; }
.autopj-form-subtitle { margin: 8px 0 0; color: var(--autopj-text-muted); }
.autopj-form-hero__meta { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; }
.autopj-form-card { padding: 22px 24px; }
.autopj-form-section-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 18px; }
.autopj-section-title { margin: 0; font-size: 18px; font-weight: 800; }
.autopj-section-subtitle { margin: 6px 0 0; color: var(--autopj-text-muted); font-size: 13px; }
.autopj-form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.autopj-field { display: flex; flex-direction: column; gap: 8px; padding: 16px; border: 1px solid var(--autopj-border); border-radius: 18px; background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%); }
.autopj-field--full { grid-column: 1 / -1; }
.autopj-field__label { font-size: 14px; font-weight: 800; color: var(--autopj-text); }
.autopj-field__hint { color: var(--autopj-text-muted); font-size: 12px; line-height: 1.4; }
.autopj-form-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: flex-end; margin-top: 22px; padding-top: 18px; border-top: 1px solid #e5eaf3; }
input[type="datetime-local"],
input[type="time"] {
  width: 100%;
  min-height: 40px;
  border: 1px solid var(--autopj-border);
  border-radius: 12px;
  padding: 10px 12px;
  background: #fff;
}
hr { border: 0; border-top: 1px solid #e5eaf3; }
.empty, .empty-state, .helper-text {
  padding: 18px;
  border-radius: 14px;
  background: #f8fafc;
  color: var(--autopj-text-muted);
  border: 1px dashed var(--autopj-border);
}
.badge,
.status-badge,
.event-chip,
.chip,
.tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  background: #fff5db;
  color: #8a5400;
  font-size: 12px;
  font-weight: 700;
  border: 1px solid #f3d087;
}
.table-wrap { overflow-x: auto; }
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--autopj-surface);
  border-radius: 16px;
  overflow: hidden;
}
th, td {
  border: 1px solid #e5eaf3;
  padding: 12px 10px;
  text-align: left;
  vertical-align: top;
}
th {
  background: #f8fafc;
  color: #334155;
  font-weight: 700;
}
.list-group, .schedule-list, .event-list { margin: 0; padding: 0; list-style: none; }
.list-group-item, .event-item {
  padding: 14px 16px;
  border-bottom: 1px solid #e5eaf3;
}
.list-group-item:last-child, .event-item:last-child { border-bottom: 0; }
.calendar-grid,
.cell-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 8px;
}
.weekday {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 8px;
  color: var(--autopj-text-muted);
  font-weight: 700;
}
.calendar-cell,
.cell {
  min-height: 132px;
  padding: 10px;
  border: 1px solid #e5eaf3;
  border-radius: 14px;
  background: #fff;
}
.day-no {
  font-weight: 700;
  margin-bottom: 8px;
}
.right-bottom-area {
  margin-top: 18px;
  padding: 16px;
}
.summary,
.summary-grid,
.panel-grid,
.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}
.tile,
.stat-card,
.summary-item {
  padding: 18px;
  border: 1px solid var(--autopj-border);
  border-radius: 18px;
  background: linear-gradient(180deg, #ffffff 0%, #f6f9ff 100%);
}
@media (max-width: 1180px) {
  body {
    padding-left: 0;
    padding-top: calc(var(--autopj-topbar-height) + 12px);
  }
  .autopj-nav-toggle { display: inline-flex; }
  .autopj-header__inner { align-items: flex-start; flex-direction: column; }
  .autopj-header__nav { width: 100%; overflow-x: auto; padding-bottom: 4px; }
  .autopj-leftnav {
    top: var(--autopj-topbar-height);
    width: min(86vw, 320px);
    padding: 12px;
    transform: translateX(-110%);
    transition: transform .22s ease;
  }
  body.autopj-nav-open .autopj-leftnav { transform: translateX(0); }
  .container,
  .page-shell,
  .calendar-shell,
  .login-shell,
  .dashboard-shell,
  .master-detail-shell {
    padding: 16px 12px 24px;
  }
}
@media (max-width: 768px) {
  .autopj-header__project { display: none; }
  .autopj-header__brand-wrap { width: 100%; justify-content: space-between; }
  .autopj-header__nav { flex-wrap: nowrap; justify-content: flex-start; }
  .calendar-grid,
  .cell-grid,
  .weekday,
  .summary,
  .summary-grid,
  .panel-grid,
  .stats-grid,
  .autopj-form-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .autopj-form-hero__meta { align-items: flex-start; }
  .calendar-cell,
  .cell { min-height: 110px; }
  th, td {
    padding: 10px 8px;
    font-size: 14px;
  }
}
@media (max-width: 560px) {
  .calendar-grid,
  .cell-grid,
  .weekday,
  .summary,
  .summary-grid,
  .panel-grid,
  .stats-grid,
  .autopj-form-grid {
    grid-template-columns: 1fr;
  }
  .autopj-form-hero,
  .autopj-form-section-header,
  .autopj-form-actions {
    align-items: flex-start;
    justify-content: flex-start;
  }
  .autopj-header__inner { padding: 12px 14px; }
  .autopj-header__link { min-height: 34px; padding: 0 10px; font-size: 13px; }
}
/* AUTOPJ THEME END */
"""
def _merge_theme_block(existing: str, block: str) -> str:
    body = existing or ""
    start = "/* AUTOPJ THEME START */"
    end = "/* AUTOPJ THEME END */"
    if start in body and end in body:
        return re.sub(re.escape(start) + r".*?" + re.escape(end), block.strip(), body, flags=re.DOTALL)
    if body.strip():
        return body.rstrip() + "\n\n" + block.strip() + "\n"
    return block.strip() + "\n"
def _friendly_route_meta(route_key: str | None = None) -> str:
    key = (route_key or '').strip().lower()
    return {
        'main': '메인',
        'list': '목록',
        'calendar': '달력',
        'detail': '상세',
        'view': '상세',
        'edit': '등록/수정',
        'form': '등록/수정',
        'create': '등록',
        'dashboard': '대시보드',
        'login': '로그인',
        'signup': '회원가입',
        'auth_helper': '인증 안내',
        'approval': '승인',
        'admin': '관리자',
    }.get(key, route_key or '메뉴')

def _friendly_nav_label(entity: str, route_key: str | None = None) -> str:
    entity_name = (entity or '').strip() or '메뉴'
    entity_labels = {
        'schedule': '일정',
        'member': '회원',
        'user': '사용자',
        'account': '계정',
        'notice': '공지사항',
        'board': '게시판',
        'login': '로그인',
        'dashboard': '대시보드',
        'room': '공간',
        'reservation': '예약',
        'approval': '승인',
        'admin': '관리자',
        'reservationapproval': '예약 승인',
        'reservationadmin': '예약 관리자',
    }
    entity_low = entity_name.lower()
    if (route_key or '').strip().lower() == 'signup' and entity_low in {'member', 'user', 'account', 'login', 'auth'}:
        return '회원가입'
    label = entity_labels.get(entity_low, entity_name)
    if route_key:
        route_label = _friendly_route_meta(route_key)
        if route_label and route_label not in {'메인'} and route_label != label:
            return f"{label} {route_label}"
    return label
def _extract_request_mapping_path(annotation: str) -> str:
    ann = annotation or ''
    m = re.search(r'@(?:GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping)\(\s*"([^"]+)"', ann)
    if m:
        return m.group(1).strip()
    m = re.search(r'@RequestMapping\(\s*"([^"]+)"', ann)
    if m:
        return m.group(1).strip()
    m = re.search(r'(?:value|path)\s*=\s*"([^"]+)"', ann)
    if m:
        return m.group(1).strip()
    return ''
def _annotation_http_method(annotation: str) -> str:
    ann = (annotation or '').strip()
    if '@GetMapping' in ann:
        return 'GET'
    if '@PostMapping' in ann:
        return 'POST'
    if '@PutMapping' in ann:
        return 'PUT'
    if '@DeleteMapping' in ann:
        return 'DELETE'
    if '@PatchMapping' in ann:
        return 'PATCH'
    if '@RequestMapping' in ann:
        upper = ann.upper()
        for method in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH'):
            if f'REQUESTMETHOD.{method}' in upper:
                return method
        return 'ANY'
    return ''
def _combine_route_parts(base: str, child: str) -> str:
    left = (base or '').strip()
    right = (child or '').strip()
    if not left and not right:
        return '/'
    if not left:
        return right if right.startswith('/') else '/' + right
    if not right:
        return left if left.startswith('/') else '/' + left
    return '/' + '/'.join(part.strip('/') for part in (left, right) if part.strip('/'))
def _route_key_from_url_or_view(url: str, view_name: str, method_name: str) -> str:
    hay = ' '.join(x for x in ((url or '').lower(), (view_name or '').lower(), (method_name or '').lower()) if x)
    auth_helper_markers = ('integrationguide', 'integratedlogin', 'integratedcallback', 'certlogin', 'jwtlogin', 'ssologin')
    if any(token in hay for token in auth_helper_markers):
        return 'auth_helper'
    if any(token in hay for token in ('signup', 'register', 'join')):
        return 'signup'
    if 'login' in hay:
        return 'login'
    if 'logout' in hay:
        return 'logout'
    if 'calendar' in hay:
        return 'calendar'
    if 'dashboard' in hay or 'report' in hay:
        return 'dashboard'
    if '/edit' in hay or 'form' in hay or ' edit' in hay:
        return 'edit'
    if '/create' in hay or ' create' in hay:
        return 'create'
    if '/list' in hay or 'list' in hay:
        return 'list'
    if '/view' in hay or '/detail' in hay or 'detail' in hay or ' view' in hay:
        return 'detail'
    if method_name and method_name.lower() in {'index', 'main', 'home'}:
        return 'main'
    return 'main'
def _detect_route_required_params(params_sig: str) -> bool:
    sig = params_sig or ''
    if '@PathVariable' in sig:
        return True
    for m in re.finditer(r'@RequestParam\(([^)]*)\)', sig):
        args = m.group(1)
        if 'required=false' in args.replace(' ', '').lower():
            continue
        return True
    return False
def _discover_project_route_infos(project_root: Path) -> List[Dict[str, Any]]:
    java_root = Path(project_root) / 'src/main/java'
    if not java_root.exists():
        return []
    route_infos: List[Dict[str, Any]] = []
    class_req_re = re.compile(r'@RequestMapping\(([^)]*)\)')
    view_re = re.compile(r'return\s+"([^"]+)"\s*;')
    method_name_re = re.compile(r'public\s+String\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(')
    for controller in java_root.rglob('*Controller.java'):
        body = controller.read_text(encoding='utf-8', errors='ignore')
        class_base = ''
        class_match = class_req_re.search(body)
        if class_match:
            class_base = _extract_request_mapping_path(class_match.group(0))
        lines = body.splitlines()
        i = 0
        pending_annotations: List[str] = []
        while i < len(lines):
            stripped = lines[i].strip()
            if stripped.startswith('@'):
                pending_annotations.append(stripped)
                i += 1
                continue
            if 'public String ' not in stripped:
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
            m_name = method_name_re.search(signature)
            method_name = m_name.group(1).strip() if m_name else ''
            params_sig = ''
            if m_name:
                params_start = m_name.end()
                depth = 1
                cursor = params_start
                while cursor < len(signature) and depth > 0:
                    ch = signature[cursor]
                    if ch == '(':
                        depth += 1
                    elif ch == ')':
                        depth -= 1
                    cursor += 1
                params_sig = signature[params_start: max(params_start, cursor - 1)]
            block_lines: List[str] = []
            j = i + 1
            while j < len(lines):
                next_stripped = lines[j].strip()
                if next_stripped.startswith('@') and 'public String ' not in next_stripped:
                    break
                block_lines.append(lines[j])
                if 'return ' in next_stripped and ';' in next_stripped:
                    break
                j += 1
            block = "\n".join(block_lines)
            ann = "\n".join(pending_annotations)
            http_method = _annotation_http_method(ann)
            if http_method in {'GET', 'ANY'}:
                method_path = _extract_request_mapping_path(ann)
                full_url = _combine_route_parts(class_base, method_path)
                if full_url and full_url != '/':
                    if '{' in full_url or '}' in full_url or controller.stem == 'ViewController':
                        pending_annotations = []
                        i = max(i + 1, j)
                        continue
                    view_name = ''
                    view_match = view_re.search(block)
                    if view_match:
                        view_name = view_match.group(1).strip()
                    if not (view_name.startswith('redirect:') or view_name.startswith('forward:')):
                        required_params = _detect_route_required_params(params_sig)
                        entity = ''
                        norm = full_url.strip('/')
                        if norm:
                            entity = norm.split('/', 1)[0]
                        if not entity and view_name:
                            entity = view_name.split('/', 1)[0]
                        entity = entity or controller.stem.replace('Controller', '') or 'main'
                        route_infos.append({
                            'controller': str(controller),
                            'entity': entity,
                            'url': full_url,
                            'view_name': view_name,
                            'method_name': method_name,
                            'route_key': _route_key_from_url_or_view(full_url, view_name, method_name),
                            'required_params': required_params,
                        })
            pending_annotations = []
            i = max(i + 1, j)
        
    return route_infos
def _group_route_infos_by_entity(route_infos: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for info in route_infos or []:
        key = str(info.get('entity') or '').strip() or 'main'
        grouped.setdefault(key, []).append(info)
    return grouped
def _discover_fallback_main_route(project_root: Path) -> str:
    java_root = Path(project_root) / 'src/main/java'
    if not java_root.exists():
        return '/'
    entry_domains = {'index', 'home', 'main', 'landing', 'root'}
    ranked: List[str] = []
    seen = set()
    for controller in java_root.rglob('*Controller.java'):
        body = controller.read_text(encoding='utf-8', errors='ignore')
        class_match = re.search(r'@RequestMapping\(([^)]*)\)', body)
        base = _extract_request_mapping_path(class_match.group(0)) if class_match else ''
        entity = ''
        norm = base.strip('/')
        if norm:
            entity = norm.split('/', 1)[0].lower()
        stem = controller.stem.replace('Controller', '').lower()
        if entity in entry_domains or stem in entry_domains:
            continue
        candidates: List[str] = []
        for route in re.findall(r'@GetMapping\(\s*"([^"]+)"', body):
            candidates.append(_combine_route_parts(base, route))
        for route in re.findall(r'@RequestMapping\(([^)]*RequestMethod\.GET[^)]*)\)', body, re.DOTALL):
            path_match = re.search(r'(?:value|path)\s*=\s*"([^"]+)"', route)
            if path_match:
                candidates.append(_combine_route_parts(base, path_match.group(1)))
        for route in candidates:
            low = route.lower()
            if '{' in route or '}' in route:
                continue
            if any(token in low for token in ('delete', 'remove', 'save', 'update', 'create', 'detail', 'form')):
                continue
            if route not in seen:
                seen.add(route)
                ranked.append(route)
    for token in ('/calendar.do', '/list.do', '/dashboard', '/main', '/login'):
        for route in ranked:
            if token in route.lower():
                return route
    return ranked[0] if ranked else '/'

def _discover_navigation_items(project_root: Path, preferred_entity: str | None = None) -> Optional[Dict[str, Any]]:
    route_infos = _discover_project_route_infos(project_root)
    if not route_infos:
        return None
    grouped = _group_route_infos_by_entity(route_infos)
    preferred_low = (preferred_entity or '').strip().lower()
    entity_key = ''
    if preferred_low:
        for cand in grouped:
            if cand.lower() == preferred_low:
                entity_key = cand
                break
    def _normalize_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        safe_items = [info for info in items if not info.get('required_params')] or list(items)
        unique_by_url: Dict[str, Dict[str, Any]] = {}
        for info in safe_items:
            url = str(info.get('url') or '').strip()
            if not url:
                continue
            prev = unique_by_url.get(url)
            if prev is None:
                unique_by_url[url] = info
                continue
            prev_rank = {'main': 0, 'detail': 1, 'list': 2, 'calendar': 3, 'dashboard': 3, 'edit': 4, 'create': 4, 'login': 5}.get(str(prev.get('route_key') or ''), 0)
            cur_rank = {'main': 0, 'detail': 1, 'list': 2, 'calendar': 3, 'dashboard': 3, 'edit': 4, 'create': 4, 'login': 5}.get(str(info.get('route_key') or ''), 0)
            if cur_rank > prev_rank:
                unique_by_url[url] = info
        return list(unique_by_url.values())
    def _pick_main(items: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], str, str]:
        normalized = _normalize_items(items)
        for key in ['login', 'calendar', 'dashboard', 'list', 'main']:
            found = next((info for info in normalized if str(info.get('route_key') or '') == key), None)
            if found:
                return found, str(found.get('url') or '/'), key
        if normalized:
            found = normalized[0]
            return found, str(found.get('url') or '/'), str(found.get('route_key') or 'main')
        return None, '/', 'main'
    if not entity_key:
        score_order = []
        for cand, items in grouped.items():
            found_main, _main_url, main_key = _pick_main(items)
            score = (10 if found_main else 0) + (10 if main_key in {'login', 'calendar', 'dashboard', 'list', 'main'} else 0) + len(_normalize_items(items))
            score_order.append((score, cand))
        score_order.sort(reverse=True)
        entity_key = score_order[0][1] if score_order else next(iter(grouped))
    top: List[Tuple[str, str, str]] = [('홈', '/', 'home')]
    side: List[Tuple[str, str, str]] = []
    used_top = {'/'}
    used_side: set[str] = set()
    routes_flat: List[Dict[str, Any]] = []
    entity_main_map: Dict[str, Dict[str, Any]] = {}
    main_url = '/'
    for entity_name, items in grouped.items():
        normalized = _normalize_items(items)
        routes_flat.extend(normalized)
        found_main, entity_main_url, main_key = _pick_main(items)
        if not found_main:
            continue
        entity_main_map[entity_name] = found_main
        if entity_name == entity_key:
            main_url = entity_main_url
        if entity_main_url not in used_top and entity_main_url != '/':
            top.append((_friendly_nav_label(entity_name, main_key), entity_main_url, main_key))
            used_top.add(entity_main_url)
    preferred_items = _normalize_items(grouped.get(entity_key) or [])
    for key in ['login', 'signup', 'calendar', 'dashboard', 'list', 'edit', 'create', 'form']:
        for info in preferred_items:
            if str(info.get('route_key') or '') != key:
                continue
            url = str(info.get('url') or '').strip()
            if not url or url == '/' or url in used_side:
                continue
            side.append((_friendly_nav_label(entity_key, key), url, key))
            used_side.add(url)
    for entity_name, info in entity_main_map.items():
        if entity_name == entity_key:
            continue
        url = str(info.get('url') or '').strip()
        key = str(info.get('route_key') or 'main')
        if not url or url == '/' or url in used_side:
            continue
        side.append((_friendly_nav_label(entity_name, key), url, key))
        used_side.add(url)
    if not side and entity_key in entity_main_map:
        info = entity_main_map[entity_key]
        side.append((_friendly_nav_label(entity_key, str(info.get('route_key') or 'main')), str(info.get('url') or '/'), str(info.get('route_key') or 'main')))
    return {
        'entity': entity_key,
        'main_url': main_url,
        'top': top[:8],
        'side': side[:10],
        'routes': routes_flat,
    }
def _nav_items_from_schema_map(schema_map: Dict[str, Any] | None, preferred_entity: str | None = None) -> Dict[str, List[Tuple[str, str, str]]]:
    top_items: List[Tuple[str, str, str]] = []
    side_items: List[Tuple[str, str, str]] = []
    preferred_low = (preferred_entity or '').strip().lower()
    seen_top: set[str] = set()
    seen_side: set[str] = set()
    main_infos: List[Tuple[str, str, str]] = []
    for entity, schema in (schema_map or {}).items():
        routes = getattr(schema, 'routes', None) or {}
        entity_var = getattr(schema, 'entity_var', None) or (entity[:1].lower() + entity[1:] if entity else 'item')
        if _is_entry_only_nav_entity(entity) or _is_entry_only_nav_entity(entity_var):
            continue
        main_candidates = ['login', 'calendar', 'dashboard', 'list', 'main']
        main_key = next((k for k in main_candidates if k in routes and routes.get(k) and not _is_entry_only_nav_route(routes.get(k))), None)
        if not main_key:
            for k, v in routes.items():
                if v and '{' not in str(v) and not _is_entry_only_nav_route(v):
                    main_key = k
                    break
        if main_key:
            url = str(routes.get(main_key) or '').strip()
            if url and url not in seen_top and not _is_entry_only_nav_route(url):
                label = _friendly_nav_label(entity_var, main_key)
                top_items.append((label, url, entity_var))
                main_infos.append((label, url, main_key))
                seen_top.add(url)
        if preferred_low and entity_var.lower() != preferred_low and entity.lower() != preferred_low:
            continue
        for key in ['login', 'signup', 'calendar', 'dashboard', 'list', 'form', 'edit', 'create']:
            url = str(routes.get(key) or '').strip()
            if not url or '{' in url or url in seen_side or _is_entry_only_nav_route(url):
                continue
            side_items.append((_friendly_nav_label(entity_var, key), url, key))
            seen_side.add(url)
    if not top_items:
        top_items = [('홈', '/', 'home')]
    else:
        if '/' not in seen_top:
            top_items.insert(0, ('홈', '/', 'home'))
    for label, url, key in main_infos:
        if url in seen_side or url == '/' or _is_entry_only_nav_route(url):
            continue
        side_items.append((label, url, key))
        seen_side.add(url)
    if not side_items:
        fallback = [(label, url, key) for label, url, key in (top_items[1:] or top_items[:1]) if not _is_entry_only_nav_route(url)]
        side_items = fallback or [(label, url, key) for label, url, key in (top_items[1:] or top_items[:1])]
    return {'top': top_items[:8], 'side': side_items[:10]}
def _build_header_jsp(
    schema_map: Dict[str, Any] | None = None,
    preferred_entity: str | None = None,
    project_title: str | None = None,
    nav_override: Optional[Dict[str, Any]] = None,
) -> str:
    nav = (nav_override or {}).get('top') or _nav_items_from_schema_map(schema_map, preferred_entity)['top']
    nav = [item for item in nav if len(item) >= 2 and '{' not in str(item[1]) and '}' not in str(item[1])]
    if not nav:
        nav = _nav_items_from_schema_map(schema_map, preferred_entity)['top']
    project_label = (project_title or '').strip() or 'AUTOPJ Project'
    home_route = (nav_override or {}).get('main_url') or _pick_main_route_from_schema_map(schema_map or {}) or '/'
    if '{' in str(home_route) or '}' in str(home_route):
        home_route = _pick_main_route_from_schema_map(schema_map or {}) or '/'
    links = '\n'.join(
        f"      <a class=\"autopj-header__link\" href=\"<c:url value='{url}' />\">{label}</a>"
        for label, url, _ in nav
    )
    return (
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>\n'
        '<link rel="stylesheet" class="autopj-generated" href="${pageContext.request.contextPath}/css/common.css" />\n'
        '<link rel="stylesheet" class="autopj-generated" href="${pageContext.request.contextPath}/css/schedule.css" />\n'
        '<script src="${pageContext.request.contextPath}/js/jquery.min.js"></script>\n'
        '<script src="${pageContext.request.contextPath}/js/common.js"></script>\n'
        '<div class="autopj-header">\n'
        '  <div class="autopj-header__inner">\n'
        '    <div class="autopj-header__brand-wrap">\n'
        f"      <a class=\"autopj-header__brand\" href=\"<c:url value='{home_route}' />\">AUTOPJ</a>\n"
        f'      <span class="autopj-header__project">{project_label}</span>\n'
        '      <button type="button" class="autopj-nav-toggle" data-autopj-nav-toggle aria-expanded="false" aria-controls="autopj-leftnav">☰</button>\n'
        '    </div>\n'
        '    <nav class="autopj-header__nav" aria-label="상단 메뉴">\n'
        f'{links}\n'
        '    </nav>\n'
        '  </div>\n'
        '</div>\n'
    )
def _build_leftnav_jsp(
    schema_map: Dict[str, Any] | None = None,
    preferred_entity: str | None = None,
    nav_override: Optional[Dict[str, Any]] = None,
) -> str:
    nav = (nav_override or {}).get('side') or _nav_items_from_schema_map(schema_map, preferred_entity)['side']
    nav = [item for item in nav if len(item) >= 2 and '{' not in str(item[1]) and '}' not in str(item[1])]
    if not nav:
        nav = _nav_items_from_schema_map(schema_map, preferred_entity)['side']
    current_hint = str((nav_override or {}).get('entity') or (preferred_entity or '').strip() or '업무')
    main_url = str((nav_override or {}).get('main_url') or '')
    if '{' in main_url or '}' in main_url:
        main_url = ''
    items_buf = []
    for idx, (label, url, meta) in enumerate(nav):
        active_class = ' is-active' if (main_url and url == main_url) or (not main_url and idx == 0) else ''
        items_buf.append(
            f"        <li><a class=\"autopj-leftnav__link{active_class}\" href=\"<c:url value='{url}' />\"><span>{label}</span><span class=\"autopj-leftnav__meta\">{_friendly_route_meta(meta)}</span></a></li>"
        )
    items = '\n'.join(items_buf)
    return (
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>\n'
        '<div class="autopj-nav-overlay" data-autopj-nav-overlay></div>\n'
        '<aside id="autopj-leftnav" class="autopj-leftnav" aria-label="왼쪽 메뉴">\n'
        '  <div class="autopj-leftnav__panel">\n'
        f'    <h2 class="autopj-leftnav__title">{_friendly_nav_label(current_hint)}</h2>\n'
        '    <div class="autopj-leftnav__section">\n'
        '      <div class="autopj-leftnav__section-title">바로가기</div>\n'
        '      <ul class="autopj-leftnav__menu">\n'
        f'{items}\n'
        '      </ul>\n'
        '    </div>\n'
        '  </div>\n'
        '</aside>\n'
    )
def _is_jsp_layout_partial(rel_path: str) -> bool:
    norm = (rel_path or '').replace('\\', '/').lower()
    return norm.endswith('/web-inf/views/common/header.jsp') or norm.endswith('/web-inf/views/common/leftnav.jsp') or norm.endswith('/web-inf/views/common/footer.jsp') or norm.endswith('/web-inf/views/common/taglibs.jsp') or norm.endswith('/web-inf/views/include.jsp') or norm.endswith('/web-inf/views/common/include.jsp') or norm.endswith('/web-inf/views/common/navi.jsp') or norm.endswith('/web-inf/views/common/layout.jsp') or norm.endswith('/web-inf/views/common.jsp') or norm.endswith('/web-inf/views/_layout.jsp')
def _replace_legacy_common_include_aliases(body: str) -> str:
    text = body or ''
    alias_pairs = [
        ('<%@ include file="/WEB-INF/views/common.jsp" %>', '<%@ include file="/WEB-INF/views/common/header.jsp" %>\n<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>'),
        ('<%@ include file="/common.jsp" %>', '<%@ include file="/WEB-INF/views/common/header.jsp" %>\n<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>'),
        ('<%@ include file="common.jsp" %>', '<%@ include file="/WEB-INF/views/common/header.jsp" %>\n<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>'),
    ]
    for src, dest in alias_pairs:
        text = text.replace(src, dest)
    return text

def _strip_jsp_include_directives(body: str) -> str:
    cleaned = re.sub(r'(?im)^\s*<%@\s*include\s+file\s*=\s*"[^"]+"\s*%>\s*\n?', '', body or '')
    return cleaned.lstrip('\ufeff')
def _ensure_jsp_header_file(
    project_root: Path,
    schema_map: Optional[Dict[str, Any]] = None,
    preferred_entity: Optional[str] = None,
    project_title: Optional[str] = None,
    nav_override: Optional[Dict[str, Any]] = None,
) -> str:
    rel = "src/main/webapp/WEB-INF/views/common/header.jsp"
    p = project_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    desired = _build_header_jsp(schema_map=schema_map, preferred_entity=preferred_entity, project_title=project_title, nav_override=nav_override)
    existing = p.read_text(encoding="utf-8") if p.exists() else ""
    if existing != desired:
        p.write_text(desired, encoding="utf-8")
    return rel
def _ensure_jsp_leftnav_file(
    project_root: Path,
    schema_map: Optional[Dict[str, Any]] = None,
    preferred_entity: Optional[str] = None,
    nav_override: Optional[Dict[str, Any]] = None,
) -> str:
    rel = "src/main/webapp/WEB-INF/views/common/leftNav.jsp"
    p = project_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    desired = _build_leftnav_jsp(schema_map=schema_map, preferred_entity=preferred_entity, nav_override=nav_override)
    existing = p.read_text(encoding="utf-8") if p.exists() else ""
    if existing != desired:
        p.write_text(desired, encoding="utf-8")
    return rel
def _ensure_jsp_taglibs_file(project_root: Path) -> str:
    rel = "src/main/webapp/WEB-INF/views/common/taglibs.jsp"
    p = project_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    desired = (
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>\n'
        '<%@ taglib prefix="fmt" uri="http://java.sun.com/jsp/jstl/fmt"%>\n'
        '<%@ taglib prefix="fn" uri="http://java.sun.com/jsp/jstl/functions"%>\n'
    )
    existing = p.read_text(encoding="utf-8") if p.exists() else ""
    if existing != desired:
        p.write_text(desired, encoding="utf-8")
    return rel


def _ensure_jsp_include_file(project_root: Path) -> str:
    rel = "src/main/webapp/WEB-INF/views/include.jsp"
    desired = (
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>\n'
        '<%@ taglib prefix="fmt" uri="http://java.sun.com/jsp/jstl/fmt"%>\n'
        '<%@ taglib prefix="fn" uri="http://java.sun.com/jsp/jstl/functions"%>\n'
    )
    for rel_candidate in (rel, "src/main/webapp/WEB-INF/views/common/include.jsp"):
        p = project_root / rel_candidate
        p.parent.mkdir(parents=True, exist_ok=True)
        existing = p.read_text(encoding="utf-8") if p.exists() else ""
        if existing != desired:
            p.write_text(desired, encoding="utf-8")
    return rel


def _ensure_jsp_domain_header_alias_files(project_root: Path) -> List[str]:
    base = project_root / 'src/main/webapp/WEB-INF/views'
    common_header = base / 'common/header.jsp'
    if not common_header.exists():
        return []
    include_re = re.compile(r'<%@\s*include\s+file\s*=\s*"([^"]+)"\s*%>')
    created: List[str] = []
    for jsp in base.rglob('*.jsp'):
        body = jsp.read_text(encoding='utf-8')
        for m in include_re.finditer(body):
            inc = (m.group(1) or '').strip()
            if not (inc.startswith('/WEB-INF/views/') and inc.endswith('/_header.jsp')):
                continue
            rel = inc.split('/WEB-INF/views/', 1)[1].lstrip('/')
            alias_rel = f'src/main/webapp/WEB-INF/views/{rel}'
            alias_path = project_root / alias_rel
            desired = '<%@ include file="/WEB-INF/views/common/header.jsp" %>\n'
            existing = alias_path.read_text(encoding='utf-8') if alias_path.exists() else ''
            if existing != desired:
                alias_path.parent.mkdir(parents=True, exist_ok=True)
                alias_path.write_text(desired, encoding='utf-8')
            created.append(alias_rel)
    return sorted(set(created))


def _ensure_jsp_layout_file(project_root: Path) -> str:
    rel = "src/main/webapp/WEB-INF/views/_layout.jsp"
    p = project_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    desired = (
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<%-- AUTOPJ deprecated layout placeholder. Individual JSP views must include common/header.jsp and common/leftNav.jsp directly. --%>\n'
    )
    existing = p.read_text(encoding="utf-8") if p.exists() else ""
    if existing != desired:
        p.write_text(desired, encoding="utf-8")
    return rel
def _ensure_jsp_common_layout_file(project_root: Path) -> str:
    rel = "src/main/webapp/WEB-INF/views/common/layout.jsp"
    p = project_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    desired = (
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<%-- AUTOPJ shared layout fragment placeholder. Concrete domain JSPs must include common/header.jsp and common/leftNav.jsp directly, not sample routes or inline jQuery. --%>\n'
    )
    existing = p.read_text(encoding="utf-8") if p.exists() else ""
    if existing != desired:
        p.write_text(desired, encoding="utf-8")
    return rel
def _mirror_jsp_asset_to_static(project_root: Path, rel_path: str, content: str) -> None:
    normalized = str(rel_path or '').replace('\\', '/').strip()
    if not normalized.startswith('src/main/webapp/'):
        return
    suffix = normalized[len('src/main/webapp/'):].lstrip('/')
    if not suffix or suffix.startswith('WEB-INF/'):
        return
    static_path = project_root / 'src/main/resources/static' / suffix
    static_path.parent.mkdir(parents=True, exist_ok=True)
    static_path.write_text(content, encoding='utf-8')

def _ensure_jsp_common_css(project_root: Path) -> str:
    rel = "src/main/webapp/css/common.css"
    p = project_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = p.read_text(encoding="utf-8") if p.exists() else ""
    merged = _merge_theme_block(existing, _build_autopj_theme_css())
    p.write_text(merged, encoding="utf-8")
    _mirror_jsp_asset_to_static(project_root, rel, merged)
    return rel

def _ensure_jsp_common_css_partial(project_root: Path) -> str:
    rel = "src/main/webapp/WEB-INF/views/common/css.jsp"
    p = project_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    desired = (
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<link rel="stylesheet" href="${pageContext.request.contextPath}/css/common.css"/>\n'
    )
    existing = p.read_text(encoding="utf-8") if p.exists() else ""
    if existing != desired:
        p.write_text(desired, encoding="utf-8")
    return rel
def _build_common_js() -> str:
    return """(function () {
  function setExpanded(button, expanded) {
    if (button) {
      button.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    }
  }
  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }
  function normalizePath(value) {
    try {
      var url = new URL(value, window.location.origin);
      var path = url.pathname || '/';
      return path.replace(/\\/+$|\\/$/g, '') || '/';
    } catch (e) {
      return '/';
    }
  }
  function pad(value) {
    return String(value).padStart(2, '0');
  }
  function safeDate(value) {
    if (!value) return null;
    var text = String(value).trim();
    if (!text) return null;
    text = text.replace(/\./g, '-').replace(/\//g, '-');
    text = text.replace(/\s+/g, ' ');
    text = text.replace('오전', 'AM').replace('오후', 'PM');
    var ampm = text.match(/(AM|PM)\s*(\d{1,2}):(\d{2})(?::(\d{2}))?/i);
    if (ampm) {
      var hour = parseInt(ampm[2], 10);
      if (/PM/i.test(ampm[1]) && hour < 12) hour += 12;
      if (/AM/i.test(ampm[1]) && hour === 12) hour = 0;
      text = text.replace(/(AM|PM)\s*\d{1,2}:\d{2}(?::\d{2})?/i, pad(hour) + ':' + ampm[3] + ':' + pad(ampm[4] || '00'));
    }
    var javaDate = text.match(/^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s+([A-Za-z]{3})\s+(\d{1,2})\s+(\d{2}):(\d{2}):(\d{2})\s+([A-Za-z]{2,5})\s+(\d{4})$/);
    if (javaDate) {
      var months = {Jan:'01',Feb:'02',Mar:'03',Apr:'04',May:'05',Jun:'06',Jul:'07',Aug:'08',Sep:'09',Oct:'10',Nov:'11',Dec:'12'};
      var mm = months[javaDate[2]] || '01';
      text = javaDate[8] + '-' + mm + '-' + pad(javaDate[3]) + 'T' + javaDate[4] + ':' + javaDate[5] + ':' + javaDate[6];
    } else {
      text = text.replace(/\s+/, 'T');
      if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(text)) text += ':00';
    }
    var parsed = new Date(text);
    return isNaN(parsed.getTime()) ? null : parsed;
  }
  function formatDate(date) {
    if (!date) return '-';
    return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate());
  }
  function formatDateTime(date) {
    if (!date) return '-';
    return formatDate(date) + ' ' + pad(date.getHours()) + ':' + pad(date.getMinutes()) + ':' + pad(date.getSeconds());
  }
  function normalizeDateInputValue(value) {
    var parsed = safeDate(value);
    return parsed ? formatDate(parsed) : value;
  }
  function normalizeDatetimeInputValue(value) {
    var parsed = safeDate(value);
    return parsed ? (formatDate(parsed) + 'T' + pad(parsed.getHours()) + ':' + pad(parsed.getMinutes()) + ':' + pad(parsed.getSeconds())) : value;
  }
  function enhanceTemporalFields() {
    document.querySelectorAll('input[data-autopj-temporal="date"], input[type="date"]').forEach(function (input) {
      var rawDate = input.getAttribute('data-autopj-raw-value') || input.value;
      if (rawDate) input.value = normalizeDateInputValue(rawDate);
    });
    document.querySelectorAll('input[data-autopj-temporal="datetime-local"], input[type="datetime-local"]').forEach(function (input) {
      var rawDateTime = input.getAttribute('data-autopj-raw-value') || input.value;
      if (rawDateTime) input.value = normalizeDatetimeInputValue(rawDateTime);
      if (!input.getAttribute('step')) input.setAttribute('step', '1');
      var form = input.form;
      if (form && !form.dataset.autopjTemporalBound) {
        form.dataset.autopjTemporalBound = 'true';
        form.addEventListener('submit', function () {
          form.querySelectorAll('input[data-autopj-temporal="datetime-local"], input[type="datetime-local"]').forEach(function (field) {
            if (field.value) field.value = normalizeDatetimeInputValue(field.value);
          });
          form.querySelectorAll('input[data-autopj-temporal="date"], input[type="date"]').forEach(function (field) {
            if (field.value) field.value = normalizeDateInputValue(field.value);
          });
        });
      }
    });
    document.querySelectorAll('[data-autopj-display="datetime"]').forEach(function (node) {
      var raw = node.getAttribute('data-raw-value') || node.textContent;
      var parsed = safeDate(raw);
      if (parsed) node.textContent = formatDateTime(parsed);
    });
    document.querySelectorAll('[data-autopj-display="date"]').forEach(function (node) {
      var raw = node.getAttribute('data-raw-value') || node.textContent;
      var parsed = safeDate(raw);
      if (parsed) node.textContent = formatDate(parsed);
    });
  }
  function markActiveNav() {
    var current = normalizePath(window.location.pathname || '/');
    var links = Array.prototype.slice.call(document.querySelectorAll('.autopj-header__link, .autopj-leftnav__link'));
    var best = null;
    links.forEach(function (link) {
      link.classList.remove('is-active');
      var href = link.getAttribute('href');
      if (!href || href === '#') return;
      var target = normalizePath(href);
      if (target === current) {
        best = { link: link, score: 1000 };
        return;
      }
      if (target !== '/' && current.indexOf(target) === 0) {
        var score = target.length;
        if (!best || score > best.score) {
          best = { link: link, score: score };
        }
      }
    });
    if (!best) {
      best = links.find(function (link) { return normalizePath(link.getAttribute('href') || '/') === '/'; });
      if (best && best.tagName) {
        best = { link: best, score: 1 };
      }
    }
    if (best && best.link) {
      best.link.classList.add('is-active');
    }
  }
  ready(function () {
    var body = document.body;
    var sidebar = document.getElementById('autopj-leftnav');
    var toggle = document.querySelector('[data-autopj-nav-toggle]');
    var overlay = document.querySelector('[data-autopj-nav-overlay]');
    function closeNav() {
      body.classList.remove('autopj-nav-open');
      setExpanded(toggle, false);
    }
    function openNav() {
      body.classList.add('autopj-nav-open');
      setExpanded(toggle, true);
    }
    if (toggle) {
      toggle.addEventListener('click', function () {
        if (body.classList.contains('autopj-nav-open')) {
          closeNav();
        } else {
          openNav();
        }
      });
    }
    if (overlay) {
      overlay.addEventListener('click', closeNav);
    }
    if (sidebar) {
      sidebar.querySelectorAll('a').forEach(function (link) {
        link.addEventListener('click', function () {
          if (window.matchMedia('(max-width: 1180px)').matches) {
            closeNav();
          }
          window.setTimeout(markActiveNav, 10);
        });
      });
    }
    document.querySelectorAll('.autopj-header__link').forEach(function (link) {
      link.addEventListener('click', function () {
        window.setTimeout(markActiveNav, 10);
      });
    });
    window.addEventListener('resize', function () {
      if (!window.matchMedia('(max-width: 1180px)').matches) {
        closeNav();
      }
    });
    closeNav();
    markActiveNav();
    enhanceTemporalFields();
  });
})();
"""
def _ensure_jsp_common_js(project_root: Path) -> str:
    rel = "src/main/webapp/js/common.js"
    p = project_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    body = _build_common_js()
    p.write_text(body, encoding="utf-8")
    _mirror_jsp_asset_to_static(project_root, rel, body)
    return rel
def _build_schedule_css() -> str:
    return """/* AUTOPJ SCHEDULE THEME START */
.schedule-page { padding: 24px; }
.schedule-page .page-header { margin-bottom: 18px; }
.schedule-page__title { margin: 0; font-size: 28px; line-height: 1.2; }
.schedule-page__desc { margin: 6px 0 0; color: var(--autopj-text-muted); }
.calendar-toolbar { margin-bottom: 16px; }
.calendar-toolbar__title { font-size: 18px; font-weight: 700; }
.schedule-filters {
  display: grid;
  grid-template-columns: minmax(220px, 1.8fr) repeat(2, minmax(150px, 1fr)) auto;
  gap: 12px;
  margin-bottom: 18px;
}
.schedule-layout {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr);
  gap: 18px;
}
.calendar-board,
.schedule-sidepanel { padding: 18px; }
.calendar-weekdays,
.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 8px;
}
.calendar-weekdays { margin-bottom: 8px; }
.calendar-weekdays span {
  padding: 10px 8px;
  border-radius: 12px;
  background: #eef3ff;
  color: var(--autopj-primary);
  font-size: 13px;
  font-weight: 700;
  text-align: center;
}
.calendar-cell {
  min-height: 132px;
  padding: 10px;
  border: 1px solid #e5eaf3;
  border-radius: 16px;
  background: #fff;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.calendar-cell.is-muted {
  background: #f8fafc;
  color: #94a3b8;
}
.calendar-cell.is-today {
  border-color: var(--autopj-primary);
  box-shadow: inset 0 0 0 1px rgba(31, 79, 191, 0.25);
}
.calendar-cell__day { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-weight: 700; }
.calendar-cell__events { display: flex; flex-direction: column; gap: 6px; }
.calendar-event-chip {
  display: block;
  width: 100%;
  padding: 6px 8px;
  border-radius: 10px;
  background: #eff6ff;
  border: 1px solid #cfe0ff;
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 700;
  text-overflow: ellipsis;
  overflow: hidden;
  white-space: nowrap;
}
.calendar-event-chip.is-done { background: #ecfdf3; border-color: #b7f0cb; color: #166534; }
.calendar-event-chip.is-high { background: #fff7ed; border-color: #fed7aa; color: #c2410c; }
.schedule-list-panel__head { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:14px; }
.schedule-list-panel__count { color: var(--autopj-text-muted); font-size: 13px; }
.schedule-event-list { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 12px; }
.schedule-event-item {
  padding: 16px;
  border: 1px solid var(--autopj-border);
  border-radius: 16px;
  background: linear-gradient(180deg, #fff 0%, #f8fbff 100%);
}
.schedule-event-item__top,
.schedule-event-item__meta { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; }
.schedule-event-item__title { margin: 8px 0 6px; font-size: 17px; }
.schedule-event-item__description { margin: 0 0 10px; color: var(--autopj-text-muted); font-size: 14px; }
.schedule-event-item__actions { display:flex; gap:8px; flex-wrap:wrap; }
.summary-card { padding: 18px; }
.summary-card__label { color: var(--autopj-text-muted); font-size: 13px; }
.summary-card__value { margin-top: 6px; font-size: 28px; font-weight: 800; }
.autopj-hidden { display: none !important; }
@media (max-width: 1024px) {
  .schedule-layout { grid-template-columns: 1fr; }
  .schedule-filters { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 768px) {
  .schedule-page { padding: 16px; }
  .schedule-filters { grid-template-columns: 1fr; }
  .calendar-weekdays, .calendar-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .calendar-cell { min-height: 110px; }
}
/* AUTOPJ SCHEDULE THEME END */
"""
def _merge_named_block(existing: str, start_marker: str, end_marker: str, block: str) -> str:
    body = existing or ""
    if start_marker in body and end_marker in body:
        return re.sub(re.escape(start_marker) + r".*?" + re.escape(end_marker), block.strip(), body, flags=re.DOTALL)
    if body.strip():
        return body.rstrip() + "\n\n" + block.strip() + "\n"
    return block.strip() + "\n"
def _ensure_jsp_schedule_css(project_root: Path) -> str:
    rel = "src/main/webapp/css/schedule.css"
    p = project_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = p.read_text(encoding="utf-8") if p.exists() else ""
    merged = _merge_named_block(existing, "/* AUTOPJ SCHEDULE THEME START */", "/* AUTOPJ SCHEDULE THEME END */", _build_schedule_css())
    p.write_text(merged, encoding="utf-8")
    _mirror_jsp_asset_to_static(project_root, rel, merged)
    return rel
def _build_schedule_js() -> str:
    return """(function () {
  function safeDate(value) {
    if (!value) return null;
    var normalized = String(value).replace(' ', 'T');
    var parsed = new Date(normalized);
    return isNaN(parsed.getTime()) ? null : parsed;
  }
  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
  function pad(value) {
    return String(value).padStart(2, '0');
  }
  function formatDateLabel(date) {
    if (!date) return '-';
    return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate());
  }
  function formatDateTimeLabel(date) {
    if (!date) return '-';
    return formatDateLabel(date) + ' ' + pad(date.getHours()) + ':' + pad(date.getMinutes()) + ':' + pad(date.getSeconds());
  }
  function formatTimeLabel(date) {
    if (!date) return '';
    return pad(date.getHours()) + ':' + pad(date.getMinutes());
  }
  function isSameDate(a, b) {
    return !!a && !!b
      && a.getFullYear() === b.getFullYear()
      && a.getMonth() === b.getMonth()
      && a.getDate() === b.getDate();
  }
  function collectItems(root) {
    return Array.prototype.slice.call(root.querySelectorAll('.schedule-source-item')).map(function (node) {
      return {
        id: node.dataset.id || '',
        title: node.dataset.title || '제목 없음',
        content: node.dataset.content || '',
        start: safeDate(node.dataset.start),
        end: safeDate(node.dataset.end),
        status: (node.dataset.status || '').trim(),
        priority: (node.dataset.priority || '').trim(),
        location: node.dataset.location || '',
        allDay: (node.dataset.allDay || '').toLowerCase() === 'true',
        viewUrl: node.dataset.viewUrl || '#',
        editUrl: node.dataset.editUrl || '#'
      };
    });
  }
  function initSchedulePage(root) {
    var source = root.querySelector('[data-role="schedule-source"]');
    var calendarGrid = root.querySelector('[data-role="calendar-grid"]');
    var listWrap = root.querySelector('[data-role="schedule-list"]');
    var currentLabel = root.querySelector('[data-role="calendar-current-label"]');
    var totalEl = root.querySelector('[data-role="summary-total"]');
    var visibleEl = root.querySelector('[data-role="summary-visible"]');
    var highEl = root.querySelector('[data-role="summary-high"]');
    var searchInput = root.querySelector('[data-role="schedule-search"]');
    var statusFilter = root.querySelector('[data-role="status-filter"]');
    var priorityFilter = root.querySelector('[data-role="priority-filter"]');
    var monthCursor = new Date();
    monthCursor.setDate(1);
    monthCursor.setHours(0, 0, 0, 0);
    var items = collectItems(source || root);
    var selectedDate = new Date(monthCursor);

    function filteredItems() {
      var keyword = (searchInput && searchInput.value || '').trim().toLowerCase();
      var status = statusFilter && statusFilter.value || '';
      var priority = priorityFilter && priorityFilter.value || '';
      return items.filter(function (item) {
        var matchesKeyword = !keyword || [item.title, item.content, item.location].join(' ').toLowerCase().indexOf(keyword) >= 0;
        var matchesStatus = !status || item.status === status;
        var matchesPriority = !priority || item.priority === priority;
        return matchesKeyword && matchesStatus && matchesPriority;
      });
    }
    function renderSummary(active) {
      if (totalEl) totalEl.textContent = String(items.length);
      if (visibleEl) visibleEl.textContent = String(active.length);
      if (highEl) highEl.textContent = String(active.filter(function (item) { return item.priority && item.priority.toUpperCase().indexOf('HIGH') >= 0; }).length);
    }
    function renderList(active) {
      if (!listWrap) return;
      var selectedItems = active.filter(function (item) { return isSameDate(item.start, selectedDate); });
      if (!selectedItems.length) {
        listWrap.innerHTML = '<div class="empty-state">데이터가 없습니다.</div>';
        return;
      }
      listWrap.innerHTML = '<ul class="schedule-event-list">' + selectedItems.map(function (item) {
        var when = formatDateTimeLabel(item.start);
        var status = escapeHtml(item.status || '미정');
        var priority = escapeHtml(item.priority || '보통');
        var desc = escapeHtml(item.content || '상세 설명이 없습니다.');
        var location = escapeHtml(item.location || '장소 미정');
        return '<li class="schedule-event-item">'
          + '<div class="schedule-event-item__top"><span class="badge">' + status + '</span><span class="badge">' + priority + '</span></div>'
          + '<h3 class="schedule-event-item__title"><a href="' + escapeHtml(item.viewUrl) + '">' + escapeHtml(item.title) + '</a></h3>'
          + '<p class="schedule-event-item__description">' + desc + '</p>'
          + '<div class="schedule-event-item__meta"><span>' + when + '</span><span>' + location + '</span></div>'
          + '<div class="schedule-event-item__actions"><a class="btn btn-light" href="' + escapeHtml(item.viewUrl) + '">상세</a><a class="btn" href="' + escapeHtml(item.editUrl) + '">수정</a></div>'
          + '</li>';
      }).join('') + '</ul>';
    }
    function renderCalendar(active) {
      if (!calendarGrid) return;
      var first = new Date(monthCursor.getFullYear(), monthCursor.getMonth(), 1);
      var firstDay = first.getDay();
      var start = new Date(first);
      start.setDate(first.getDate() - firstDay);
      var today = new Date();
      today.setHours(0, 0, 0, 0);
      var cells = [];
      for (var i = 0; i < 42; i += 1) {
        var cellDate = new Date(start);
        cellDate.setDate(start.getDate() + i);
        cellDate.setHours(0, 0, 0, 0);
        var sameMonth = cellDate.getMonth() === monthCursor.getMonth();
        var dayItems = active.filter(function (item) { return isSameDate(item.start, cellDate); });
        var chips = dayItems.slice(0, 3).map(function (item) {
          var classes = 'calendar-event-chip';
          if (item.status && item.status.toUpperCase().indexOf('DONE') >= 0) classes += ' is-done';
          if (item.priority && item.priority.toUpperCase().indexOf('HIGH') >= 0) classes += ' is-high';
          return '<a class="' + classes + '" href="' + escapeHtml(item.viewUrl) + '" title="' + escapeHtml(item.title) + '">' + (item.start ? ('[' + escapeHtml(formatTimeLabel(item.start)) + '] ') : '') + escapeHtml(item.title) + '</a>';
        }).join('');
        if (dayItems.length > 3) {
          chips += '<span class="calendar-event-chip">외 ' + (dayItems.length - 3) + '건</span>';
        }
        var classes = 'calendar-cell';
        if (!sameMonth) classes += ' is-muted';
        if (cellDate.getTime() === today.getTime()) classes += ' is-today';
        if (isSameDate(cellDate, selectedDate)) classes += ' is-selected';
        cells.push('<button type="button" class="' + classes + '" data-role="calendar-cell" data-date="' + formatDateLabel(cellDate) + '"><div class="calendar-cell__day"><span>' + cellDate.getDate() + '</span><span>' + dayItems.length + '건</span></div><div class="calendar-cell__events">' + chips + '</div></button>');
      }
      calendarGrid.innerHTML = cells.join('');
      Array.prototype.slice.call(calendarGrid.querySelectorAll('[data-role="calendar-cell"]')).forEach(function (button) {
        button.addEventListener('click', function (event) {
          if (event.target && event.target.closest('a')) return;
          selectedDate = safeDate(button.dataset.date) || selectedDate;
          rerender();
        });
      });
      if (currentLabel) {
        currentLabel.textContent = monthCursor.getFullYear() + '년 ' + String(monthCursor.getMonth() + 1).padStart(2, '0') + '월 / 선택일 ' + formatDateLabel(selectedDate);
      }
    }
    function rerender() {
      var active = filteredItems();
      renderSummary(active);
      renderCalendar(active);
      renderList(active);
    }
    root.querySelectorAll('[data-action="prev-month"]').forEach(function (button) {
      button.addEventListener('click', function () {
        monthCursor = new Date(monthCursor.getFullYear(), monthCursor.getMonth() - 1, 1);
        selectedDate = new Date(monthCursor.getFullYear(), monthCursor.getMonth(), 1);
        rerender();
      });
    });
    root.querySelectorAll('[data-action="next-month"]').forEach(function (button) {
      button.addEventListener('click', function () {
        monthCursor = new Date(monthCursor.getFullYear(), monthCursor.getMonth() + 1, 1);
        selectedDate = new Date(monthCursor.getFullYear(), monthCursor.getMonth(), 1);
        rerender();
      });
    });
    [searchInput, statusFilter, priorityFilter].forEach(function (el) {
      if (!el) return;
      el.addEventListener('input', rerender);
      el.addEventListener('change', rerender);
    });
    rerender();
  }
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-autopj-schedule-page]').forEach(initSchedulePage);
  });
})();
"""
def _ensure_jsp_schedule_js(project_root: Path) -> str:
    rel = "src/main/webapp/js/schedule.js"
    p = project_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    body = _build_schedule_js()
    p.write_text(body, encoding="utf-8")
    _mirror_jsp_asset_to_static(project_root, rel, body)
    return rel
def _build_schedule_calendar_jsp() -> str:
    class _DefaultScheduleSchema:
        entity = "Schedule"
        entity_var = "schedule"
        feature_kind = "SCHEDULE"
        id_prop = "scheduleId"
        fields = [
            ("scheduleId", "schedule_id", "String"),
            ("title", "title", "String"),
            ("content", "content", "String"),
            ("startDatetime", "start_datetime", "String"),
            ("endDatetime", "end_datetime", "String"),
            ("allDayYn", "all_day_yn", "String"),
            ("statusCd", "status_cd", "String"),
            ("priorityCd", "priority_cd", "String"),
            ("location", "location", "String"),
            ("writerId", "writer_id", "String"),
            ("useYn", "use_yn", "String"),
            ("regDt", "reg_dt", "String"),
            ("updDt", "upd_dt", "String"),
        ]
        routes = {
            "calendar": "/schedule/calendar.do",
            "detail": "/schedule/view.do",
            "form": "/schedule/edit.do",
            "save": "/schedule/save.do",
            "delete": "/schedule/remove.do",
        }

    return _build_entity_calendar_jsp(_DefaultScheduleSchema())
def _calendar_field_candidates(schema: Any, preferred: List[str], fallback_tokens: List[str]) -> str:
    fields = list(getattr(schema, 'fields', []) or [])
    props = [str(prop or '') for prop, _col, _jt in fields]
    low_map = {prop.lower(): prop for prop in props if prop}
    for cand in preferred:
        if cand.lower() in low_map:
            return low_map[cand.lower()]
    for prop in props:
        low = prop.lower()
        if any(tok in low for tok in fallback_tokens):
            return prop
    return props[0] if props else ''

def _effective_schema_id_binding(schema: Any) -> Tuple[str, str]:
    fields = list(getattr(schema, 'fields', []) or [])
    schema_id_prop = str(getattr(schema, 'id_prop', '') or '').strip()
    schema_id_col = str(getattr(schema, 'id_column', '') or '').strip()
    if fields:
        if schema_id_prop:
            for prop, col, _jt in fields:
                if str(prop or '').strip() == schema_id_prop:
                    return str(prop or '').strip(), str(col or '').strip()
        if schema_id_col:
            for prop, col, _jt in fields:
                if str(col or '').strip() == schema_id_col:
                    return str(prop or '').strip(), str(col or '').strip()
        preferred = ['memberId', 'loginId', 'userId', 'accountId', 'customerId', 'adminId', 'scheduleId', 'reservationId', 'roomId', 'boardId', 'noticeId', 'postId']
        low_prop_map = {str(prop or '').strip().lower(): (str(prop or '').strip(), str(col or '').strip()) for prop, col, _jt in fields if str(prop or '').strip()}
        for cand in preferred:
            hit = low_prop_map.get(cand.lower())
            if hit:
                return hit
        for prop, col, _jt in fields:
            prop_text = str(prop or '').strip()
            col_text = str(col or '').strip()
            if prop_text.lower() == 'id' or col_text.lower() == 'id':
                return prop_text or 'id', col_text or 'id'
        for prop, col, _jt in fields:
            prop_text = str(prop or '').strip()
            col_text = str(col or '').strip()
            if prop_text.lower().endswith('id') or col_text.lower().endswith('_id'):
                return prop_text or 'id', col_text or prop_text
        first_prop, first_col, _first_type = fields[0]
        return str(first_prop or '').strip() or 'id', str(first_col or '').strip() or str(first_prop or '').strip() or 'id'
    return schema_id_prop or 'id', schema_id_col or schema_id_prop or 'id'
def _build_entity_calendar_jsp(schema: Any) -> str:
    entity = str(getattr(schema, 'entity', '') or 'Item')
    entity_label = _friendly_nav_label(entity)
    routes = getattr(schema, 'routes', None) or {}
    id_prop, _id_col = _effective_schema_id_binding(schema)
    title_prop = _calendar_field_candidates(schema, ['title', 'subject', 'purpose', 'name', 'roomName', 'reserverName'], ['title', 'subject', 'purpose', 'name'])
    content_prop = _calendar_field_candidates(schema, ['content', 'description', 'remark', 'memo', 'note'], ['content', 'description', 'remark', 'memo', 'note'])
    start_prop = _calendar_field_candidates(schema, ['startDatetime', 'startDate', 'startDt', 'regDt'], ['start', 'date', 'datetime'])
    end_prop = _calendar_field_candidates(schema, ['endDatetime', 'endDate', 'endDt', 'updDt'], ['end'])
    status_prop = _calendar_field_candidates(schema, ['statusCd', 'status', 'useYn'], ['status'])
    priority_prop = _calendar_field_candidates(schema, ['priorityCd', 'priority'], ['priority'])
    location_prop = _calendar_field_candidates(schema, ['location', 'roomName'], ['location', 'room'])
    calendar_route = str(routes.get('calendar') or routes.get('list') or '#')
    form_route = str(routes.get('form') or routes.get('edit') or routes.get('create') or '#')
    detail_route = str(routes.get('detail') or '#')
    title_expr = title_prop or id_prop
    content_expr = content_prop or title_expr
    location_expr = location_prop or ''
    status_expr = status_prop or ''
    priority_expr = priority_prop or ''
    start_expr = start_prop or ''
    end_expr = end_prop or ''
    location_attr = f'data-location="${{fn:escapeXml(item.{location_expr})}}"' if location_expr else 'data-location=""'
    status_attr = f'data-status="${{item.{status_expr}}}"' if status_expr else 'data-status=""'
    priority_attr = f'data-priority="${{item.{priority_expr}}}"' if priority_expr else 'data-priority=""'
    end_attr = f'data-end="${{item.{end_expr}}}"' if end_expr else 'data-end=""'
    if status_expr:
        selected_status_badge = f'''<span class="badge"><c:choose><c:when test="${{not empty row.{status_expr}}}"><c:out value="${{row.{status_expr}}}"/></c:when><c:otherwise>미정</c:otherwise></c:choose></span>'''
    else:
        selected_status_badge = '<span class="badge">미정</span>'
    selected_priority_badge = f'<c:if test="${{not empty row.{priority_expr}}}"><span class="badge"><c:out value="${{row.{priority_expr}}}"/></span></c:if>' if priority_expr else ''
    if content_expr:
        selected_description = f'''<c:choose><c:when test="${{not empty row.{content_expr}}}"><c:out value="${{row.{content_expr}}}"/></c:when><c:otherwise>상세 설명이 없습니다.</c:otherwise></c:choose>'''
    else:
        selected_description = '상세 설명이 없습니다.'
    selected_when = f'<c:out value="${{row.{start_expr}}}"/>' if start_expr else '-'
    selected_location = f'<c:out value="${{row.{location_expr}}}"/>' if location_expr else '장소 미정'
    return f'''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<%@ taglib prefix="fn" uri="http://java.sun.com/jsp/jstl/functions"%>
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{entity_label} 달력</title>
</head>
<body>
<%@ include file="/WEB-INF/views/common/header.jsp" %>
<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>
<div class="calendar-shell">
  <div class="page-card schedule-page" data-autopj-schedule-page>
    <div class="page-header">
      <div>
        <h1 class="schedule-page__title">{entity_label} 달력</h1>
        <p class="schedule-page__desc"></p>
      </div>
      <div class="action-bar">
        <a class="btn" href="<c:url value='{form_route}'/>">등록</a>
      </div>
    </div>
    <div class="summary-grid">
      <div class="summary-card"><div class="summary-card__label">전체 건수</div><div class="summary-card__value" data-role="summary-total">${{fn:length(list)}}</div></div>
      <div class="summary-card"><div class="summary-card__label">표시 일정</div><div class="summary-card__value" data-role="summary-visible">${{fn:length(list)}}</div></div>
      <div class="summary-card"><div class="summary-card__label">높은 우선순위</div><div class="summary-card__value" data-role="summary-high">0</div></div>
    </div>
    <div class="calendar-toolbar toolbar">
      <button type="button" class="btn btn-light" data-action="prev-month">이전 달</button>
      <div class="calendar-toolbar__title" data-role="calendar-current-label">
        <c:choose>
          <c:when test="${{not empty currentYear and not empty currentMonth}}"><c:out value="${{currentYear}}"/>년 <c:out value="${{currentMonth}}"/>월</c:when>
          <c:otherwise>-</c:otherwise>
        </c:choose>
      </div>
      <button type="button" class="btn btn-light" data-action="next-month">다음 달</button>
      <div class="action-bar" style="margin-left:auto;"><a class="btn" href="<c:url value='{form_route}'/>">등록</a></div>
    </div>
    <div class="schedule-layout">
      <div class="calendar-board card-panel">
        <div class="calendar-weekdays"><span>일</span><span>월</span><span>화</span><span>수</span><span>목</span><span>금</span><span>토</span></div>
        <div class="calendar-grid" data-role="calendar-grid">
          <c:forEach var="cell" items="${{calendarCells}}">
            <a class="calendar-cell" href="<c:url value='{calendar_route}'/>?year=${{currentYear}}&month=${{currentMonth}}&selectedDate=${{cell.date}}" style="text-decoration:none;color:inherit;">
              <div class="calendar-cell__day"><span><c:out value="${{cell.day}}"/></span><span><c:out value="${{cell.eventCount}}"/>건</span></div>
              <div class="calendar-cell__events">
                <c:forEach var="row" items="${{cell.events}}" begin="0" end="1">
                  <span class="calendar-event-chip"><c:out value="${{row.{title_expr}}}"/></span>
                </c:forEach>
                <c:if test="${{cell.eventCount gt 2}}"><span class="calendar-event-chip">외 <c:out value="${{cell.eventCount - 2}}"/>건</span></c:if>
              </div>
            </a>
          </c:forEach>
        </div>
        <div class="autopj-hidden" data-role="calendar-cells-source">
          <c:forEach var="cell" items="${{calendarCells}}">
            <div class="calendar-cell-source" data-date="${{cell.date}}" data-size="${{cell.eventCount}}"></div>
          </c:forEach>
        </div>
      </div>
      <div class="schedule-sidepanel right-bottom-area">
        <div class="schedule-list-panel__head">
          <h2>선택 날짜 일정</h2>
          <span class="schedule-list-panel__count">달력에서 날짜를 선택하세요.</span>
        </div>
        <div data-role="schedule-list">
          <c:choose>
            <c:when test="${{not empty selectedDateSchedules}}">
              <ul class="schedule-event-list">
                <c:forEach var="row" items="${{selectedDateSchedules}}">
                  <li class="schedule-event-item">
                    <div class="schedule-event-item__top">{selected_status_badge}{selected_priority_badge}</div>
                    <h3 class="schedule-event-item__title"><a href="<c:url value='{detail_route}'/>?{id_prop}=${{row.{id_prop}}}"><c:out value="${{row.{title_expr}}}"/></a></h3>
                    <p class="schedule-event-item__description">{selected_description}</p>
                    <div class="schedule-event-item__meta"><span>{selected_when}</span><span>{selected_location}</span></div>
                    <div class="schedule-event-item__actions"><a class="btn btn-light" href="<c:url value='{detail_route}'/>?{id_prop}=${{row.{id_prop}}}">상세</a><a class="btn" href="<c:url value='{form_route}'/>?{id_prop}=${{row.{id_prop}}}">수정</a></div>
                  </li>
                </c:forEach>
              </ul>
            </c:when>
            <c:otherwise><div class="empty-state">데이터가 없습니다.</div></c:otherwise>
          </c:choose>
        </div>
      </div>
    </div>
    <div class="autopj-hidden" data-role="selected-date-schedules-source">
      <c:forEach var="row" items="${{selectedDateSchedules}}">
        <div class="selected-schedule-source" data-id="${{row.{id_prop}}}"></div>
      </c:forEach>
    </div>
    <div class="autopj-hidden" data-role="schedule-source">
      <c:forEach var="item" items="${{list}}">
        <div class="schedule-source-item"
             data-id="${{item.{id_prop}}}"
             data-title="${{fn:escapeXml(item.{title_expr})}}"
             data-content="${{fn:escapeXml(item.{content_expr})}}"
             data-start="${{item.{start_expr}}}"
             {end_attr}
             {status_attr}
             {priority_attr}
             {location_attr}
             data-all-day="false"
             data-view-url="${{pageContext.request.contextPath}}{detail_route}?{id_prop}=${{item.{id_prop}}}"
             data-edit-url="${{pageContext.request.contextPath}}{form_route}?{id_prop}=${{item.{id_prop}}}"></div>
      </c:forEach>
    </div>
  </div>
</div>
<script src="${{pageContext.request.contextPath}}/js/common.js"></script>
<script src="${{pageContext.request.contextPath}}/js/schedule.js"></script>
</body>
</html>
'''
def _normalize_calendar_jsp(project_root: Path, rel_path: str, schema: Optional[Any] = None) -> bool:
    norm = (rel_path or "").replace("\\", "/")
    if not norm.lower().endswith('calendar.jsp'):
        return False
    path = project_root / norm
    if not path.exists():
        return False
    body = path.read_text(encoding='utf-8')
    lower = body.lower()
    needs_replace = False
    legacy_markers = (
        'fullcalendar.min.js', 'moment.min.js', 'onclick="prevmonth()"', 'onclick="nextmonth()"',
        'dayclick:', 'eventclick:', 'function prevmonth', 'function nextmonth', '$(', '$(document).ready'
    )
    if any(marker in lower for marker in legacy_markers):
        needs_replace = True
    if 'data-autopj-schedule-page' not in lower:
        needs_replace = True
    if '<style type="text/css">' in lower or '<style>' in lower:
        needs_replace = True
    has_server_cells = 'items="${calendarcells}"' in lower
    has_selected_list = 'items="${selecteddateschedules}"' in lower and 'schedule-event-list' in lower
    sidepanel_first = 'schedule-sidepanel right-bottom-area' in lower and 'calendar-board card-panel' in lower and lower.index('schedule-sidepanel right-bottom-area') < lower.index('calendar-board card-panel')
    if not has_server_cells or not has_selected_list or sidepanel_first:
        needs_replace = True
    if not needs_replace:
        return False
    if schema is None:
        return False
    path.write_text(_build_entity_calendar_jsp(schema), encoding='utf-8')
    return True
def _ensure_index_redirect(project_root: Path, target: str) -> str:
    rel = "src/main/webapp/index.jsp"
    p = project_root / rel
    dest = target or "/"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<%\n'
        f'    response.sendRedirect(request.getContextPath() + "{dest}");\n'
        '    return;\n'
        '%>\n',
        encoding="utf-8",
    )
    return rel
def _ensure_static_index_html(project_root: Path, target: str) -> str:
    rel = "src/main/resources/static/index.html"
    p = project_root / rel
    dest = target or "/"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        '<!DOCTYPE html>\n'
        '<html><head><meta charset="UTF-8"/><meta http-equiv="refresh" content="0;url=' + dest + '"/>'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0"/><title>Home</title>'
        '<script>window.location.replace("' + dest + '");</script></head>'
        '<body><noscript><a href="' + dest + '">Go</a></noscript></body></html>\n',
        encoding="utf-8",
    )
    return rel
_SHARED_JSP_ASSET_URLS = {
    '/css/common.css',
    '/css/schedule.css',
    '/js/jquery.min.js',
}


def _is_shared_jsp_asset_url(url: str) -> bool:
    return str(url or '').strip() in _SHARED_JSP_ASSET_URLS


def _strip_shared_jsp_asset_tags(body: str) -> str:
    updated = body or ''
    for url in sorted(_SHARED_JSP_ASSET_URLS):
        href_pattern = re.compile(
            rf'^\s*<link\b[^>]*href=["\']\$\{{pageContext\.request\.contextPath\}}{re.escape(url)}["\'][^>]*/?>\s*\n?',
            flags=re.IGNORECASE | re.MULTILINE,
        )
        src_pattern = re.compile(
            rf'^\s*<script\b[^>]*src=["\']\$\{{pageContext\.request\.contextPath\}}{re.escape(url)}["\'][^>]*>\s*</script>\s*\n?',
            flags=re.IGNORECASE | re.MULTILINE,
        )
        updated = href_pattern.sub('', updated)
        updated = src_pattern.sub('', updated)
    return updated

def _inject_common_assets_into_jsp(
    project_root: Path,
    rel_path: str,
    css_web_url: str,
    extra_css_urls: Optional[List[str]] = None,
    js_web_urls: Optional[List[str]] = None,
) -> bool:
    path = project_root / rel_path
    if not path.exists() or path.suffix.lower() != ".jsp":
        return False
    if _is_jsp_layout_partial(rel_path):
        body = _strip_jsp_include_directives(path.read_text(encoding="utf-8"))
        if body != path.read_text(encoding="utf-8"):
            path.write_text(body, encoding="utf-8")
        return False
    raw_body = path.read_text(encoding="utf-8")
    original = raw_body
    body = _strip_shared_jsp_asset_tags(_replace_legacy_common_include_aliases(raw_body))
    if "<c:" in body and 'taglib prefix="c"' not in body and "taglib prefix='c'" not in body:
        if body.lstrip().startswith("<%@ page"):
            body = re.sub(
                r'(^\s*<%@\s*page[^%]*%>\s*)',
                r'\1\n<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>\n',
                body,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            body = '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>\n' + body
    body = body.replace('/WEB-INF/views/_layout.jsp', '/WEB-INF/views/common/header.jsp')
    body = body.replace('/WEB-INF/views/common/_layout.jsp', '/WEB-INF/views/common/header.jsp')
    body = body.replace('<%@ include file="/common/header.jsp" %>', '<%@ include file="/WEB-INF/views/common/header.jsp" %>')
    body = body.replace('<%@ include file="/common/leftNav.jsp" %>', '<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>')
    body = body.replace('<%@ include file="/common/footer.jsp" %>', '<%@ include file="/WEB-INF/views/common/footer.jsp" %>')
    body = body.replace('<%@ include file="/common/navi.jsp" %>', '<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>')
    body = body.replace('<%@ include file="common/header.jsp" %>', '<%@ include file="/WEB-INF/views/common/header.jsp" %>')
    body = body.replace('<%@ include file="common/leftNav.jsp" %>', '<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>')
    body = body.replace('<%@ include file="common/footer.jsp" %>', '<%@ include file="/WEB-INF/views/common/footer.jsp" %>')
    body = body.replace('<%@ include file="common/navi.jsp" %>', '<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>')
    if 'common/header.jsp' not in body:
        if re.search(r'<body[^>]*>', body, flags=re.IGNORECASE):
            body = re.sub(r'(<body[^>]*>)', r'\1\n<%@ include file="/WEB-INF/views/common/header.jsp" %>', body, count=1, flags=re.IGNORECASE)
        elif '</head>' in body:
            body = body.replace('</head>', '</head>\n<body>\n<%@ include file="/WEB-INF/views/common/header.jsp" %>', 1)
        else:
            body = '<%@ include file="/WEB-INF/views/common/header.jsp" %>\n' + body
    if 'common/leftNav.jsp' not in body:
        if 'common/header.jsp' in body:
            body = body.replace('<%@ include file="/WEB-INF/views/common/header.jsp" %>', '<%@ include file="/WEB-INF/views/common/header.jsp" %>\n<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>', 1)
        elif re.search(r'<body[^>]*>', body, flags=re.IGNORECASE):
            body = re.sub(r'(<body[^>]*>)', r'\1\n<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>', body, count=1, flags=re.IGNORECASE)
        else:
            body = '<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>\n' + body
    css_urls: List[str] = []
    if css_web_url:
        css_urls.append(css_web_url)
    for extra in extra_css_urls or []:
        if extra and extra not in css_urls:
            css_urls.append(extra)
    for url in css_urls:
        if _is_shared_jsp_asset_url(url) or url in body:
            continue
        link = f'<link rel="stylesheet" class="autopj-generated" href="${{pageContext.request.contextPath}}{url}" />'
        if '</head>' in body:
            body = body.replace('</head>', f'  {link}\n</head>', 1)
        elif re.search(r'<html[^>]*>', body, flags=re.IGNORECASE):
            body = re.sub(r'(<html[^>]*>)', r'\1\n<head>\n  ' + link + '\n</head>', body, count=1, flags=re.IGNORECASE)
        else:
            body = link + '\n' + body
    for url in js_web_urls or []:
        if not url or _is_shared_jsp_asset_url(url) or url in body:
            continue
        script = f'<script src="${{pageContext.request.contextPath}}{url}"></script>'
        if '</body>' in body:
            body = body.replace('</body>', f'  {script}\n</body>', 1)
        else:
            body = body + '\n' + script + '\n'
    if body != original:
        path.write_text(body, encoding="utf-8")
        return True
    return False
def _schema_for_jsp_view(rel_path: str, schema_map: Dict[str, Any]) -> Optional[Any]:
    norm = (rel_path or '').replace('\\', '/').lower()
    stem = Path(norm).stem.lower()
    folder = Path(norm).parent.name.lower()
    stem_base = re.sub(r'(list|detail|form|calendar|login)$', '', stem)
    candidates = {folder, stem, stem_base}
    for entity, schema in (schema_map or {}).items():
        entity_name = str(getattr(schema, 'entity', entity) or entity).strip().lower()
        entity_var = str(getattr(schema, 'entity_var', '') or '').strip().lower()
        keys = {entity_name, entity_var}
        if any(c and c in keys for c in candidates):
            return schema
    for entity, schema in (schema_map or {}).items():
        entity_name = str(getattr(schema, 'entity', entity) or entity).strip().lower()
        entity_var = str(getattr(schema, 'entity_var', '') or '').strip().lower()
        if (entity_name and f'/{entity_name}/' in norm) or (entity_var and f'/{entity_var}/' in norm):
            return schema
    return None
def _autopj_normalized_name(prop: str = '', col: str = '') -> str:
    return re.sub(r'[^a-z0-9]+', '_', (prop or col or '').lower())
def _autopj_is_yn_field(prop: str = '', col: str = '') -> bool:
    normalized = _autopj_normalized_name(prop, col)
    return normalized.endswith('_yn') or normalized.endswith('yn') or normalized in {'yn', 'use_yn', 'all_day_yn'}
def _autopj_is_date_only_name(prop: str = '', col: str = '') -> bool:
    normalized = _autopj_normalized_name(prop, col)
    if not normalized:
        return False
    if any(token in normalized for token in ('datetime', 'date_time', 'timestamp', 'time_stamp')):
        return False
    if normalized.endswith('_dt') or normalized.endswith('dt'):
        return False
    if normalized.endswith('_time') or normalized == 'time' or (normalized.endswith('time') and 'update_time' not in normalized):
        return False
    return normalized.endswith('_date') or normalized == 'date' or normalized.endswith('date')
def _autopj_is_date_java_type(jt: str) -> bool:
    return (jt or '').strip() in {'Date', 'java.util.Date', 'java.time.LocalDate', 'LocalDate', 'java.time.LocalDateTime', 'LocalDateTime'}
def _autopj_input_type(prop: str, jt: str) -> str:
    low = (prop or '').lower()
    jt_norm = (jt or '').strip()
    if 'password' in low or low.endswith('pw'):
        return 'password'
    if jt_norm in ('Long', 'long', 'Integer', 'int', 'java.math.BigDecimal'):
        return 'number'
    if _autopj_is_date_java_type(jt_norm):
        return 'date' if _autopj_is_date_only_name(prop, prop) else 'datetime-local'
    normalized = _autopj_normalized_name(prop, prop)
    if any(token in normalized for token in ('datetime', 'date_time', 'timestamp', 'time_stamp')) or normalized.endswith('_dt') or normalized.endswith('dt') or normalized.endswith('_time') or normalized == 'time' or (normalized.endswith('time') and 'update_time' not in normalized):
        return 'datetime-local'
    if _autopj_is_date_only_name(prop, prop):
        return 'date'
    return 'text'
def _autopj_is_textarea_field(prop: str) -> bool:
    low = (prop or '').lower()
    return any(token in low for token in ('content', 'description', 'desc', 'remark', 'memo', 'note', 'body'))
def _autopj_field_label(prop: str) -> str:
    prop_key = (prop or '').strip()
    translated = {
        'roomId': '공간 ID',
        'roomName': '공간명 (Room Name)',
        'reservationId': '예약 ID',
        'reserverName': '예약자명',
        'purpose': '사용 목적',
        'startDatetime': '시작 일시',
        'startDate': '시작일',
        'endDatetime': '종료 일시',
        'endDate': '종료일',
        'statusCd': '상태',
        'status': '상태',
        'priorityCd': '우선순위',
        'priority': '우선순위',
        'remark': '비고',
        'memo': '메모',
        'note': '메모',
        'location': '위치 (Location)',
        'capacity': '수용 인원 (Capacity)',
        'useYn': '사용 여부',
        'writerId': '작성자 ID',
        'title': '제목',
        'content': '내용',
        'description': '설명',
        'name': '이름',
    }.get(prop_key)
    if translated:
        return translated
    words = re.findall(r'[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])', prop or '') or [prop or 'Field']
    return ' '.join(w[:1].upper() + w[1:] for w in words if w)
def _autopj_field_hint(prop: str, jt: str) -> str:
    return ''

def _is_hidden_form_helper_field(prop: str, col: str = '') -> bool:
    low_prop = (prop or '').lower()
    low_col = (col or '').lower()
    compact_prop = re.sub(r'[^a-z0-9]+', '', low_prop)
    compact_col = re.sub(r'[^a-z0-9]+', '', low_col)
    if low_prop.startswith('search') or low_col.startswith('search_'):
        return True
    hidden_markers = {'writerid', 'delyn', 'compile', 'compiled', 'build', 'runtime', 'startup', 'endpointsmoke'}
    return compact_prop in hidden_markers or compact_col in hidden_markers or low_col in {'writer_id', 'del_yn', 'endpoint_smoke'}


def _auth_ui_path_tail(path: str) -> str:
    raw = str(path or '').replace('\\', '/')
    lower = raw.lower()
    for marker in ('/web-inf/views/', '/src/pages/', '/src/views/', '/frontend/react/src/', '/frontend/vue/src/'):
        idx = lower.find(marker)
        if idx >= 0:
            return raw[idx:]
    parts = [p for p in raw.split('/') if p]
    return '/'.join(parts[-5:]) if parts else raw


def _auth_ui_scan_tokens(path: str) -> set[str]:
    raw = _auth_ui_path_tail(path)
    raw = re.sub(r'([a-z0-9])([A-Z])', r'\1/\2', raw)
    raw = re.sub(r'[^A-Za-z0-9]+', '/', raw).strip('/').lower()
    compact = raw.replace('/', '')
    tokens = {token for token in raw.split('/') if token}
    if 'login' in compact:
        tokens.add('login')
    if 'signup' in compact:
        tokens.add('signup')
    if 'signin' in compact:
        tokens.add('signin')
    if 'register' in compact:
        tokens.add('register')
    if 'join' in compact:
        tokens.add('join')
    if 'password' in compact or 'passwd' in compact:
        tokens.add('password')
    return tokens


def _is_auth_ui_rel_path(path: str) -> bool:
    norm = _auth_ui_path_tail(path).replace('\\', '/').lower()
    basename = norm.rsplit('/', 1)[-1]
    stem = basename.rsplit('.', 1)[0]
    compact_stem = re.sub(r'[^a-z0-9]+', '', stem)
    collection_suffixes = ('list', 'detail', 'calendar')
    auth_collection_prefixes = ('login', 'signin', 'auth')
    if compact_stem.endswith(collection_suffixes):
        if any(compact_stem == f"{prefix}{suffix}" for prefix in auth_collection_prefixes for suffix in collection_suffixes):
            return True
        return False
    if compact_stem.endswith('form') and compact_stem not in {'signupform', 'registerform', 'joinform', 'loginform', 'signinform'}:
        return False
    auth_exact = {
        'login', 'signin', 'signup', 'register', 'join', 'auth',
        'passwordreset', 'resetpassword', 'changepassword', 'passwordchange',
        'certlogin', 'jwtlogin', 'integratedlogin', 'ssologin',
    }
    if compact_stem in auth_exact or any(compact_stem.endswith(token) for token in auth_exact if len(token) > 4):
        return True
    if '/login/' in norm or '/auth/' in norm:
        return True
    tokens = _auth_ui_scan_tokens(path)
    auth_tokens = {
        'login', 'auth', 'signup', 'signin', 'register', 'join',
        'password', 'passwd', 'reset', 'resetpassword', 'passwordreset',
    }
    if tokens & auth_tokens and not compact_stem.endswith(collection_suffixes):
        return True
    auth_markers = ('/login/', '/auth/', 'sign-up', 'sign-in', 'reset-password', 'resetpassword')
    return any(marker in norm for marker in auth_markers)

def _is_auth_sensitive_field(prop: str, col: str = '') -> bool:
    low_prop = (prop or '').strip().lower()
    low_col = (col or '').strip().lower()
    compact_prop = re.sub(r'[^a-z0-9]+', '', low_prop)
    compact_col = re.sub(r'[^a-z0-9]+', '', low_col)
    exact_markers = {
        'password', 'passwd', 'pwd', 'loginpassword', 'loginpwd', 'userpw', 'passcode',
        'passwordhash', 'passwordsalt', 'secretkey', 'credential', 'credentials', 'pincode', 'pinno',
    }
    substring_markers = ('password', 'passwd', 'passcode', 'loginpw', 'loginpwd', 'userpw', 'secret', 'credential', 'pin')
    return (
        compact_prop in exact_markers
        or compact_col in exact_markers
        or any(token in compact_prop for token in substring_markers)
        or any(token in compact_col for token in substring_markers)
    )


def _schema_has_account_credentials(schema: Any) -> bool:
    fields = list(getattr(schema, 'fields', []) or [])
    field_cols = {str(col or '').strip().lower() for _prop, col, _jt in fields if str(col or '').strip()}
    field_props = {re.sub(r'[^a-z0-9]+', '', str(prop or '').strip().lower()) for prop, _col, _jt in fields if str(prop or '').strip()}
    has_sensitive = any(_is_auth_sensitive_field(prop, col) for prop, col, _jt in fields)
    has_identifier = bool(field_cols & {'login_id', 'user_id', 'member_id', 'account_id', 'email'}) or bool(field_props & {'loginid', 'userid', 'memberid', 'accountid', 'email'})
    return has_sensitive and has_identifier


def _is_collection_ui_rel_path(path: str) -> bool:
    norm = _auth_ui_path_tail(path).replace('\\', '/').lower()
    basename = norm.rsplit('/', 1)[-1]
    stem = basename.rsplit('.', 1)[0]
    compact_stem = re.sub(r'[^a-z0-9]+', '', stem)
    return compact_stem.endswith(('list', 'detail', 'calendar', 'search'))


def _ui_allows_auth_sensitive_fields(rel_path: str, schema: Any) -> bool:
    if _is_auth_ui_rel_path(rel_path):
        return True
    if _is_collection_ui_rel_path(rel_path):
        return False
    if not _schema_has_account_credentials(schema):
        return False
    return allows_auth_sensitive_in_account_form(rel_path, 'login_id login_password user_id user_name role_cd')


def _schema_ui_fields(rel_path: str, schema: Any, *, include_id: bool = False, include_hidden_helpers: bool = False) -> List[Tuple[str, str, str]]:
    fields: List[Tuple[str, str, str]] = []
    auth_ui = _ui_allows_auth_sensitive_fields(rel_path, schema)
    id_prop = str(getattr(schema, 'id_prop', '') or '')
    for prop, col, jt in list(getattr(schema, 'fields', []) or []):
        if not include_id and prop == id_prop:
            continue
        if not _is_valid_java_identifier(prop) or not _is_valid_column_identifier(col):
            continue
        if not include_hidden_helpers and _is_hidden_form_helper_field(prop, col):
            continue
        if not auth_ui and _is_auth_sensitive_field(prop, col):
            continue
        fields.append((prop, col, jt))
    return fields


def _render_form_field_markup(prop: str, jt: str) -> str:
    label = _autopj_field_label(prop)
    hint = _autopj_field_hint(prop, jt)
    hint_markup = f'\n        <span class="autopj-field__hint">{hint}</span>' if hint else ''
    wrapper_class = 'autopj-field autopj-field--full' if (_autopj_is_textarea_field(prop) or (_autopj_is_date_java_type(jt) and not _autopj_is_date_only_name(prop, prop))) else 'autopj-field'
    if _autopj_is_yn_field(prop, prop):
        return f'''      <label class="{wrapper_class}">
        <span class="autopj-field__label">{label}</span>{hint_markup}
        <select name="{prop}" class="form-control">
          <option value="Y" <c:if test="${{item.{prop} == 'Y'}}">selected</c:if>>예</option>
          <option value="N" <c:if test="${{empty item or item.{prop} == 'N' || empty item.{prop}}}">selected</c:if>>아니오</option>
        </select>
      </label>'''
    if jt in ('Boolean', 'boolean'):
        return f'''      <label class="{wrapper_class}">
        <span class="autopj-field__label">{label}</span>{hint_markup}
        <select name="{prop}" class="form-control">
          <option value="false" <c:if test="${{empty item or item.{prop} == false}}">selected</c:if>>아니오</option>
          <option value="true" <c:if test="${{item.{prop} == true}}">selected</c:if>>예</option>
        </select>
      </label>'''
    if _autopj_is_textarea_field(prop):
        return f'''      <label class="{wrapper_class}">
        <span class="autopj-field__label">{label}</span>{hint_markup}
        <textarea name="{prop}" class="form-control"><c:out value='${{item.{prop}}}'/></textarea>
      </label>'''
    input_type = _autopj_input_type(prop, jt)
    extra_attr = ' step="1"' if input_type == 'datetime-local' else ''
    temporal_attr = f' data-autopj-temporal="{input_type}"' if input_type in ('date', 'datetime-local') else ''
    raw_attr = f" data-autopj-raw-value=\"<c:out value='${{item.{prop}}}'/>\"" if input_type in ('date', 'datetime-local') else ''
    return f'''      <label class="{wrapper_class}">
        <span class="autopj-field__label">{label}</span>{hint_markup}
        <input type="{input_type}" name="{prop}" class="form-control" value="<c:out value='${{item.{prop}}}'/>"{extra_attr}{temporal_attr}{raw_attr}/>
      </label>'''
def _rewrite_form_jsp_from_schema(project_root: Path, rel_path: str, schema: Any) -> bool:
    path = project_root / rel_path
    if not path.exists() or not str(rel_path).lower().endswith('form.jsp'):
        return False
    body = path.read_text(encoding='utf-8')
    routes = getattr(schema, 'routes', None) or {}
    action = str(routes.get('save') or routes.get('form') or '/')
    cancel = str(routes.get('calendar') or routes.get('list') or '/')
    delete_route = str(routes.get('delete') or '')
    fields = list(getattr(schema, 'fields', []) or [])
    editable = []
    hidden = []
    id_prop = str(getattr(schema, 'id_prop', '') or '')
    id_type = ''
    numeric_id = False
    allowed_fields = _schema_ui_fields(rel_path, schema, include_id=True, include_hidden_helpers=False)
    allowed_lookup = {(prop, col, jt) for prop, col, jt in allowed_fields}
    for prop, col, jt in fields:
        if prop == id_prop:
            id_type = jt
        col_low = str(col or '').lower()
        if (prop, col, jt) not in allowed_lookup:
            continue
        editable.append((prop, col, jt))
    numeric_id = bool(id_prop and id_type in {'Long', 'long', 'Integer', 'int'} and (str(id_prop).lower().endswith('id') or str(getattr(schema, 'id_column', '') or '').lower().endswith('_id') or str(id_prop).lower() == 'id'))
    if numeric_id:
        editable = [(prop, col, jt) for prop, col, jt in editable if prop != id_prop]
        hidden.append(f"      <input type=\"hidden\" name=\"{id_prop}\" value=\"<c:out value='${{item.{id_prop}}}'/>\"/>")
    elif id_prop:
        hidden.append(f"      <input type=\"hidden\" name=\"_original{id_prop[:1].upper() + id_prop[1:]}\" value=\"<c:out value='${{item.{id_prop}}}'/>\"/>")
    field_parts = []
    for prop, col, jt in editable:
        if prop == id_prop and not numeric_id:
            label = _autopj_field_label(prop)
            hint = _autopj_field_hint(prop, jt)
            hint_markup = f'\n        <span class="autopj-field__hint">{hint}</span>' if hint else ''
            wrapper_class = 'autopj-field autopj-field--full' if (_autopj_is_textarea_field(prop) or (_autopj_is_date_java_type(jt) and not _autopj_is_date_only_name(prop, prop))) else 'autopj-field'
            input_type = _autopj_input_type(prop, jt)
            extra_attr = ' step="1"' if input_type == 'datetime-local' else ''
            temporal_attr = f' data-autopj-temporal="{input_type}"' if input_type in ('date', 'datetime-local') else ''
            raw_attr = f" data-autopj-raw-value=\"<c:out value='${{item.{prop}}}'/>\"" if input_type in ('date', 'datetime-local') else ''
            field_parts.append(f'''      <label class="{wrapper_class}">
        <span class="autopj-field__label">{label}</span>{hint_markup}
        <input type="{input_type}" name="{prop}" class="form-control" value="<c:out value='${{item.{prop}}}'/>"{extra_attr}{temporal_attr}{raw_attr}/>
      </label>
      <script>document.addEventListener('DOMContentLoaded', function(){{ var el = document.querySelector('input[name="{prop}"]'); if (!el) return; var v = (el.value || '').trim(); if (v) {{ el.setAttribute('readonly', 'readonly'); el.setAttribute('data-autopj-id-lock', 'true'); }} else {{ el.removeAttribute('readonly'); }} }});</script>''')
            continue
        field_parts.append(_render_form_field_markup(prop, jt))
    field_markup = '\n'.join(field_parts)
    hidden_block = '\n'.join(hidden)
    delete_form = ''
    if delete_route and id_prop:
        delete_form = f'''      <c:if test="${{not empty item and not empty item.{id_prop}}}">
        <button type="submit" formaction="<c:url value='{delete_route}'/>" formmethod="post" onclick="return confirm('삭제하시겠습니까?');">삭제</button>
      </c:if>'''
    entity = str(getattr(schema, 'entity', '') or 'Item')
    entity_label = _friendly_nav_label(entity)
    page = f'''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{entity_label} 등록/수정</title>
</head>
<body>
<%@ include file="/WEB-INF/views/common/header.jsp" %>
<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>
<section class="page-shell autopj-form-page">
  <div class="autopj-form-hero page-card">
    <div>
      <p class="autopj-eyebrow">{entity_label}</p>
      <h2 class="autopj-form-title">{entity_label} 등록/수정</h2>
    </div>
    <div class="autopj-form-hero__meta">
    </div>
  </div>
  <form class="autopj-form-card form-card" action="<c:url value='{action}'/>" method="post">
{hidden_block}
    <div class="autopj-form-section-header">
      <div>
        <h3 class="autopj-section-title">기본 정보</h3>
      </div>
    </div>
    <div class="autopj-form-grid">
{field_markup}
    </div>
    <div class="autopj-form-actions">
      <button type="submit">저장</button>
{delete_form}
      <a class="btn btn-secondary" href="<c:url value='{cancel}'/>">취소</a>
    </div>
  </form>
</section>
</body>
</html>
'''
    if body == page:
        return False
    path.write_text(_compact_frontend_content(rel_path, page), encoding='utf-8')
    return True
def _rewrite_list_jsp_from_schema(project_root: Path, rel_path: str, schema: Any) -> bool:
    path = project_root / rel_path
    if not path.exists() or not str(rel_path).lower().endswith('list.jsp'):
        return False
    routes = getattr(schema, 'routes', None) or {}
    form = str(routes.get('form') or '')
    detail = str(routes.get('detail') or '')
    delete_route = str(routes.get('delete') or '')
    fields = _schema_ui_fields(rel_path, schema, include_id=False, include_hidden_helpers=False)
    searchable_fields = _schema_ui_fields(rel_path, schema, include_id=True, include_hidden_helpers=False)
    id_prop, _id_col = _effective_schema_id_binding(schema)
    entity = str(getattr(schema, 'entity', '') or 'Item')
    entity_label = _friendly_nav_label(entity)
    searchable_fields: List[Tuple[str, str, str]] = list(searchable_fields)
    visible_fields: List[Tuple[str, str, str]] = list(fields)
    visible_fields = visible_fields[:5]
    header_cells = ''.join(f'<th>{_autopj_field_label(prop)}</th>' for prop, _col, _jt in visible_fields)
    body_cells_parts: List[str] = []
    for prop, col, jt in visible_fields:
        if _autopj_is_date_java_type(jt) and not _autopj_is_date_only_name(prop, col):
            value_markup = f'<span data-autopj-display="datetime"><c:out value="${{row.{prop}}}"/></span>'
        elif _autopj_is_date_java_type(jt) and _autopj_is_date_only_name(prop, col):
            value_markup = f'<span data-autopj-display="date"><c:out value="${{row.{prop}}}"/></span>'
        else:
            value_markup = f'<c:out value="${{row.{prop}}}"/>'
        body_cells_parts.append(f'                  <td>{value_markup}</td>')
    body_cells = '\n'.join(body_cells_parts) if body_cells_parts else '                  <td>-</td>'
    create_link = f"<a class=\"btn\" href=\"<c:url value='{form}'/>\">등록</a>" if form else ""
    id_link = f'<c:out value="${{row.{id_prop}}}"/>'
    if detail:
        id_link = f"<a href=\"<c:url value='{detail}'/>?{id_prop}=${{row.{id_prop}}}\"><c:out value=\"${{row.{id_prop}}}\"/></a>"
    actions: List[str] = []
    if detail:
        actions.append(f"<a class=\"btn btn-light\" href=\"<c:url value='{detail}'/>?{id_prop}=${{row.{id_prop}}}\">상세</a>")
    if form:
        actions.append(f"<a class=\"btn btn-light\" href=\"<c:url value='{form}'/>?{id_prop}=${{row.{id_prop}}}\">수정</a>")
    if delete_route:
        actions.append(f'''<form action="<c:url value='{delete_route}'/>" method="post" style="display:inline-flex;margin:0;">
                      <input type="hidden" name="{id_prop}" value="${{row.{id_prop}}}"/>
                      <button type="submit" onclick="return confirm('삭제하시겠습니까?');">삭제</button>
                    </form>''')
    search_fields_markup: List[str] = []
    for prop, col, jt in searchable_fields:
        label = _autopj_field_label(prop)
        temporal_type = _autopj_input_type(prop, jt)
        if _autopj_is_yn_field(prop, col):
            control = (
                f'<select name="{prop}">'
                f'<option value="">전체</option>'
                f'<option value="Y">Y</option>'
                f'<option value="N">N</option>'
                f'</select>'
            )
        elif temporal_type in ('date', 'datetime-local'):
            control = (
                f'<input type="{temporal_type}" name="{prop}From" value="${{param.{prop}From}}"/>'
                f'<span class="range-sep">~</span>'
                f'<input type="{temporal_type}" name="{prop}To" value="${{param.{prop}To}}"/>'
            )
        else:
            control = f'<input type="text" name="{prop}" value="${{param.{prop}}}"/>'
        search_fields_markup.append(
            f'        <div class="form-row" data-search-field="{prop}">\n'
            f'          <label for="{prop}">{label}</label>\n'
            f'          {control}\n'
            '        </div>'
        )
    search_panel = '\n'.join(search_fields_markup)
    actions_block = '\n                    '.join(actions)
    page = f'''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{entity_label} 목록</title>
</head>
<body>
<%@ include file="/WEB-INF/views/common/header.jsp" %>
<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>
<section class="page-shell">
  <div class="page-card autopj-form-hero">
    <div>
      <p class="autopj-eyebrow">{entity_label}</p>
      <h2 class="autopj-form-title">{entity_label} 목록</h2>
    </div>
    <div class="action-bar">{create_link}</div>
  </div>
  <div class="page-card" style="padding:22px 24px;">
    <form id="searchForm" class="autopj-search-form" method="get" style="margin-bottom:18px;">
      <div class="autopj-form-grid">
      {search_panel}
      </div>
      <div class="autopj-form-actions">
        <button type="submit">검색</button>
      </div>
    </form>
    <c:choose>
      <c:when test="${{not empty list}}">
        <div class="table-wrap autopj-record-grid">
          <table class="data-table autopj-data-table">
            <thead>
              <tr>
                <th>ID</th>
                {header_cells}
                <th>작업</th>
              </tr>
            </thead>
            <tbody>
              <c:forEach var="row" items="${{list}}">
                <tr>
                  <td>{id_link}</td>
{body_cells}
                  <td>
                    <div class="action-bar">
                    {actions_block}
                    </div>
                  </td>
                </tr>
              </c:forEach>
            </tbody>
          </table>
        </div>
      </c:when>
      <c:otherwise>
        <div class="empty-state">데이터가 없습니다.</div>
      </c:otherwise>
    </c:choose>
  </div>
</section>
</body>
</html>
'''
    original = path.read_text(encoding='utf-8')
    if original == page:
        return False
    path.write_text(_compact_frontend_content(rel_path, page), encoding='utf-8')
    return True
def _rewrite_detail_jsp_from_schema(project_root: Path, rel_path: str, schema: Any) -> bool:
    path = project_root / rel_path
    if not path.exists() or path.suffix.lower() != '.jsp':
        return False
    fields = _schema_ui_fields(rel_path, schema, include_id=False, include_hidden_helpers=False)
    rows: List[str] = []
    for prop, col, jt in fields:
        label = _autopj_field_label(prop)
        if jt in ('Boolean', 'boolean'):
            value_markup = f'<c:choose><c:when test="${{item.{prop}}}">예</c:when><c:otherwise>아니오</c:otherwise></c:choose>'
        elif _autopj_is_date_java_type(jt) and not _autopj_is_date_only_name(prop, col):
            value_markup = f'<span data-autopj-display="datetime"><c:out value="${{item.{prop}}}"/></span>'
        elif _autopj_is_date_java_type(jt) and _autopj_is_date_only_name(prop, col):
            value_markup = f'<span data-autopj-display="date"><c:out value="${{item.{prop}}}"/></span>'
        else:
            value_markup = f'<c:out value="${{item.{prop}}}"/>'
        rows.append(f'''      <div class="autopj-field"><span class="autopj-field__label">{label}</span><div class="autopj-field__value">{value_markup}</div></div>''')
    details_block = '\n'.join(rows)
    back = str((getattr(schema, 'routes', {}) or {}).get('calendar') or (getattr(schema, 'routes', {}) or {}).get('list') or '/')
    form = str((getattr(schema, 'routes', {}) or {}).get('form') or '')
    delete_route = str((getattr(schema, 'routes', {}) or {}).get('delete') or '')
    id_prop, _id_col = _effective_schema_id_binding(schema)
    edit_link = ''
    if form:
        edit_link = f'''        <a class="btn" href="<c:url value='{form}'/>?{id_prop}=${{item.{id_prop}}}">수정</a>'''
    delete_form = ''
    if delete_route:
        delete_form = f'''        <form action="<c:url value='{delete_route}'/>" method="post" style="margin:0;display:inline-flex;">
          <input type="hidden" name="{id_prop}" value="${{item.{id_prop}}}"/>
          <button type="submit" onclick="return confirm('삭제하시겠습니까?');">삭제</button>
        </form>'''
    entity = str(getattr(schema, 'entity', '') or 'Item')
    entity_label = _friendly_nav_label(entity)
    page = f'''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{entity_label} 상세</title>
</head>
<body>
<%@ include file="/WEB-INF/views/common/header.jsp" %>
<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>
<section class="page-shell master-detail-shell autopj-detail-page">
  <div class="autopj-form-hero page-card">
    <div>
      <p class="autopj-eyebrow">{entity_label}</p>
      <h2 class="autopj-form-title">{entity_label} 상세</h2>
    </div>
    <div class="autopj-form-hero__meta">
    </div>
  </div>
  <c:if test="${{empty item}}">
    <div class="empty-state">데이터가 없습니다.</div>
  </c:if>
  <c:if test="${{not empty item}}">
    <div class="detail-card autopj-form-card">
      <div class="autopj-form-section-header">
        <div>
          <h3 class="autopj-section-title">상세 정보</h3>
          </div>
      </div>
      <div class="autopj-form-grid">
{details_block}
      </div>
      <div class="autopj-form-actions">
{edit_link}
{delete_form}
        <a class="btn btn-secondary" href="<c:url value='{back}'/>">목록으로</a>
      </div>
    </div>
  </c:if>
</section>
</body>
</html>
'''
    original = path.read_text(encoding='utf-8')
    if original == page:
        return False
    path.write_text(_compact_frontend_content(rel_path, page), encoding='utf-8')
    return True
def _coerce_temporal_inputs_in_jsp(project_root: Path, rel_path: str, schema: Any) -> bool:
    path = project_root / rel_path
    if not path.exists() or path.suffix.lower() != '.jsp':
        return False
    body = path.read_text(encoding='utf-8')
    original = body
    for prop, _col, jt in list(getattr(schema, 'fields', []) or []):
        desired = _autopj_input_type(prop, jt)
        if desired not in {'date', 'datetime-local'}:
            continue
        pattern = re.compile(r'(<input\b[^>]*\bname=["\']' + re.escape(prop) + r'["\'][^>]*)(>)', re.IGNORECASE)
        def repl(match):
            tag = match.group(1)
            closing = match.group(2)
            tag = re.sub(r'\s+type=["\'][^"\']*["\']', '', tag, flags=re.IGNORECASE)
            if desired == 'datetime-local' and ' step=' not in tag:
                tag += ' step="1"'
            return f'{tag} type="{desired}"{closing}'
        body = pattern.sub(repl, body)
    if body != original:
        path.write_text(body, encoding='utf-8')
        return True
    return False
def _patch_generated_jsp_assets(
    project_root: Path,
    generated_rel_paths: List[str],
    preferred_entity: str,
    schema_map: Dict[str, Any],
    cfg: Optional[ProjectConfig] = None,
) -> Dict[str, Any]:
    root = Path(project_root)
    css_rel = _ensure_jsp_common_css(root)
    css_jsp_rel = _ensure_jsp_common_css_partial(root)
    common_js_rel = _ensure_jsp_common_js(root)
    schedule_css_rel = _ensure_jsp_schedule_css(root)
    schedule_js_rel = _ensure_jsp_schedule_js(root)
    nav_override = _discover_navigation_items(root, preferred_entity=preferred_entity)
    fallback_main_route = _discover_fallback_main_route(root)
    schema_main_route = _pick_main_route_from_schema_map(schema_map)
    preferred_main_route = fallback_main_route if fallback_main_route not in {'', '/'} else (schema_main_route or '/')
    main_route = str((nav_override or {}).get('main_url') or '')
    if not main_route or '{' in main_route or '}' in main_route or (preferred_main_route and preferred_main_route != '/' and main_route != preferred_main_route):
        main_route = preferred_main_route or '/'
    if (nav_override or {}).get('main_url') != main_route and nav_override is not None:
        nav_override = dict(nav_override)
        nav_override['main_url'] = main_route
    index_rel = _ensure_index_redirect(root, main_route)
    static_index_rel = _ensure_static_index_html(root, main_route)
    project_title = getattr(cfg, "project_name", None) if cfg is not None else None
    header_rel = _ensure_jsp_header_file(root, schema_map=schema_map, preferred_entity=preferred_entity, project_title=project_title, nav_override=nav_override)
    leftnav_rel = _ensure_jsp_leftnav_file(root, schema_map=schema_map, preferred_entity=preferred_entity, nav_override=nav_override)
    taglibs_rel = _ensure_jsp_taglibs_file(root)
    include_rel = _ensure_jsp_include_file(root)
    domain_header_alias_rels = _ensure_jsp_domain_header_alias_files(root)
    layout_rel = _ensure_jsp_layout_file(root)
    common_layout_rel = _ensure_jsp_common_layout_file(root)
    css_web_url = "/css/common.css"
    schedule_css_web_url = "/css/schedule.css"
    common_js_web_url = "/js/common.js"
    schedule_js_web_url = "/js/schedule.js"
    candidate_rel_paths = list(generated_rel_paths or [])
    discovered_rel_paths = [str(p.relative_to(root)).replace("\\", "/") for p in root.glob('src/main/webapp/WEB-INF/views/**/*.jsp')]
    if discovered_rel_paths:
        seen_rel_paths = {str(path or '').replace("\\", "/") for path in candidate_rel_paths}
        for discovered in discovered_rel_paths:
            if discovered not in seen_rel_paths:
                candidate_rel_paths.append(discovered)
                seen_rel_paths.add(discovered)
    patched_views: List[str] = []
    normalized_views: List[str] = []
    for rel in candidate_rel_paths:
        norm = (rel or "").replace("\\", "/")
        if not norm.lower().endswith('.jsp'):
            continue
        if not norm.lower().startswith('src/main/webapp/web-inf/views/'):
            continue
        if _is_jsp_layout_partial(norm):
            continue
        schema = _schema_for_jsp_view(norm, schema_map)
        extra_css_urls: List[str] = []
        js_web_urls: List[str] = [common_js_web_url]
        if schema is not None and norm.lower().endswith('calendar.jsp') and _schema_feature_family(schema) == 'calendar':
            if _normalize_calendar_jsp(root, norm, schema):
                normalized_views.append(norm)
            extra_css_urls.append(schedule_css_web_url)
            js_web_urls.append(schedule_js_web_url)
        rewritten_form = False
        if schema is not None and norm.lower().endswith('list.jsp'):
            if _rewrite_list_jsp_from_schema(root, norm, schema):
                normalized_views.append(norm)
        if schema is not None and norm.lower().endswith('form.jsp'):
            if _rewrite_form_jsp_from_schema(root, norm, schema):
                normalized_views.append(norm)
                rewritten_form = True
        if schema is not None and norm.lower().endswith('detail.jsp'):
            if _rewrite_detail_jsp_from_schema(root, norm, schema):
                normalized_views.append(norm)
        if schema is not None and not rewritten_form:
            _coerce_temporal_inputs_in_jsp(root, norm, schema)
        if _inject_common_assets_into_jsp(root, norm, css_web_url, extra_css_urls=extra_css_urls, js_web_urls=js_web_urls):
            patched_views.append(norm)
    return {
        "common_css": css_rel,
        "common_js": common_js_rel,
        "schedule_css": schedule_css_rel,
        "schedule_js": schedule_js_rel,
        "index_jsp": index_rel,
        "static_index_html": static_index_rel,
        "header_jsp": header_rel,
        "leftnav_jsp": leftnav_rel,
        "taglibs_jsp": taglibs_rel,
        "include_jsp": include_rel,
        "domain_header_aliases": domain_header_alias_rels,
        "layout_jsp": layout_rel,
        "css_web_url": css_web_url,
        "patched_views": patched_views,
        "normalized_views": normalized_views,
        "preferred_entity": preferred_entity,
        "main_route": main_route,
        "nav_override": nav_override or {},
        "families": {key: _schema_feature_family(value) for key, value in (schema_map or {}).items()},
    }
def apply_file_ops_with_execution_core(
    file_ops: List[Dict[str, Any]],
    project_root: Path,
    cfg: ProjectConfig,
    overwrite: bool = True,
) -> Dict[str, Any]:
    """Apply file_ops into an existing Eclipse eGovFrame project root, then patch for MySQL+JSP runtime."""
    report: Dict[str, Any] = {"created": [], "overwritten": [], "skipped": [], "errors": [], "patched": {}}
    # Detect base package. If the existing boot package still uses 'example',
    # replace that placeholder with the UI project name (or project root name).
    base_package = _resolve_base_package(project_root, cfg)
    patch_boot_application(project_root, base_package)
    ordered_file_ops = _sort_file_ops_for_dependency_order(file_ops)
    report["patched"]["file_apply_order"] = [
        (item.get("path") or "").replace("\\", "/") for item in ordered_file_ops[:50]
    ]
    preferred_entity = _preferred_crud_entity(ordered_file_ops)
    schema_map = _augment_schema_map_with_auth(_schema_map_from_file_ops(ordered_file_ops, cfg.effective_extra_requirements() if hasattr(cfg, "effective_extra_requirements") else cfg.extra_requirements), ordered_file_ops, cfg)
    report["patched"]["schema_tables"] = {entity: getattr(schema, "table", "") for entity, schema in (schema_map or {}).items() if schema is not None}
    # Patch application.properties (JSP view resolver + mybatis locations etc)
    try:
        props_path = patch_application_properties(project_root, base_package, cfg.frontend_key)
        report["patched"]["application.properties"] = str(props_path)
    except Exception as e:
        report["errors"].append({"path": "application.properties", "reason": f"patch_failed: {e}"})
    # Ensure Maven wrapper exists so generated projects build without a global mvn install
    try:
        wrapper_paths = ensure_maven_wrapper(project_root)
        report["patched"]["maven_wrapper"] = [str(p) for p in wrapper_paths]
    except Exception as e:
        report["errors"].append({"path": "mvnw", "reason": f"maven_wrapper_failed: {e}"})
    # Patch datasource properties from UI cfg (MySQL-only)
    try:
        if (cfg.database_key or "").strip().lower() == "mysql":
            db = _mysql_config_from_cfg(cfg)
            if patch_datasource_properties and db.get("host") and db.get("user") and db.get("database"):
                patch_datasource_properties(project_root, db)
                report["patched"]["datasource"] = "ok"
            else:
                report["patched"]["datasource"] = "skipped(no db creds)"
        else:
            report["patched"]["datasource"] = f"skipped(frontend={cfg.frontend_key}, db={cfg.database_key})"
    except Exception as e:
        report["errors"].append({"path": "application.properties", "reason": f"datasource_patch_failed: {e}"})
    # Write schema.sql so Spring Boot creates local DB tables automatically on startup
    try:
        schema_path = _write_schema_sql_from_schemas(project_root, schema_map)
        report["patched"]["schema.sql"] = str(schema_path) if schema_path else "skipped(no inferred schema)"
    except Exception as e:
        report["errors"].append({"path": "schema.sql", "reason": f"schema_write_failed: {e}"})
    # Login-only SQL bootstrap: keep login table creation and seed insert explicit and isolated
    try:
        auth_sql_artifacts = _write_auth_sql_artifacts(project_root, schema_map, base_package)
        if auth_sql_artifacts:
            report["patched"].update(auth_sql_artifacts)
    except Exception as e:
        report["errors"].append({"path": "login-schema.sql", "reason": f"auth_sql_write_failed: {e}"})
    # Ensure SQL bootstrap initializer exists for non-auth projects too
    try:
        if report["patched"].get("LoginDatabaseInitializer"):
            report["patched"]["DatabaseInitializer"] = "skipped(use LoginDatabaseInitializer)"
        else:
            init_path = write_database_initializer(project_root, base_package)
            report["patched"]["DatabaseInitializer"] = str(init_path)
    except Exception as e:
        report["errors"].append({"path": "DatabaseInitializer.java", "reason": f"write_failed: {e}"})
    # Ensure MyBatisConfig exists (MapperScan + SqlSessionFactory/Template)
    try:
        p = _ensure_mybatis_config(project_root, base_package)
        report["patched"]["MyBatisConfig"] = str(p)
    except Exception as e:
        report["errors"].append({"path": "MyBatisConfig.java", "reason": f"write_failed: {e}"})
    # Ensure standalone JSPs are reachable only through controller routes.
    try:
        standalone_views: List[str] = []
        for item in file_ops or []:
            raw_path = (item.get("path") or "").replace('\\', '/')
            if not raw_path.lower().startswith("src/main/webapp/web-inf/views/"):
                continue
            name = Path(raw_path).name
            if name.lower() == "index.jsp":
                continue
            if _canonical_crud_logical_path(name):
                continue
            if name.lower().endswith('.jsp'):
                standalone_views.append(Path(name).stem)
        if standalone_views:
            vc = _write_view_controller(project_root, base_package)
            report["patched"]["ViewController"] = str(vc)
        else:
            report["patched"]["ViewController"] = "skipped(no standalone views)"
    except Exception as e:
        report["errors"].append({"path": "ViewController.java", "reason": f"write_failed: {e}"})
    frontend_mode = (cfg.frontend_key or "").strip().lower()
    if frontend_mode == "react":
        try:
            report["patched"]["react_runtime_baseline"] = _ensure_react_runtime_baseline(project_root, overwrite=False)
        except Exception as e:
            report["errors"].append({"path": "frontend/react", "reason": f"react_runtime_baseline_failed: {e}"})
    if frontend_mode == "vue":
        try:
            report["patched"]["vue_runtime_baseline"] = _ensure_vue_runtime_baseline(project_root, preferred_entity, schema_map, overwrite=False)
        except Exception as e:
            report["errors"].append({"path": "frontend/vue", "reason": f"vue_runtime_baseline_failed: {e}"})
    # Patch pom.xml for mysql driver + JSP deps if helpers exist
    try:
        if (cfg.database_key or "").strip().lower() == "mysql" and patch_pom_mysql_driver:
            changed = patch_pom_mysql_driver(project_root)
            report["patched"]["pom_mysql_driver"] = bool(changed)
        else:
            report["patched"]["pom_mysql_driver"] = False
        if (cfg.frontend_key or "").strip().lower() == "jsp" and patch_pom_jsp_support:
            changed2 = patch_pom_jsp_support(project_root)
            report["patched"]["pom_jsp_support"] = bool(changed2)
        else:
            report["patched"]["pom_jsp_support"] = False
    except Exception as e:
        report["errors"].append({"path": "pom.xml", "reason": f"pom_patch_failed: {e}"})
    # Apply file ops
    auth_owner = _auth_owner_entity(schema_map)
    for item in ordered_file_ops:
        raw_path = item.get("path", "")
        raw_content = item.get("content", "") or ""
        extra_hint = " ".join(str(x or "") for x in (item.get("purpose", ""), (cfg.effective_extra_requirements() if hasattr(cfg, 'effective_extra_requirements') else cfg.extra_requirements)))
        is_auth_item = _looks_like_auth_artifact(item)
        effective_entity = auth_owner if (is_auth_item and auth_owner) else preferred_entity
        canonical_raw_path = _canonicalize_auth_raw_path(raw_path, schema_map) if is_auth_item else raw_path
        if is_auth_item and not canonical_raw_path:
            report["skipped"].append(raw_path)
            continue
        path = _normalize_out_path(canonical_raw_path, base_package, effective_entity, raw_content, extra_hint)
        path = _map_frontend_rel_path(path, cfg.frontend_key)
        content = _repair_content_by_path(path, raw_content, base_package, effective_entity, schema_map)
        if not path or ".." in path or path.startswith("/") or ":" in path:
            report["errors"].append({"path": path, "reason": "invalid_path"})
            continue
        if (cfg.frontend_key or "").strip().lower() == "react" and _should_protect_react_runtime_file(path, content):
            report["skipped"].append(path)
            report["errors"].append({"path": path, "reason": "invalid_react_runtime_content_kept_baseline"})
            continue
        if (cfg.frontend_key or "").strip().lower() == "vue" and _should_protect_vue_runtime_file(path, content):
            report["skipped"].append(path)
            report["errors"].append({"path": path, "reason": "invalid_vue_runtime_content_kept_baseline"})
            continue
        try:
            status = _write_file(project_root, path, content, overwrite)
            report[status].append(path)
        except Exception as e:
            report["errors"].append({"path": path, "reason": str(e)})
    if (cfg.frontend_key or "").strip().lower() == "react":
        try:
            report["patched"]["react_backend_cleanup"] = cleanup_leaked_backend_artifacts(project_root, base_package, list(schema_map.keys()))
        except Exception as e:
            report["errors"].append({"path": "src/main/java", "reason": f"react_backend_cleanup_failed: {e}"})
        try:
            report["patched"]["react_backend_builtin"] = ensure_react_backend_crud(project_root, base_package, schema_map)
        except Exception as e:
            report["errors"].append({"path": "src/main/java", "reason": f"react_backend_builtin_failed: {e}"})
        try:
            report["patched"]["react_frontend_builtin"] = ensure_react_frontend_crud(project_root, schema_map)
        except Exception as e:
            report["errors"].append({"path": "frontend/react", "reason": f"react_frontend_builtin_failed: {e}"})
    if (cfg.frontend_key or "").strip().lower() == "vue":
        try:
            report["patched"]["vue_frontend_builtin"] = ensure_vue_frontend_crud(project_root, schema_map)
        except Exception as e:
            report["errors"].append({"path": "frontend/vue", "reason": f"vue_frontend_builtin_failed: {e}"})
    try:
        purged_auth = _purge_misplaced_auth_artifacts(project_root, base_package, schema_map)
        report["patched"]["purged_auth_artifacts"] = purged_auth
        if purged_auth:
            purged_set = {str(p or '').replace('\\', '/') for p in purged_auth if str(p or '').strip()}
            for bucket in ('created', 'overwritten', 'skipped'):
                report[bucket] = [rel for rel in (report.get(bucket) or []) if str(rel or '').replace('\\', '/') not in purged_set]
        auth_changed = _ensure_auth_bundle_files(project_root, base_package, schema_map, cfg)
        report["patched"]["auth_bundle_files"] = auth_changed
        for rel in auth_changed:
            if rel not in report["created"] and rel not in report["overwritten"]:
                report["created"].append(rel)
    except Exception as e:
        report["errors"].append({"path": "src/main/java", "reason": f"auth_bundle_ensure_failed: {e}"})
    if (cfg.frontend_key or "").strip().lower() == "jsp":
        try:
            generated_rel_paths = []
            for key in ("created", "overwritten"):
                for rel in report.get(key) or []:
                    if rel not in generated_rel_paths:
                        generated_rel_paths.append(rel)
            report["patched"]["jsp_design_assets"] = _patch_generated_jsp_assets(project_root, generated_rel_paths, preferred_entity, schema_map, cfg)
        except Exception as e:
            report["errors"].append({"path": "src/main/webapp", "reason": f"jsp_design_assets_failed: {e}"})
    try:
        final_boot_path = patch_boot_application(project_root, base_package)
        try:
            report["patched"]["boot_application_final"] = str(final_boot_path.relative_to(project_root)).replace("\\", "/")
        except Exception:
            report["patched"]["boot_application_final"] = str(final_boot_path)
    except Exception as e:
        report["errors"].append({"path": "src/main/java/EgovBootApplication.java", "reason": f"boot_application_finalize_failed: {e}"})
    try:
        changed_imports = fix_project_java_imports(project_root)
        report["patched"]["java_import_fixer"] = {
            "changed_count": len(changed_imports),
            "files": [str(p.relative_to(project_root)).replace("\\", "/") for p in changed_imports[:100]],
        }
    except Exception as e:
        report["errors"].append({"path": "src/main/java", "reason": f"java_import_fixer_failed: {e}"})
    # Apply DDL to MySQL if possible (MySQL-only workflow)
    try:
        ddls = [ddl(s) for s in schema_map.values() if s is not None]
        if (cfg.database_key or "").strip().lower() == "mysql" and ddls:
            db = _mysql_config_from_cfg(cfg)
            report["patched"]["db_apply"] = _apply_mysql_ddl(db, ddls, project_root=project_root)
        elif ddls:
            report["patched"]["db_apply"] = f"skipped(db={cfg.database_key})"
        else:
            report["patched"]["db_apply"] = "skipped(no inferred schema)"
    except Exception as e:
        report["patched"]["db_apply"] = f"failed: {e}"
    return report
