from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from execution_core.builtin_crud import builtin_file


def _entity_var(name: str) -> str:
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


def _remove_path(path: Path) -> None:
    if path.is_file():
        path.unlink()
        return
    if path.is_dir():
        for child in sorted(path.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                try:
                    child.rmdir()
                except OSError:
                    pass
        try:
            path.rmdir()
        except OSError:
            pass


def cleanup_leaked_backend_artifacts(project_root: Path, base_package: str, entities: List[str]) -> Dict[str, List[str]]:
    removed = {"java": [], "jsp": []}
    allowed_root = (base_package or "").replace(".", "/")
    java_root = project_root / "src/main/java/egovframework"
    if java_root.exists():
        for entity in entities:
            if not entity:
                continue
            for suffix in ("Controller.java", "RestController.java", "Service.java", "ServiceImpl.java", "Mapper.java", "VO.java"):
                for path in java_root.glob(f"**/{entity}{suffix}"):
                    norm = path.as_posix()
                    if allowed_root and allowed_root in norm:
                        continue
                    _remove_path(path)
                    removed["java"].append(norm)
        for path in java_root.glob("**/config/MyBatisConfig.java"):
            norm = path.as_posix()
            if allowed_root and allowed_root in norm:
                continue
            _remove_path(path)
            removed["java"].append(norm)
    for entity in entities:
        ev = _entity_var(entity)
        view_dir = project_root / f"src/main/webapp/WEB-INF/views/{ev}"
        if view_dir.exists():
            _remove_path(view_dir)
            removed["jsp"].append(view_dir.as_posix())
    return removed


def _module_base(base_package: str, entity: str) -> str:
    ev = _entity_var(entity)
    return f"{base_package}.{ev}"


def _canonical_backend_path(base_package: str, logical_path: str) -> str:
    entity = re.sub(r".*?/([A-Za-z0-9_]+)(?:ServiceImpl|Service|Mapper|VO|RestController)\.java$", r"\1", logical_path)
    module_base = _module_base(base_package, entity)
    pkg_path = module_base.replace(".", "/")
    if logical_path.startswith("java/service/impl/"):
        return f"src/main/java/{pkg_path}/service/impl/{Path(logical_path).name}"
    if logical_path.startswith("java/service/mapper/"):
        return f"src/main/java/{pkg_path}/service/mapper/{Path(logical_path).name}"
    if logical_path.startswith("java/service/vo/"):
        return f"src/main/java/{pkg_path}/service/vo/{Path(logical_path).name}"
    if logical_path.startswith("java/service/"):
        return f"src/main/java/{pkg_path}/service/{Path(logical_path).name}"
    if logical_path.startswith("java/controller/"):
        return f"src/main/java/{pkg_path}/web/{Path(logical_path).name}"
    if logical_path.startswith("mapper/"):
        return f"src/main/resources/egovframework/mapper/{logical_path.replace('mapper/', '', 1)}"
    raise ValueError(f"unsupported logical_path={logical_path}")


def ensure_react_backend_crud(project_root: Path, base_package: str, schema_map: Dict[str, Any]) -> Dict[str, str]:
    report: Dict[str, str] = {}
    for entity, schema in (schema_map or {}).items():
        if schema is None:
            continue
        for logical in (
            f"java/service/{entity}Service.java",
            f"java/service/impl/{entity}ServiceImpl.java",
            f"java/service/mapper/{entity}Mapper.java",
            f"java/service/vo/{entity}VO.java",
            f"java/controller/{entity}RestController.java",
            f"mapper/{_entity_var(entity)}/{entity}Mapper.xml",
        ):
            built = builtin_file(logical, _module_base(base_package, entity), schema)
            if not built:
                continue
            rel_path = _canonical_backend_path(base_package, logical)
            target = project_root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(built, encoding="utf-8")
            report[rel_path] = "written"
        legacy_controller = project_root / _canonical_backend_path(base_package, f"java/controller/{entity}Controller.java")
        if legacy_controller.exists():
            _remove_path(legacy_controller)
            report[legacy_controller.relative_to(project_root).as_posix()] = "removed"
    return report


def _build_service(entity: str, schema: Any) -> str:
    entity_name = entity
    ev = _entity_var(entity)
    id_prop = getattr(schema, "id_prop", "id")
    return f'''import {{ apiRequest }} from "@/api/client";

const API_BASE = "/api/{ev}";

export async function list{entity_name}() {{
  return apiRequest(API_BASE);
}}

export async function get{entity_name}({id_prop}) {{
  return apiRequest(`${{API_BASE}}/${{encodeURIComponent({id_prop})}}`);
}}

export async function create{entity_name}(payload) {{
  return apiRequest(API_BASE, {{
    method: "POST",
    body: JSON.stringify(payload),
  }});
}}

export async function update{entity_name}({id_prop}, payload) {{
  return apiRequest(`${{API_BASE}}/${{encodeURIComponent({id_prop})}}`, {{
    method: "PUT",
    body: JSON.stringify(payload),
  }});
}}

export async function delete{entity_name}({id_prop}) {{
  return apiRequest(`${{API_BASE}}/${{encodeURIComponent({id_prop})}}`, {{
    method: "DELETE",
  }});
}}
'''


def _build_list_page(entity: str, schema: Any) -> str:
    ev = _entity_var(entity)
    key = _route_key(ev)
    id_prop = getattr(schema, "id_prop", "id")
    fields = list(getattr(schema, "fields", []) or [])
    visible = fields[: min(4, len(fields))] or [(id_prop, getattr(schema, "id_column", id_prop), "String")]
    header_cells = "\n".join([f"              <th>{_label(prop)}</th>" for prop, _, _ in visible])
    value_cells = "\n".join([f"                <td>{{item.{prop} ?? \"\"}}</td>" for prop, _, _ in visible])
    return f'''import {{ useEffect, useState }} from "react";
import {{ useNavigate }} from "react-router-dom";
import ROUTES from "@/constants/routes";
import {{ list{entity} }} from "@/api/services/{ev}";

export default function {entity}ListPage() {{
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {{
    let active = true;
    (async () => {{
      try {{
        const data = await list{entity}();
        if (active) {{
          setItems(Array.isArray(data) ? data : []);
        }}
      }} catch (e) {{
        if (active) {{
          setError(e.message || "조회 실패");
        }}
      }} finally {{
        if (active) {{
          setLoading(false);
        }}
      }}
    }})();
    return () => {{
      active = false;
    }};
  }}, []);

  return (
    <div className="page-shell">
      <div className="page-card">
        <div className="page-header">
          <h1>{_label(entity)}</h1>
          <button type="button" onClick={{() => navigate(ROUTES.{key}_CREATE)}}>등록</button>
        </div>
        {{error ? <p className="error-text">{{error}}</p> : null}}
        {{loading ? (
          <p>로딩중</p>
        ) : items.length === 0 ? (
          <p>없음</p>
        ) : (
          <table style={{{{ width: "100%", borderCollapse: "collapse" }}}}>
            <thead>
              <tr>
{header_cells}
              </tr>
            </thead>
            <tbody>
              {{items.map((item) => (
                <tr key={{item.{id_prop}}} style={{{{ cursor: "pointer" }}}} onClick={{() => navigate(ROUTES.{key}_DETAIL(item.{id_prop}))}}>
{value_cells}
                </tr>
              ))}}
            </tbody>
          </table>
        )}}
      </div>
    </div>
  );
}}
'''


def _build_detail_page(entity: str, schema: Any) -> str:
    ev = _entity_var(entity)
    key = _route_key(ev)
    id_prop = getattr(schema, "id_prop", "id")
    fields = list(getattr(schema, "fields", []) or []) or [(id_prop, getattr(schema, "id_column", id_prop), "String")]
    detail_rows = "\n".join([f"            <tr><th style={{{{ textAlign: 'left', paddingRight: 16 }}}}>{_label(prop)}</th><td>{{item.{prop} ?? ''}}</td></tr>" for prop, _, _ in fields])
    return f'''import {{ useEffect, useState }} from "react";
import {{ useNavigate, useParams }} from "react-router-dom";
import ROUTES from "@/constants/routes";
import {{ delete{entity}, get{entity} }} from "@/api/services/{ev}";

export default function {entity}DetailPage() {{
  const navigate = useNavigate();
  const params = useParams();
  const {id_prop} = params.{id_prop};
  const [item, setItem] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {{
    let active = true;
    (async () => {{
      try {{
        const data = await get{entity}({id_prop});
        if (active) {{
          setItem(data);
        }}
      }} catch (e) {{
        if (active) {{
          setError(e.message || "조회 실패");
        }}
      }} finally {{
        if (active) {{
          setLoading(false);
        }}
      }}
    }})();
    return () => {{
      active = false;
    }};
  }}, [{id_prop}]);

  const handleDelete = async () => {{
    if (!window.confirm("삭제하시겠습니까?")) {{
      return;
    }}
    try {{
      await delete{entity}({id_prop});
      navigate(ROUTES.{key}_LIST);
    }} catch (e) {{
      setError(e.message || "삭제에 실패했습니다.");
    }}
  }};

  return (
    <div className="page-shell">
      <div className="page-card">
        <div className="page-header">
          <h1>{_label(entity)}</h1>
          <div style={{{{ display: "flex", gap: 8, flexWrap: "wrap" }}}}>
            <button type="button" onClick={{() => navigate(ROUTES.{key}_LIST)}}>목록</button>
            <button type="button" onClick={{() => navigate(ROUTES.{key}_EDIT({id_prop}))}}>수정</button>
            <button type="button" onClick={{handleDelete}}>삭제</button>
          </div>
        </div>
        {{error ? <p className="error-text">{{error}}</p> : null}}
        {{loading ? (
          <p>로딩중</p>
        ) : !item ? (
          <p>없음</p>
        ) : (
          <table>
{detail_rows}
          </table>
        )}}
      </div>
    </div>
  );
}}
'''


def _build_form_page(entity: str, schema: Any) -> str:
    ev = _entity_var(entity)
    key = _route_key(ev)
    id_prop = getattr(schema, "id_prop", "id")
    fields = list(getattr(schema, "fields", []) or []) or [(id_prop, getattr(schema, "id_column", id_prop), "String")]
    initial_form = ", ".join([f'{prop}: ""' for prop, _, _ in fields])
    input_blocks = "\n".join([
        f'''          <label style={{{{ display: "grid", gap: 6 }}}}>
            <span>{_label(prop)}</span>
            <input
              name="{prop}"
              value={{form.{prop} ?? ""}}
              onChange={{handleChange}}
              {"readOnly={isEdit}" if prop == id_prop else ""}
            />
          </label>''' for prop, _, _ in fields
    ])
    return f'''import {{ useEffect, useState }} from "react";
import {{ useNavigate, useParams }} from "react-router-dom";
import ROUTES from "@/constants/routes";
import {{ create{entity}, get{entity}, update{entity} }} from "@/api/services/{ev}";

const INITIAL_FORM = {{ {initial_form} }};

export default function {entity}FormPage() {{
  const navigate = useNavigate();
  const params = useParams();
  const {id_prop} = params.{id_prop};
  const isEdit = Boolean({id_prop});
  const [form, setForm] = useState(INITIAL_FORM);
  const [loading, setLoading] = useState(isEdit);
  const [error, setError] = useState("");

  useEffect(() => {{
    if (!isEdit) {{
      setForm(INITIAL_FORM);
      setLoading(false);
      return;
    }}
    let active = true;
    (async () => {{
      try {{
        const data = await get{entity}({id_prop});
        if (active) {{
          setForm({{ ...INITIAL_FORM, ...(data || {{}}) }});
        }}
      }} catch (e) {{
        if (active) {{
          setError(e.message || "조회 실패");
        }}
      }} finally {{
        if (active) {{
          setLoading(false);
        }}
      }}
    }})();
    return () => {{
      active = false;
    }};
  }}, [isEdit, {id_prop}]);

  const handleChange = (event) => {{
    const {{ name, value }} = event.target;
    setForm((prev) => ({{ ...prev, [name]: value }}));
  }};

  const handleSubmit = async (event) => {{
    event.preventDefault();
    setError("");
    try {{
      if (isEdit) {{
        await update{entity}({id_prop}, form);
      }} else {{
        await create{entity}(form);
      }}
      navigate(ROUTES.{key}_LIST);
    }} catch (e) {{
      setError(e.message || "저장에 실패했습니다.");
    }}
  }};

  return (
    <div className="page-shell">
      <div className="page-card">
        <div className="page-header">
          <h1>{{isEdit ? "{_label(entity)} Edit" : "{_label(entity)} Create"}}</h1>
          <button type="button" onClick={{() => navigate(ROUTES.{key}_LIST)}}>목록</button>
        </div>
        {{error ? <p className="error-text">{{error}}</p> : null}}
        {{loading ? (
          <p>로딩중</p>
        ) : (
          <form onSubmit={{handleSubmit}} style={{{{ display: "grid", gap: 16, maxWidth: 640 }}}}>
{input_blocks}
            <div style={{{{ display: "flex", gap: 8 }}}}>
              <button type="submit">저장</button>
            </div>
          </form>
        )}}
      </div>
    </div>
  );
}}
'''


def _build_routes(entities: List[str], schema_map: Dict[str, Any]) -> Tuple[str, str, str]:
    if not entities:
        constants = 'const ROUTES = {\n  MAIN: "/",\n};\n\nexport default ROUTES;\n'
        router = 'import { createBrowserRouter } from "react-router-dom";\nimport MainPage from "../pages/main/MainPage";\n\nconst router = createBrowserRouter([{ path: "/", element: <MainPage /> }]);\n\nexport default router;\n'
        main_page = 'export default function MainPage() { return <div className="page-shell"><div className="page-card"><h1>Main Page</h1></div></div>; }\n'
        return constants, router, main_page

    lines = ['const ROUTES = {', '  MAIN: "/",']
    imports = ['import { Navigate, createBrowserRouter } from "react-router-dom";', 'import ROUTES from "@/constants/routes";']
    route_lines: List[str] = []
    first_key = _route_key(_entity_var(entities[0]))
    links: List[str] = []

    for entity in entities:
        ev = _entity_var(entity)
        key = _route_key(ev)
        id_prop = getattr(schema_map.get(entity), 'id_prop', f'{ev}Id')
        imports.append(f'import {entity}ListPage from "@/pages/{ev}/{entity}ListPage";')
        imports.append(f'import {entity}DetailPage from "@/pages/{ev}/{entity}DetailPage";')
        imports.append(f'import {entity}FormPage from "@/pages/{ev}/{entity}FormPage";')
        lines.append(f'  {key}_LIST: "/{ev}",')
        lines.append(f'  {key}_CREATE: "/{ev}/create",')
        lines.append(f'  {key}_DETAIL: ({id_prop}) => `/{ev}/${{{id_prop}}}`,')
        lines.append(f'  {key}_EDIT: ({id_prop}) => `/{ev}/edit/${{{id_prop}}}`,')
        route_lines.extend([
            f'  {{ path: ROUTES.{key}_LIST, element: <{entity}ListPage /> }},',
            f'  {{ path: ROUTES.{key}_CREATE, element: <{entity}FormPage /> }},',
            f'  {{ path: "/{ev}/:{id_prop}", element: <{entity}DetailPage /> }},',
            f'  {{ path: "/{ev}/edit/:{id_prop}", element: <{entity}FormPage /> }},',
        ])
        links.append(f'          <li><a href={{ROUTES.{key}_LIST}}>{_label(entity)} 관리</a></li>')

    lines.append('};')
    lines.append('')
    lines.append('export default ROUTES;')
    constants = "\n".join(lines) + "\n"
    router = "\n".join(imports) + f'\n\nconst router = createBrowserRouter([\n  {{ path: ROUTES.MAIN, element: <Navigate to={{ROUTES.{first_key}_LIST}} replace /> }},\n' + "\n".join(route_lines) + '\n]);\n\nexport default router;\n'
    main_page = 'import ROUTES from "@/constants/routes";\n\nexport default function MainPage() {\n  return (\n    <div className="page-shell">\n      <div className="page-card">\n        <h1>Main Page</h1>\n        <ul>\n' + "\n".join(links) + '\n        </ul>\n      </div>\n    </div>\n  );\n}\n'
    return constants, router, main_page


def ensure_react_frontend_crud(project_root: Path, schema_map: Dict[str, Any]) -> Dict[str, str]:
    report: Dict[str, str] = {}
    entities = [entity for entity in (schema_map or {}).keys() if entity]
    constants, router, main_page = _build_routes(entities, schema_map)
    files: Dict[str, str] = {
        'frontend/react/src/constants/routes.js': constants,
        'frontend/react/src/routes/index.jsx': router,
        'frontend/react/src/pages/main/MainPage.jsx': main_page,
    }
    for entity in entities:
        schema = schema_map.get(entity)
        if schema is None:
            continue
        ev = _entity_var(entity)
        files[f'frontend/react/src/api/services/{ev}.js'] = _build_service(entity, schema)
        files[f'frontend/react/src/pages/{ev}/{entity}ListPage.jsx'] = _build_list_page(entity, schema)
        files[f'frontend/react/src/pages/{ev}/{entity}DetailPage.jsx'] = _build_detail_page(entity, schema)
        files[f'frontend/react/src/pages/{ev}/{entity}FormPage.jsx'] = _build_form_page(entity, schema)
    for rel_path, content in files.items():
        target = project_root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        report[rel_path] = 'written'
    return report
