from pathlib import Path

from execution_core.builtin_crud import Schema, _display_fields, _editable_fields
from app.validation.generated_project_validator import validate_generated_project
from app.validation.post_generation_repair import _sanitize_jsp_partial_includes


class DummyCfg:
    project_name = "ttte"
    frontend_key = "jsp"


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_builtin_crud_excludes_generation_metadata_fields_from_display_and_edit():
    schema = Schema(
        entity="Member",
        entity_var="member",
        table="tb_member",
        id_prop="memberId",
        id_column="member_id",
        fields=[
            ("memberId", "member_id", "String"),
            ("memberName", "member_name", "String"),
            ("db", "db", "String"),
            ("tableName", "table_name", "String"),
            ("packageName", "package_name", "String"),
        ],
        routes={},
        views={},
    )
    display_props = {prop for prop, _col, _jt in _display_fields(schema)}
    editable_props = {prop for prop, _col, _jt in _editable_fields(schema)}
    assert "memberId" in display_props
    assert "memberName" in display_props
    assert "db" not in editable_props
    assert "tableName" not in editable_props
    assert "packageName" not in editable_props


def test_validator_skips_common_layout_partial_for_route_and_jquery_checks(tmp_path: Path):
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/common/layout.jsp', '''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<script>$(function(){ location.href='/sample/selectSample.do'; });</script>
<a href="/user/selectUser.do">sample</a>
''')
    report = validate_generated_project(tmp_path, DummyCfg(), include_runtime=False, run_runtime=False)
    messages = [item['message'] for item in report['static_issues']]
    assert 'jsp uses jquery syntax without jquery script include' not in messages
    assert not any('jsp references routes with no matching controller mapping' in msg for msg in messages)


def test_sanitize_partial_includes_rewrites_common_layout_to_safe_placeholder(tmp_path: Path):
    layout = tmp_path / 'src/main/webapp/WEB-INF/views/common/layout.jsp'
    _write(layout, '''<%@ include file="/WEB-INF/views/common/header.jsp" %>
<script>$(function(){ location.href='/sample/selectSample.do'; });</script>
''')
    changed = _sanitize_jsp_partial_includes(tmp_path)
    assert 'src/main/webapp/WEB-INF/views/common/layout.jsp' in changed
    body = layout.read_text(encoding='utf-8')
    assert 'sample/selectSample.do' not in body
    assert '$(' not in body
    assert 'layout fragment placeholder' in body
