from pathlib import Path

from app.io.execution_core_apply import _rewrite_list_jsp_from_schema
from app.validation.generated_project_validator import _scan_temporal_inputs
from app.validation.project_auto_repair import _repair_search_fields_incomplete, _repair_temporal_inputs
from execution_core.builtin_crud import _temporal_write_value_expr, schema_for


def test_list_search_datetime_field_uses_date_input(tmp_path: Path):
    project_root = tmp_path
    rel = "src/main/webapp/WEB-INF/views/member/memberList.jsp"
    path = project_root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<html></html>", encoding="utf-8")
    schema = schema_for(
        "Member",
        table="member",
        inferred_fields=[("regDt", "reg_dt", "String"), ("startDatetime", "start_datetime", "String")],
    )
    schema.routes['list'] = '/member/list.do'
    changed = _rewrite_list_jsp_from_schema(project_root, rel, schema)
    body = path.read_text(encoding="utf-8")

    assert changed is True
    assert 'type="date"' in body
    assert 'name="startDatetimeFrom"' in body and 'type="date"' in body
    assert 'name="startDatetimeTo"' in body and 'type="date"' in body
    assert 'datetime-local' not in body


def test_search_field_repair_uses_date_for_range_inputs(tmp_path: Path):
    path = tmp_path / 'memberList.jsp'
    path.write_text('<form id="searchForm" method="get"><button type="submit">검색</button></form>', encoding='utf-8')
    changed = _repair_search_fields_incomplete(
        path,
        issue={'details': {'missing_fields': ['regDtFrom', 'regDtTo', 'startDatetimeFrom', 'startDatetimeTo']}},
        project_root=tmp_path,
    )
    body = path.read_text(encoding='utf-8')

    assert changed is True
    assert 'name="regDtFrom" data-autopj-temporal="date"' in body
    assert 'name="regDtTo" data-autopj-temporal="date"' in body
    assert 'name="startDatetimeFrom" data-autopj-temporal="date"' in body
    assert 'name="startDatetimeTo" data-autopj-temporal="date"' in body
    assert 'datetime-local' not in body


def test_temporal_validator_and_repair_accept_date_for_query_ranges(tmp_path: Path):
    project_root = tmp_path
    jsp = project_root / 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<html><body>'
        '<form id="searchForm" method="get">'
        '<input type="text" name="startDatetimeFrom" />'
        '<input type="text" name="startDatetimeTo" />'
        '</form>'
        '</body></html>',
        encoding='utf-8',
    )

    changed = _repair_temporal_inputs(jsp, {}, project_root)
    issues = _scan_temporal_inputs(project_root)
    body = jsp.read_text(encoding='utf-8')

    assert changed is True
    assert 'type="date" data-autopj-temporal="date" name="startDatetimeFrom"' in body or 'name="startDatetimeFrom"' in body and 'data-autopj-temporal="date"' in body
    assert not issues


def test_temporal_write_value_expr_expands_datetime_query_range_to_full_day():
    assert _temporal_write_value_expr('startDatetimeFrom', 'start_datetime') == "STR_TO_DATE(CONCAT(NULLIF(#{startDatetimeFrom}, ''), ' 00:00:00'), '%Y-%m-%d %H:%i:%s')"
    assert _temporal_write_value_expr('startDatetimeTo', 'start_datetime') == "STR_TO_DATE(CONCAT(NULLIF(#{startDatetimeTo}, ''), ' 23:59:59'), '%Y-%m-%d %H:%i:%s')"
