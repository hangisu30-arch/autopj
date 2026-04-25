from pathlib import Path

from app.validation.generated_project_validator import _suggest_property_replacement
from app.validation.post_generation_repair import _find_existing_rel_path
from app.validation.project_auto_repair import _repair_jsp_vo_property_mismatch, _select_replacement_prop


def test_find_existing_rel_path_resolves_any_boot_application(tmp_path: Path):
    boot_path = tmp_path / 'src/main/java/com/example/MyAppApplication.java'
    boot_path.parent.mkdir(parents=True, exist_ok=True)
    boot_path.write_text(
        'package com.example;\n\n'
        'import org.springframework.boot.autoconfigure.SpringBootApplication;\n\n'
        '@SpringBootApplication\n'
        'public class MyAppApplication {}\n',
        encoding='utf-8',
    )

    resolved = _find_existing_rel_path(tmp_path, 'src/main/java/egovframework/test/spring/EgovBootApplication.java')

    assert resolved == 'src/main/java/com/example/MyAppApplication.java'


def test_id_replacement_prefers_domain_specific_identifier():
    available = ['memberId', 'memberName', 'loginId']

    assert _suggest_property_replacement('id', available) == 'memberId'
    assert _select_replacement_prop('id', available) == 'memberId'


def test_repair_jsp_vo_property_mismatch_rewrites_generic_id_to_member_id(tmp_path: Path):
    jsp_path = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberDetail.jsp'
    jsp_path.parent.mkdir(parents=True, exist_ok=True)
    jsp_path.write_text(
        '<div>${item.id}</div>\n'
        '<a href="/member/view.do?id=${item.id}">상세</a>\n',
        encoding='utf-8',
    )
    vo_path = tmp_path / 'src/main/java/egovframework/test/member/service/vo/MemberVO.java'
    vo_path.parent.mkdir(parents=True, exist_ok=True)
    vo_path.write_text(
        'package egovframework.test.member.service.vo;\n\n'
        'public class MemberVO {\n'
        '  private String memberId;\n'
        '  public String getMemberId() { return memberId; }\n'
        '  public void setMemberId(String memberId) { this.memberId = memberId; }\n'
        '}\n',
        encoding='utf-8',
    )

    changed = _repair_jsp_vo_property_mismatch(
        jsp_path,
        {
            'details': {
                'vo_path': 'src/main/java/egovframework/test/member/service/vo/MemberVO.java',
                'available_props': ['memberId'],
                'mapper_props': ['memberId'],
                'missing_props': ['id'],
                'missing_props_by_var': {'item': ['id']},
                'suggested_replacements': {'id': 'memberId'},
            }
        },
        tmp_path,
    )

    body = jsp_path.read_text(encoding='utf-8')
    assert changed is True
    assert '${item.memberId}' in body
    assert '${item.id}' not in body
    assert '?id=${item.memberId}' in body
