from pathlib import Path
from types import SimpleNamespace

from app.engine.analysis.schema_parser import SchemaParser
from app.io.execution_core_apply import _rewrite_list_jsp_from_schema
from execution_core.builtin_crud import _table_from_sources


def test_schema_parser_preserves_explicit_table_name_without_tb_prefix():
    parser = SchemaParser()
    tables = parser.infer_from_requirements(
        "테이블명 member_profile\n컬럼: member_id, member_name, reg_dt",
        ["member"],
        auth_intent=False,
    )
    assert tables
    assert tables[0].table_name == "member_profile"


def test_builtin_crud_prefers_explicit_table_name_from_requirements():
    table = _table_from_sources("Member", {"requirements": "테이블명 member_profile\n회원 관리 CRUD 생성"})
    assert table == "member_profile"


def test_rewrite_list_jsp_uses_ul_li_instead_of_table(tmp_path: Path):
    rel = "src/main/webapp/WEB-INF/views/member/memberList.jsp"
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("placeholder", encoding="utf-8")
    schema = SimpleNamespace(
        routes={"form": "/member/form.do", "detail": "/member/detail.do", "delete": "/member/delete.do", "list": "/member/list.do"},
        entity="Member",
        table="member_profile",
        id_prop="memberId",
        id_column="member_id",
        fields=[("memberId", "member_id", "String"), ("memberName", "member_name", "String"), ("regDt", "reg_dt", "String")],
        feature_kind="crud",
        authority="heuristic",
        unified_auth=False,
        cert_login=False,
        jwt_login=False,
        field_comments={},
        field_db_types={},
        field_nullable={},
        field_unique={},
        field_auto_increment={},
        field_defaults={},
        field_references={},
    )
    changed = _rewrite_list_jsp_from_schema(tmp_path, rel, schema)
    assert changed is True
    content = target.read_text(encoding="utf-8")
    assert '<ul class="autopj-record-list"' in content
    assert '<li class="autopj-record-item"' in content
    assert '<table' not in content
