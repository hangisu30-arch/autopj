from pathlib import Path

from app.validation.project_auto_repair import (
    _repair_jsp_missing_route_reference,
    _repair_route_param_mismatch,
    _rewrite_membership_controller_to_safe_routes,
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_rewrite_membership_controller_infers_member_id_for_admin_member(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java'
    vo = tmp_path / 'src/main/java/egovframework/test/adminMember/service/vo/AdminMemberVO.java'
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/adminMember/adminMemberList.jsp'
    _write(
        vo,
        'package egovframework.test.adminMember.service.vo;\n'
        'public class AdminMemberVO {\n'
        '  private String memberId;\n'
        '  private String memberName;\n'
        '}\n',
    )
    _write(
        controller,
        'package egovframework.test.adminMember.web;\n'
        'public class AdminMemberController {}\n',
    )
    _write(
        jsp,
        '<form action="<c:url value=\'/adminMember/delete.do\'/>" method="post">'
        '<input type="hidden" name="memberId" value="${item.memberId}"></form>',
    )
    assert _rewrite_membership_controller_to_safe_routes(controller, 'adminMember') is True
    body = controller.read_text(encoding='utf-8')
    assert '@RequestParam(value = "memberId", required = false) String memberId' in body
    assert '@PostMapping("/delete.do")' in body
    assert 'redirect:/adminMember/list.do' in body


def test_adminmember_route_param_repair_rewrites_member_routes_and_param_names(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java'
    list_jsp = tmp_path / 'src/main/webapp/WEB-INF/views/adminMember/adminMemberList.jsp'
    form_jsp = tmp_path / 'src/main/webapp/WEB-INF/views/adminMember/adminMemberForm.jsp'
    _write(
        controller,
        'package egovframework.test.adminMember.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller\n@RequestMapping("/adminMember")\n'
        'public class AdminMemberController {\n'
        '  @GetMapping("/detail.do") public String detail(@RequestParam("memberId") String memberId){ return "adminMember/adminMemberDetail"; }\n'
        '  @GetMapping("/form.do") public String form(@RequestParam(value="memberId", required=false) String memberId){ return "adminMember/adminMemberForm"; }\n'
        '  @PostMapping("/delete.do") public String delete(@RequestParam("memberId") String memberId){ return "redirect:/adminMember/list.do"; }\n'
        '  @PostMapping("/save.do") public String save(){ return "redirect:/adminMember/list.do"; }\n'
        '  @GetMapping("/list.do") public String list(){ return "adminMember/adminMemberList"; }\n'
        '}\n',
    )
    _write(
        list_jsp,
        '<a href="<c:url value=\'/member/detail.do\'/>?id=${item.memberId}">상세</a>'
        '<a href="<c:url value=\'/member/form.do\'/>?id=${item.memberId}">수정</a>'
        '<form action="<c:url value=\'/member/delete.do\'/>" method="post">'
        '<input type="hidden" name="id" value="${item.memberId}"></form>',
    )
    _write(
        form_jsp,
        '<a href="<c:url value=\'/member/list.do\'/>">목록</a>'
        '<form action="<c:url value=\'/member/save.do\'/>" method="post">'
        '<input type="hidden" name="id" value="${item.memberId}"></form>',
    )
    issue = {
        'details': {
            'domain': 'adminMember',
            'route_params': {
                '/adminMember/detail.do': 'memberId',
                '/adminMember/form.do': 'memberId',
                '/adminMember/delete.do': 'memberId',
            },
            'jsp_paths': [],
            'found_params': {},
        }
    }
    assert _repair_route_param_mismatch(controller, issue, tmp_path) is True
    list_body = list_jsp.read_text(encoding='utf-8')
    form_body = form_jsp.read_text(encoding='utf-8')
    assert '/adminMember/detail.do' in list_body
    assert '/adminMember/form.do' in list_body
    assert '/adminMember/delete.do' in list_body
    assert '?memberId=' in list_body
    assert 'name="memberId"' in list_body
    assert '/adminMember/list.do' in form_body
    assert '/adminMember/save.do' in form_body


def test_index_detail_and_form_views_become_entry_redirect_pages(tmp_path: Path):
    login = tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java'
    _write(
        login,
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        '@Controller public class LoginController {\n'
        '  @GetMapping("/login/login.do") public String form(){ return "login/login"; }\n'
        '}\n',
    )
    for name in ('indexDetail.jsp', 'indexForm.jsp'):
        jsp = tmp_path / f'src/main/webapp/WEB-INF/views/index/{name}'
        _write(jsp, '<a href="<c:url value=\'/member/list.do\'/>">회원</a>')
        changed = _repair_jsp_missing_route_reference(
            jsp,
            issue={'details': {'missing_routes': ['/member/list.do'], 'discovered_routes': ['/login/login.do']}},
            project_root=tmp_path,
        )
        assert changed is True
        body = jsp.read_text(encoding='utf-8')
        assert '진입 전용 화면' in body
        assert '/login/login.do' in body
        assert '/member/list.do' not in body
