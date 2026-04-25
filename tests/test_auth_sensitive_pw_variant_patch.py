from pathlib import Path

from app.validation.post_generation_repair import _sanitize_frontend_ui_file
from app.validation.project_auto_repair import _replace_jsp_missing_property


def test_member_list_memberpw_is_removed_from_non_auth_list(tmp_path: Path) -> None:
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>\n'
        '<table><tbody><c:forEach var="row" items="${list}"><tr>'
        '<td>${row.memberPw}</td><td>${row.memberNm}</td></tr></c:forEach></tbody></table>',
        encoding='utf-8',
    )

    vo = tmp_path / 'src/main/java/egovframework/test/member/service/vo/MemberVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        'package egovframework.test.member.service.vo;\n'
        'public class MemberVO {\n'
        '  private String memberId;\n'
        '  private String memberNm;\n'
        '  private String memberPw;\n'
        '  private String useYn;\n'
        '}\n',
        encoding='utf-8',
    )

    mapper = tmp_path / 'src/main/resources/egovframework/mapper/member/MemberMapper.xml'
    mapper.parent.mkdir(parents=True, exist_ok=True)
    mapper.write_text(
        '<mapper namespace="egovframework.test.member.service.mapper.MemberMapper">\n'
        '  <resultMap id="memberMap" type="egovframework.test.member.service.vo.MemberVO">\n'
        '    <id property="memberId" column="member_id"/>\n'
        '    <result property="memberNm" column="member_nm"/>\n'
        '    <result property="memberPw" column="member_pw"/>\n'
        '    <result property="useYn" column="use_yn"/>\n'
        '  </resultMap>\n'
        '</mapper>\n',
        encoding='utf-8',
    )

    changed = _sanitize_frontend_ui_file(jsp, 'non-auth UI must not expose auth-sensitive fields such as password/login_password')
    body = jsp.read_text(encoding='utf-8').lower()
    assert changed is True
    assert 'memberpw' not in body
    assert 'member_pw' not in body
    assert 'membernm' in body or 'member_nm' in body


def test_replace_missing_property_does_not_emit_empty_value_placeholder() -> None:
    body = '<input type="hidden" name="memberId" value="<c:out value="${item.missingId}"/>"/>'
    repaired = _replace_jsp_missing_property(body, 'item', 'missingId')
    assert 'value=""' not in repaired
