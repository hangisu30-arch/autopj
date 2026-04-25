from pathlib import Path

from app.validation.generated_project_validator import _scan_search_fields_cover_all_columns
from app.validation.project_auto_repair import _repair_search_fields_incomplete


def test_validator_accepts_date_range_search_fields(tmp_path: Path):
    root = tmp_path
    (root / 'src/main/java/egovframework/test/member/service/vo').mkdir(parents=True, exist_ok=True)
    (root / 'src/main/webapp/WEB-INF/views/member').mkdir(parents=True, exist_ok=True)
    (root / 'src/main/java/egovframework/test/member/service/vo/MemberVO.java').write_text(
        'package egovframework.test.member.service.vo;\npublic class MemberVO { private String regDt; private String modDt; }',
        encoding='utf-8',
    )
    (root / 'src/main/webapp/WEB-INF/views/member/memberList.jsp').write_text(
        '<form id="searchForm" method="get">\n'
        '<input type="date" name="regDtFrom"/>\n<input type="date" name="regDtTo"/>\n'
        '<input type="date" name="modDtFrom"/>\n<input type="date" name="modDtTo"/>\n'
        '<button type="submit">검색</button></form>',
        encoding='utf-8',
    )
    issues = _scan_search_fields_cover_all_columns(root)
    assert not any(i.get('code') == 'search_fields_incomplete' for i in issues)


def test_repair_adds_date_range_inputs_for_dt_fields(tmp_path: Path):
    path = tmp_path / 'memberList.jsp'
    path.write_text('<form id="searchForm" method="get"><button type="submit">검색</button></form>', encoding='utf-8')
    changed = _repair_search_fields_incomplete(
        path,
        issue={'details': {'missing_fields': ['regDt', 'modDt']}},
        project_root=tmp_path,
    )
    assert changed is True
    body = path.read_text(encoding='utf-8')
    assert 'name="regDtFrom"' in body and 'name="regDtTo"' in body
    assert 'name="modDtFrom"' in body and 'name="modDtTo"' in body
