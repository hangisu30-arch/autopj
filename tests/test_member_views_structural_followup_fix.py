from pathlib import Path

from app.validation.project_auto_repair import (
    _repair_jsp_missing_route_reference,
    _repair_jsp_structural_views_artifact,
    _repair_malformed_jsp_structure,
    _split_domain_tokens,
)


def test_split_domain_tokens_handles_lowercase_tb_compounds():
    assert _split_domain_tokens('tbmember') == ['tb', 'member']
    assert _split_domain_tokens('tbadminmember') == ['tb', 'admin', 'member']


def test_repair_jsp_structural_views_artifact_deletes_views_crud_file(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/views/viewsDetail.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('x', encoding='utf-8')

    assert _repair_jsp_structural_views_artifact(jsp, {}, tmp_path) is True
    assert not jsp.exists()


def test_repair_malformed_jsp_structure_wraps_missing_open_form(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/memberAdmin/memberAdminForm.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<body>\n'
        '<section class="page-shell autopj-form-page">\n'
        '  <div class="autopj-form-actions"><button type="submit">저장</button></div>\n'
        '</form>\n'
        '</section>\n'
        '</body>\n',
        encoding='utf-8',
    )

    assert _repair_malformed_jsp_structure(jsp, {'details': {}}, tmp_path) is True
    body = jsp.read_text(encoding='utf-8')
    assert '<form ' in body
    assert body.count('<form ') == 1
    assert '</form>' in body


def test_repair_member_list_routes_when_controller_domain_is_tbmember(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/tbmember/web/TbMemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.tbmember.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        '@Controller\n'
        'public class TbMemberController { }\n',
        encoding='utf-8',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<a href="${pageContext.request.contextPath}/member/form.do">등록</a>\n'
        '<a href="${pageContext.request.contextPath}/member/detail.do?memberId=${row.memberId}">상세</a>\n'
        '<form action="${pageContext.request.contextPath}/member/delete.do" method="post"></form>\n',
        encoding='utf-8',
    )

    issue = {
        'details': {
            'missing_routes': ['/member/form.do', '/member/detail.do', '/member/delete.do'],
            'discovered_routes': [],
        }
    }
    assert _repair_jsp_missing_route_reference(jsp, issue, tmp_path) is True
    controller_body = controller.read_text(encoding='utf-8')
    assert '@RequestMapping("/member")' in controller_body
    assert '@GetMapping("/detail.do")' in controller_body
    assert '@GetMapping("/list.do")' in controller_body
