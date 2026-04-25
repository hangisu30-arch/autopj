from pathlib import Path

from app.validation.generated_project_validator import _scan_search_fields_cover_all_columns
from app.validation.project_auto_repair import auto_repair_generated_project
from app.io.execution_core_apply import _rewrite_list_jsp_from_schema
from execution_core.builtin_crud import schema_for


def test_validator_accepts_temporal_range_inputs_and_search_field_markers(tmp_path: Path):
    project_root = tmp_path
    vo_path = project_root / 'src/main/java/egovframework/test/member/service/MemberVO.java'
    vo_path.parent.mkdir(parents=True, exist_ok=True)
    vo_path.write_text(
        'package egovframework.test.member.service;\n\n'
        'public class MemberVO {\n'
        '  private String memberId;\n'
        '  private String useYn;\n'
        '  private String regDt;\n'
        '}\n',
        encoding='utf-8',
    )
    jsp_path = project_root / 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    jsp_path.parent.mkdir(parents=True, exist_ok=True)
    jsp_path.write_text(
        '<form id="searchForm" method="get">\n'
        '  <div class="autopj-search-fields">\n'
        '    <div data-search-field="memberId"><input type="text" name="memberId"/></div>\n'
        '    <div data-search-field="useYn"><select name="useYn"><option value=""></option></select></div>\n'
        '    <div data-search-field="regDt"><input type="datetime-local" name="regDtFrom"/><input type="datetime-local" name="regDtTo"/></div>\n'
        '  </div>\n'
        '  <button type="submit">검색</button>\n'
        '</form>\n',
        encoding='utf-8',
    )

    issues = _scan_search_fields_cover_all_columns(project_root)
    assert issues == []


def test_search_field_repair_adds_temporal_range_and_keeps_existing_fields(tmp_path: Path):
    project_root = tmp_path
    jsp_path = project_root / 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    jsp_path.parent.mkdir(parents=True, exist_ok=True)
    jsp_path.write_text(
        '<form id="searchForm" method="get">\n'
        '  <div class="autopj-search-fields">\n'
        '    <div data-search-field="memberId"><input type="text" name="memberId"/></div>\n'
        '  </div>\n'
        '</form>\n',
        encoding='utf-8',
    )
    report = {
        'static_issues': [
            {
                'type': 'search_fields_incomplete',
                'path': str(jsp_path.relative_to(project_root)).replace('\\', '/'),
                'repairable': True,
                'details': {'missing_fields': ['useYn', 'regDt']},
            }
        ]
    }

    result = auto_repair_generated_project(project_root, report)
    body = jsp_path.read_text(encoding='utf-8')

    assert result['changed_count'] == 1
    assert 'name="memberId"' in body
    assert 'name="useYn"' in body
    assert 'data-search-field="regDt"' in body
    assert 'name="regDtFrom"' in body
    assert 'name="regDtTo"' in body


def test_list_jsp_rewrite_generates_temporal_range_for_string_datetime_fields(tmp_path: Path):
    project_root = tmp_path
    rel = 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    jsp_path = project_root / rel
    jsp_path.parent.mkdir(parents=True, exist_ok=True)
    jsp_path.write_text('<html></html>', encoding='utf-8')
    schema = schema_for(
        'Member',
        table='member',
        inferred_fields=[
            ('memberId', 'member_id', 'String'),
            ('useYn', 'use_yn', 'String'),
            ('regDt', 'reg_dt', 'String'),
        ],
    )
    schema.routes['list'] = '/member/list.do'
    schema.routes['detail'] = '/member/detail.do'
    schema.routes['form'] = '/member/form.do'
    schema.routes['delete'] = '/member/delete.do'

    changed = _rewrite_list_jsp_from_schema(project_root, rel, schema)
    body = jsp_path.read_text(encoding='utf-8')

    assert changed is True
    assert 'data-search-field="useYn"' in body
    assert 'name="useYn"' in body
    assert 'data-search-field="regDt"' in body
    assert 'name="regDtFrom"' in body
    assert 'name="regDtTo"' in body
