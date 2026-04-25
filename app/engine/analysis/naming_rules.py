from __future__ import annotations

import re
from typing import Iterable

from .analysis_result import DomainNaming


_RESERVED_WORDS = {
    "class",
    "public",
    "private",
    "void",
    "int",
    "long",
    "float",
    "double",
    "delete",
    "default",
    "package",
    "import",
    "return",
    "new",
}


def normalize_token(value: str) -> str:
    if not value:
        return ""
    value = value.strip()
    value = re.sub(r"[^\w가-힣]+", "_", value)
    value = re.sub(r"_+", "_", value)
    value = value.strip("_")
    return value.lower()


def normalize_project_name(value: str) -> str:
    token = normalize_token(value)
    return token or "project"


def strip_logical_tb_prefix(value: str) -> str:
    token = normalize_token(value)
    if not token:
        return ""
    if token in {"tb", "tb_"}:
        return ""
    if token.startswith("tb_"):
        token = token[3:]
    elif token.startswith("tb") and len(token) > 2:
        token = token[2:]
    token = token.lstrip("_")
    return token or ""


def to_camel_case(value: str) -> str:
    parts = [p for p in re.split(r"[_\-\s]+", value.strip()) if p]
    if not parts:
        return "field"
    head = parts[0].lower()
    tail = "".join(p[:1].upper() + p[1:].lower() for p in parts[1:])
    result = head + tail
    if result in _RESERVED_WORDS:
        result += "Field"
    return result


def to_pascal_case(value: str) -> str:
    parts = [p for p in re.split(r"[_\-\s]+", value.strip()) if p]
    if not parts:
        return "Item"
    result = "".join(p[:1].upper() + p[1:].lower() for p in parts)
    if result.lower() in _RESERVED_WORDS:
        result += "Item"
    return result


def singularize(name: str) -> str:
    n = normalize_token(name)
    if n.endswith("ies"):
        return n[:-3] + "y"
    if n.endswith("s") and not n.endswith("ss"):
        return n[:-1]
    return n


def choose_domain_name(candidates: Iterable[str]) -> str:
    cleaned = []
    for x in candidates:
        token = strip_logical_tb_prefix(x) or normalize_token(x)
        if token:
            cleaned.append(token)
    return cleaned[0] if cleaned else "domain"


def build_domain_naming(base_package: str, domain_name: str, frontend_mode: str) -> DomainNaming:
    domain_name = strip_logical_tb_prefix(domain_name) or normalize_token(domain_name)
    entity_name = to_pascal_case(singularize(domain_name))
    package_base = f"{base_package}.{domain_name}"

    web_package = f"{package_base}.web"
    service_package = f"{package_base}.service"
    service_impl_package = f"{service_package}.impl"
    mapper_package = f"{service_package}.mapper"
    vo_package = f"{service_package}.vo"

    controller_suffix = "Controller" if frontend_mode == "jsp" else "RestController"

    return DomainNaming(
        package_base=package_base,
        web_package=web_package,
        service_package=service_package,
        service_impl_package=service_impl_package,
        mapper_package=mapper_package,
        vo_package=vo_package,
        entity_name=entity_name,
        vo_class_name=f"{entity_name}VO",
        mapper_class_name=f"{entity_name}Mapper",
        service_class_name=f"{entity_name}Service",
        service_impl_class_name=f"{entity_name}ServiceImpl",
        controller_class_name=f"{entity_name}{controller_suffix}",
        jsp_list_view=f"/WEB-INF/views/{domain_name}/{domain_name}List.jsp",
        jsp_detail_view=f"/WEB-INF/views/{domain_name}/{domain_name}Detail.jsp",
        jsp_form_view=f"/WEB-INF/views/{domain_name}/{domain_name}Form.jsp",
        react_list_page_path=f"frontend/react/src/pages/{domain_name}/{entity_name}ListPage.jsx",
        react_detail_page_path=f"frontend/react/src/pages/{domain_name}/{entity_name}DetailPage.jsx",
        react_form_page_path=f"frontend/react/src/pages/{domain_name}/{entity_name}FormPage.jsx",
        react_api_path=f"frontend/react/src/api/{domain_name}Api.js",
    )
