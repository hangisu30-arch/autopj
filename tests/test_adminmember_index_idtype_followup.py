from pathlib import Path

from app.validation.generated_project_validator import _scan_id_type_mismatch
from app.validation.project_auto_repair import _repair_jsp_missing_route_reference


def test_id_type_mismatch_ignores_boolean_like_non_id_vo_fields(tmp_path: Path):
    vo = tmp_path / 'src/main/java/egovframework/test/adminMember/service/vo/AdminMemberVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        'package egovframework.test.adminMember.service.vo;\n'
        'public class AdminMemberVO {\n'
        '  private String memberId;\n'
        '  private Boolean status;\n'
        '}\n',
        encoding='utf-8',
    )
    controller = tmp_path / 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.adminMember.web;\n'
        'import org.springframework.web.bind.annotation.RequestParam;\n'
        'public class AdminMemberController {\n'
        '  public String detail(@RequestParam("memberId") String memberId){ return "ok"; }\n'
        '}\n',
        encoding='utf-8',
    )

    issues = _scan_id_type_mismatch(tmp_path)
    assert issues == []


def test_adminmember_route_repair_prefers_adminmember_domain_over_member_routes(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.adminMember.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller\n@RequestMapping("/adminMember")\n'
        'public class AdminMemberController {\n'
        '  @GetMapping("/list.do") public String list(){ return "adminMember/adminMemberList"; }\n'
        '  @GetMapping("/detail.do") public String detail(){ return "adminMember/adminMemberDetail"; }\n'
        '  @GetMapping("/form.do") public String form(){ return "adminMember/adminMemberForm"; }\n'
        '  @GetMapping("/delete.do") public String delete(){ return "redirect:/adminMember/list.do"; }\n'
        '}\n',
        encoding='utf-8',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/adminMember/adminMemberList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<a href="<c:url value="/member/detail.do"/>">상세</a>'
        '<a href="<c:url value="/member/form.do"/>">등록</a>'
        '<a href="<c:url value="/member/delete.do"/>">삭제</a>',
        encoding='utf-8',
    )
    changed = _repair_jsp_missing_route_reference(
        jsp,
        issue={
            'details': {
                'missing_routes': ['/member/detail.do', '/member/form.do', '/member/delete.do'],
                'discovered_routes': ['/adminMember/list.do', '/adminMember/detail.do', '/adminMember/form.do', '/adminMember/delete.do'],
            }
        },
        project_root=tmp_path,
    )
    body = jsp.read_text(encoding='utf-8')
    assert changed is True
    assert '/adminMember/detail.do' in body
    assert '/adminMember/form.do' in body
    assert '/adminMember/delete.do' in body
    assert '/member/detail.do' not in body


def test_index_jsp_with_member_crud_refs_rewrites_to_entry_redirect(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/index/indexList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<a href="<c:url value="/member/list.do"/>">회원</a>', encoding='utf-8')
    controller = tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        '@Controller public class LoginController {\n'
        '  @GetMapping("/login/login.do") public String form(){ return "login/login"; }\n'
        '}\n',
        encoding='utf-8',
    )

    changed = _repair_jsp_missing_route_reference(
        jsp,
        issue={'details': {'missing_routes': ['/member/list.do'], 'discovered_routes': ['/login/login.do']}},
        project_root=tmp_path,
    )
    body = jsp.read_text(encoding='utf-8')
    assert changed is True
    assert '진입 전용 화면' in body
    assert '/login/login.do' in body
