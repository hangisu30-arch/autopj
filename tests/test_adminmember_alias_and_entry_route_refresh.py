from pathlib import Path

from app.validation.project_auto_repair import (
    _discover_primary_menu_route,
    _repair_jsp_missing_route_reference,
    _rewrite_membership_controller_to_safe_routes,
    _rewrite_signup_jsp_to_safe_routes,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_membership_controller_aliases_cover_adminmember_and_memberadmin(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/memberAdmin/web/MemberAdminController.java'
    _write(controller, 'package egovframework.test.memberAdmin.web;\npublic class MemberAdminController {}\n')

    assert _rewrite_membership_controller_to_safe_routes(controller, 'adminMember') is True
    body = controller.read_text(encoding='utf-8')

    assert '@RequestMapping({"/adminMember", "/memberAdmin", "/tbMemberAdmin", "/tbmemberadmin"})' in body
    assert '@GetMapping({"/list.do", "/approval/list.do", "/admin/list.do"})' in body
    assert '@GetMapping("/checkLoginId.do")' in body


def test_primary_menu_route_prefers_plain_list_over_admin_alias(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java'
    _write(controller, 'package egovframework.test.adminMember.web;\npublic class AdminMemberController {}\n')
    _rewrite_membership_controller_to_safe_routes(controller, 'adminMember')

    assert _discover_primary_menu_route(tmp_path) == '/adminMember/list.do'


def test_signup_route_rewrite_avoids_adminmember_when_member_route_exists(tmp_path: Path):
    member_controller = tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java'
    admin_controller = tmp_path / 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java'
    signup_jsp = tmp_path / 'src/main/webapp/WEB-INF/views/login/signup.jsp'
    _write(member_controller, 'package egovframework.test.member.web;\npublic class MemberController {}\n')
    _write(admin_controller, 'package egovframework.test.adminMember.web;\npublic class AdminMemberController {}\n')
    _rewrite_membership_controller_to_safe_routes(member_controller, 'member')
    _rewrite_membership_controller_to_safe_routes(admin_controller, 'adminMember')
    _write(signup_jsp, '<form action="<c:url value=\'/adminMember/signup.do\' />"></form><script>fetch("${pageContext.request.contextPath}/adminMember/checkLoginId.do?loginId=")</script>')

    assert _rewrite_signup_jsp_to_safe_routes(signup_jsp, tmp_path) is True
    body = signup_jsp.read_text(encoding='utf-8')
    assert '/member/save.do' in body
    assert '/member/checkLoginId.do' in body
    assert '/adminMember/signup.do' not in body
    assert '/adminMember/checkLoginId.do' not in body


def test_adminmember_detail_route_repair_rewrites_controller_and_index_entry(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/memberAdmin/web/MemberAdminController.java'
    detail_jsp = tmp_path / 'src/main/webapp/WEB-INF/views/adminMember/adminMemberDetail.jsp'
    index_jsp = tmp_path / 'src/main/webapp/WEB-INF/views/index/indexDetail.jsp'
    _write(controller, 'package egovframework.test.memberAdmin.web;\npublic class MemberAdminController {}\n')
    _write(detail_jsp, '<a href="<c:url value=\'/adminMember/list.do\' />">목록</a><a href="<c:url value=\'/adminMember/form.do\' />">수정</a><form action="<c:url value=\'/adminMember/delete.do\' />" method="post"><input type="hidden" name="id"/></form>')
    _write(index_jsp, '<a href="<c:url value=\'/adminMember/admin/list.do\' />">이동</a>')
    issue1 = {'details': {'missing_routes': ['/adminMember/list.do', '/adminMember/form.do', '/adminMember/delete.do'], 'discovered_routes': []}}
    issue2 = {'details': {'missing_routes': ['/adminMember/admin/list.do'], 'discovered_routes': []}}

    assert _repair_jsp_missing_route_reference(detail_jsp, issue1, tmp_path) is True
    assert _repair_jsp_missing_route_reference(index_jsp, issue2, tmp_path) is True

    controller_body = controller.read_text(encoding='utf-8')
    index_body = index_jsp.read_text(encoding='utf-8')
    assert '/adminMember/list.do' in controller_body
    assert '/adminMember/list.do' in index_body
    assert '/adminMember/admin/list.do' not in index_body
