from pathlib import Path

from app.io.execution_core_apply import _rewrite_list_jsp_from_schema
from execution_core.builtin_crud import schema_for


def test_list_rewrite_includes_primary_key_in_search_form(tmp_path: Path):
    rel = "src/main/webapp/WEB-INF/views/admin/adminList.jsp"
    jsp_path = tmp_path / rel
    jsp_path.parent.mkdir(parents=True, exist_ok=True)
    jsp_path.write_text("<html></html>", encoding="utf-8")

    schema = schema_for(
        "Admin",
        table="tb_member",
        inferred_fields=[
            ("memberId", "member_id", "String"),
            ("memberName", "member_name", "String"),
            ("useYn", "use_yn", "String"),
        ],
    )
    schema.routes["list"] = "/admin/list.do"
    schema.routes["detail"] = "/admin/detail.do"
    schema.routes["form"] = "/admin/form.do"
    schema.routes["delete"] = "/admin/delete.do"

    changed = _rewrite_list_jsp_from_schema(tmp_path, rel, schema)
    body = jsp_path.read_text(encoding="utf-8")

    assert changed is True
    assert "id=\"searchForm\"" in body
    assert "data-search-field=\"memberId\"" in body
    assert "name=\"memberId\"" in body
    assert "data-search-field=\"memberName\"" in body
    assert "data-search-field=\"useYn\"" in body
