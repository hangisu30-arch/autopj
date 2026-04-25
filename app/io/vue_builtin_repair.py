from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


def vue_entity_var(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "", name or "").strip() or "item"
    if cleaned.isupper():
        return cleaned.lower()
    m = re.match(r"^([A-Z]{2,})([A-Z][a-z].*)$", cleaned)
    if m:
        return m.group(1).lower() + m.group(2)
    return cleaned[:1].lower() + cleaned[1:]


def _route_key(domain: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", domain or "").upper().strip("_") or "ITEM"


def _label(prop: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", prop or "").strip()
    if not cleaned:
        return "Field"
    parts = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", cleaned) or [cleaned]
    return " ".join(p[:1].upper() + p[1:] for p in parts if p)


def _write_text_if_changed(target: Path, content: str) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        existing = target.read_text(encoding="utf-8", errors="ignore")
        if existing == content:
            return "kept"
    target.write_text(content, encoding="utf-8")
    return "written"


def _build_routes(entities: List[Tuple[str, Any]]) -> Tuple[str, str]:
    imports = [
        'import { createRouter, createWebHistory } from "vue-router";',
        'import ROUTES from "@/constants/routes";',
    ]
    first_key = _route_key(vue_entity_var(entities[0][0]))
    route_lines = [f"  {{ path: ROUTES.MAIN, redirect: ROUTES.{first_key}_LIST }},"]
    const_lines = ['  MAIN: "/",']

    for entity, schema in entities:
        ev = vue_entity_var(entity)
        key = _route_key(ev)
        id_prop = getattr(schema, "id_prop", "id")
        imports.extend([
            f'import {entity}List from "@/views/{ev}/{entity}List.vue";',
            f'import {entity}Detail from "@/views/{ev}/{entity}Detail.vue";',
            f'import {entity}Form from "@/views/{ev}/{entity}Form.vue";',
        ])
        const_lines.extend([
            f'  {key}_LIST: "/{ev}/list",',
            f'  {key}_CREATE: "/{ev}/create",',
            f'  {key}_DETAIL: ({id_prop} = ":{id_prop}") => `/{ev}/detail/${{{id_prop}}}`,',
            f'  {key}_EDIT: ({id_prop} = ":{id_prop}") => `/{ev}/edit/${{{id_prop}}}`,',
        ])
        route_lines.extend([
            f'  {{ path: ROUTES.{key}_LIST, name: "{ev}-list", component: {entity}List }},',
            f'  {{ path: "/{ev}/detail/:{id_prop}", name: "{ev}-detail", component: {entity}Detail, props: true }},',
            f'  {{ path: ROUTES.{key}_CREATE, name: "{ev}-create", component: {entity}Form }},',
            f'  {{ path: "/{ev}/edit/:{id_prop}", name: "{ev}-edit", component: {entity}Form, props: true }},',
        ])

    unique_imports = []
    seen = set()
    for line in imports:
        if line not in seen:
            seen.add(line)
            unique_imports.append(line)

    router = "\n".join(unique_imports) + "\n\nconst routes = [\n" + "\n".join(route_lines) + "\n];\n\nconst router = createRouter({\n  history: createWebHistory(),\n  routes,\n});\n\nexport default router;\n"
    constants = "const ROUTES = {\n" + "\n".join(const_lines) + "\n};\n\nexport default ROUTES;\n"
    return router, constants


def _build_api(entity: str, schema: Any) -> str:
    ev = vue_entity_var(entity)
    id_prop = getattr(schema, "id_prop", "id")
    return f'''import {{ apiRequest }} from "@/api/client";

const API_BASE = "/api/{ev}";

export function list{entity}() {{
  return apiRequest(API_BASE);
}}

export function get{entity}({id_prop}) {{
  return apiRequest(`${{API_BASE}}/${{encodeURIComponent({id_prop})}}`);
}}

export function create{entity}(payload) {{
  return apiRequest(API_BASE, {{
    method: "POST",
    body: JSON.stringify(payload),
  }});
}}

export function update{entity}({id_prop}, payload) {{
  return apiRequest(`${{API_BASE}}/${{encodeURIComponent({id_prop})}}`, {{
    method: "PUT",
    body: JSON.stringify(payload),
  }});
}}

export function delete{entity}({id_prop}) {{
  return apiRequest(`${{API_BASE}}/${{encodeURIComponent({id_prop})}}`, {{
    method: "DELETE",
  }});
}}
'''


def _build_list_view(entity: str, schema: Any) -> str:
    ev = vue_entity_var(entity)
    key = _route_key(ev)
    id_prop = getattr(schema, "id_prop", "id")
    fields = list(getattr(schema, "fields", []) or [])
    visible = fields[: min(4, len(fields))] or [(id_prop, getattr(schema, "id_column", id_prop), "String")]
    headers = "\n".join([f"            <th>{_label(prop)}</th>" for prop, _, _ in visible])
    cells = "\n".join([f"            <td>{{{{ item.{prop} }}}}</td>" for prop, _, _ in visible])
    return f'''<template>
  <div class="page-shell">
    <div class="page-card">
      <div class="page-header">
        <h1>{entity}</h1>
        <button @click="goCreate">추가</button>
      </div>
      <p v-if="loading">로딩중</p>
      <p v-else-if="error" class="error-text">{{{{ error }}}}</p>
      <p v-else-if="!items.length">없음</p>
      <table v-else class="data-table">
        <thead>
          <tr>
{headers}
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in items" :key="item.{id_prop}">
{cells}
            <td>
              <button @click="goDetail(item.{id_prop})">상세</button>
              <button @click="goEdit(item.{id_prop})">수정</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import {{ onMounted, ref }} from "vue";
import {{ useRouter }} from "vue-router";
import ROUTES from "@/constants/routes";
import {{ list{entity} }} from "@/api/{ev}Api";

const router = useRouter();
const items = ref([]);
const loading = ref(true);
const error = ref("");

async function load() {{
  loading.value = true;
  error.value = "";
  try {{
    const data = await list{entity}();
    items.value = Array.isArray(data) ? data : [];
  }} catch (e) {{
    error.value = e?.message || "조회 실패";
  }} finally {{
    loading.value = false;
  }}
}}

function goCreate() {{
  router.push(ROUTES.{key}_CREATE);
}}

function goDetail(id) {{
  router.push(`/{ev}/detail/${{id}}`);
}}

function goEdit(id) {{
  router.push(`/{ev}/edit/${{id}}`);
}}

onMounted(load);
</script>
'''


def _build_detail_view(entity: str, schema: Any) -> str:
    ev = vue_entity_var(entity)
    id_prop = getattr(schema, "id_prop", "id")
    fields = list(getattr(schema, "fields", []) or []) or [(id_prop, getattr(schema, "id_column", id_prop), "String")]
    rows = "\n".join([f"      <p><strong>{_label(prop)}</strong>: {{{{ item.{prop} }}}}</p>" for prop, _, _ in fields])
    return f'''<template>
  <div class="page-shell">
    <div class="page-card">
      <div class="page-header">
        <h1>{entity}</h1>
        <div>
          <button @click="goList">목록</button>
          <button @click="goEdit">수정</button>
          <button @click="removeItem">삭제</button>
        </div>
      </div>
      <p v-if="loading">로딩중</p>
      <p v-else-if="error" class="error-text">{{{{ error }}}}</p>
      <div v-else>
{rows}
      </div>
    </div>
  </div>
</template>

<script setup>
import {{ onMounted, ref }} from "vue";
import {{ useRoute, useRouter }} from "vue-router";
import {{ delete{entity}, get{entity} }} from "@/api/{ev}Api";

const route = useRoute();
const router = useRouter();
const item = ref({{}});
const loading = ref(true);
const error = ref("");
const {id_prop} = route.params.{id_prop};

async function load() {{
  loading.value = true;
  error.value = "";
  try {{
    item.value = await get{entity}({id_prop});
  }} catch (e) {{
    error.value = e?.message || "조회 실패";
  }} finally {{
    loading.value = false;
  }}
}}

function goList() {{
  router.push('/{ev}/list');
}}

function goEdit() {{
  router.push(`/{ev}/edit/${{{id_prop}}}`);
}}

async function removeItem() {{
  await delete{entity}({id_prop});
  router.push('/{ev}/list');
}}

onMounted(load);
</script>
'''


def _build_form_view(entity: str, schema: Any) -> str:
    ev = vue_entity_var(entity)
    id_prop = getattr(schema, "id_prop", "id")
    fields = list(getattr(schema, "fields", []) or []) or [(id_prop, getattr(schema, "id_column", id_prop), "String")]
    form_init = ",\n  ".join([f'{prop}: ""' for prop, _, _ in fields])
    inputs = "\n".join([
        f'''      <label class="form-row">\n        <span>{_label(prop)}</span>\n        <input v-model="form.{prop}"{' :readonly="isEdit" :aria-readonly="isEdit"' if prop == id_prop else ''} />\n      </label>'''
        for prop, _, _ in fields
    ])
    return f'''<template>
  <div class="page-shell">
    <div class="page-card">
      <div class="page-header">
        <h1>{entity} Form</h1>
        <button @click="goList">목록</button>
      </div>
      <p v-if="error" class="error-text">{{{{ error }}}}</p>
      <form @submit.prevent="submit">
{inputs}
        <div class="page-header">
          <button type="submit">저장</button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup>
import {{ onMounted, reactive, ref }} from "vue";
import {{ useRoute, useRouter }} from "vue-router";
import {{ create{entity}, get{entity}, update{entity} }} from "@/api/{ev}Api";

const route = useRoute();
const router = useRouter();
const {id_prop} = route.params.{id_prop} || "";
const isEdit = !!{id_prop};
const error = ref("");
const form = reactive({{
  {form_init}
}});

async function load() {{
  if (!isEdit) return;
  const data = await get{entity}({id_prop});
  Object.assign(form, data || {{}});
}}

async function submit() {{
  error.value = "";
  try {{
    if (isEdit) {{
      await update{entity}(form.{id_prop}, form);
    }} else {{
      await create{entity}(form);
    }}
    router.push('/{ev}/list');
  }} catch (e) {{
    error.value = e?.message || "Failed to save";
  }}
}}

function goList() {{
  router.push('/{ev}/list');
}}

onMounted(load);
</script>
'''


def ensure_vue_frontend_crud(project_root: Path, schema_map: Dict[str, Any]) -> Dict[str, str]:
    report: Dict[str, str] = {}
    entities = [(entity, schema) for entity, schema in (schema_map or {}).items() if schema is not None]
    if not entities:
        return report

    router_body, routes_body = _build_routes(entities)
    report["frontend/vue/src/router/index.js"] = _write_text_if_changed(project_root / "frontend/vue/src/router/index.js", router_body)
    report["frontend/vue/src/constants/routes.js"] = _write_text_if_changed(project_root / "frontend/vue/src/constants/routes.js", routes_body)

    nav_links: List[str] = []
    for entity, _schema in entities:
        ev = vue_entity_var(entity)
        nav_links.append(f'      <router-link style="color:#fff" to="/{ev}/list">{entity}</router-link>')
        nav_links.append(f'      <router-link style="color:#fff" to="/{ev}/create">{entity} Create</router-link>')
    nav_block = "\n".join(nav_links)
    app_body = f'''<template>
  <div>
    <nav style="display:flex;gap:12px;padding:12px 16px;background:#222;flex-wrap:wrap;">
{nav_block}
    </nav>
    <router-view />
  </div>
</template>
'''
    report["frontend/vue/src/App.vue"] = _write_text_if_changed(project_root / "frontend/vue/src/App.vue", app_body)

    for entity, schema in entities:
        ev = vue_entity_var(entity)
        report[f"frontend/vue/src/api/{ev}Api.js"] = _write_text_if_changed(project_root / f"frontend/vue/src/api/{ev}Api.js", _build_api(entity, schema))
        report[f"frontend/vue/src/views/{ev}/{entity}List.vue"] = _write_text_if_changed(project_root / f"frontend/vue/src/views/{ev}/{entity}List.vue", _build_list_view(entity, schema))
        report[f"frontend/vue/src/views/{ev}/{entity}Detail.vue"] = _write_text_if_changed(project_root / f"frontend/vue/src/views/{ev}/{entity}Detail.vue", _build_detail_view(entity, schema))
        report[f"frontend/vue/src/views/{ev}/{entity}Form.vue"] = _write_text_if_changed(project_root / f"frontend/vue/src/views/{ev}/{entity}Form.vue", _build_form_view(entity, schema))
    return report
