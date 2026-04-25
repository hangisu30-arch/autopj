from __future__ import annotations

import re
from pathlib import Path

from app.io.execution_core_apply import _REACT_RUNTIME_BASELINE, _VUE_RUNTIME_BASELINE


def _normalize(path: str) -> str:
    return (path or "").replace("\\", "/").strip()


def _domain_and_entity(spec: str, project_name: str = "") -> tuple[str, str]:
    text = spec or ""
    tokens = re.findall(r"\b([A-Z][A-Za-z0-9_]*)\b", text)
    entity = tokens[0] if tokens else "Member"
    domain = entity[:1].lower() + entity[1:]
    if project_name and entity == "Member":
        # keep default generic if nothing stronger is present
        pass
    return domain, entity


def _route_baseline(frontend_key: str, spec: str, project_name: str = "") -> dict[str, str]:
    fk = (frontend_key or "").strip().lower()
    domain, entity = _domain_and_entity(spec, project_name)
    if fk == "vue":
        return {
            "src/constants/routes.js": f'''const ROUTES = {{
  MAIN: "/",
  {entity.upper()}_LIST: "/{domain}/list",
  {entity.upper()}_CREATE: "/{domain}/create",
  {entity.upper()}_DETAIL: ({domain}Id = ":{domain}Id") => `/{domain}/detail/${{{domain}Id}}`,
  {entity.upper()}_EDIT: ({domain}Id = ":{domain}Id") => `/{domain}/edit/${{{domain}Id}}`,
}};

export default ROUTES;
''',
            "src/router/index.js": f'''import {{ createRouter, createWebHistory }} from "vue-router";
import ROUTES from "../constants/routes";
import {entity}List from "@/views/{domain}/{entity}List.vue";
import {entity}Detail from "@/views/{domain}/{entity}Detail.vue";
import {entity}Form from "@/views/{domain}/{entity}Form.vue";

const routes = [
  {{ path: ROUTES.MAIN, redirect: ROUTES.{entity.upper()}_LIST }},
  {{ path: ROUTES.{entity.upper()}_LIST, name: "{entity}List", component: {entity}List }},
  {{ path: ROUTES.{entity.upper()}_CREATE, name: "{entity}Create", component: {entity}Form }},
  {{ path: ROUTES.{entity.upper()}_DETAIL(), name: "{entity}Detail", component: {entity}Detail, props: true }},
  {{ path: ROUTES.{entity.upper()}_EDIT(), name: "{entity}Edit", component: {entity}Form, props: true }},
];

export default createRouter({{
  history: createWebHistory(),
  routes,
}});
''',
            "src/App.vue": '<template>\n  <router-view />\n</template>\n',
        }
    if fk == "react":
        return {}
    return {}


def build_frontend_runtime_fallback(path: str, frontend_key: str, spec: str = "", project_name: str = "") -> str:
    norm = _normalize(path)
    fk = (frontend_key or "").strip().lower()
    if fk == "vue":
        rel = norm
        if rel.startswith("frontend/vue/"):
            rel = rel[len("frontend/vue/"):]
        custom = _route_baseline("vue", spec, project_name)
        if rel in custom:
            return custom[rel]
        return _VUE_RUNTIME_BASELINE.get(rel, "")
    if fk == "react":
        rel = norm
        if rel.startswith("frontend/react/"):
            rel = rel[len("frontend/react/"):]
        return _REACT_RUNTIME_BASELINE.get(rel, "")
    return ""
