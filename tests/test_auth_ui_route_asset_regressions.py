from pathlib import Path

from execution_core.builtin_crud import _canonical_userish_entity
from app.validation.project_auto_repair import (
    _repair_jsp_dependency_missing,
    _repair_jsp_missing_route_reference,
    _repair_jsp_vo_property_mismatch,
    _rewrite_auth_alias_collection_jsp,
)


def test_canonical_userish_entity_keeps_member_for_shared_admin_approval_flow():
    source = {
        "requirements_text": "회원가입 + 일반 로그인 + 관리자 승인 + 관리자 메뉴. 회원가입/로그인/회원관리 동일 테이블 사용. 승인 후 로그인.",
    }
    assert _canonical_userish_entity('Login', 'tb_member', source) == 'Member'


def test_rewrite_auth_alias_collection_jsp_generates_safe_collection_without_password(tmp_path: Path):
    root = tmp_path / 'project'
    jsp = root / 'src/main/webapp/WEB-INF/views/login/loginApprovalList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<html><body>placeholder</body></html>', encoding='utf-8')

    vo = root / 'src/main/java/egovframework/test/login/service/vo/LoginVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        'package egovframework.test.login.service.vo;\n'
        'public class LoginVO {\n'
        '  private String member_id;\n'
        '  private String login_id;\n'
        '  private String password;\n'
        '  private String approval_status;\n'
        '  private String use_yn;\n'
        '}\n',
        encoding='utf-8',
    )

    controller = root / 'src/main/java/egovframework/test/login/web/LoginController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/member") public class LoginController {\n'
        '  @GetMapping("/approval/list.do") public String approval(){ return "login/loginApprovalList"; }\n'
        '  @GetMapping("/detail.do") public String detail(){ return "login/loginDetail"; }\n'
        '  @GetMapping("/form.do") public String form(){ return "login/loginForm"; }\n'
        '  @PostMapping("/delete.do") public String delete(){ return "redirect:/member/approval/list.do"; }\n'
        '}\n',
        encoding='utf-8',
    )

    changed = _rewrite_auth_alias_collection_jsp(jsp, root)
    body = jsp.read_text(encoding='utf-8').lower()
    assert changed is True
    assert 'type="password"' not in body
    assert 'name="password"' not in body
    assert '/member/approval/list.do' in body


def test_repair_jsp_dependency_missing_removes_missing_moment_asset(tmp_path: Path):
    root = tmp_path / 'project'
    jsp = root / 'src/main/webapp/WEB-INF/views/main/home.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<html><body><script src="${pageContext.request.contextPath}/js/moment.min.js"></script><div>ok</div></body></html>',
        encoding='utf-8',
    )
    issue = {'details': {'kind': 'asset', 'asset': '/js/moment.min.js'}}
    assert _repair_jsp_dependency_missing(jsp, issue, root) is True
    body = jsp.read_text(encoding='utf-8')
    assert 'moment.min.js' not in body


def test_repair_jsp_missing_route_reference_rewrites_member_controller_to_standard_crud(tmp_path: Path):
    root = tmp_path / 'project'
    jsp = root / 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '''<a href="<c:url value='/member/detail.do'/>">상세</a><a href="<c:url value='/member/form.do'/>">수정</a>''',
        encoding='utf-8',
    )
    controller = root / 'src/main/java/egovframework/test/member/web/MemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller\n@RequestMapping("/member")\npublic class MemberController {\n'
        '  @GetMapping("/login.do") public String loginForm(){ return "member/memberForm"; }\n'
        '  @PostMapping("/actionLogin.do") public String actionLogin(){ return "redirect:/member/login.do"; }\n'
        '}\n',
        encoding='utf-8',
    )
    issue = {'details': {'missing_routes': ['/member/detail.do', '/member/form.do', '/member/delete.do', '/member/list.do', '/member/save.do'], 'discovered_routes': []}}
    _repair_jsp_missing_route_reference(jsp, issue, root)
    body = controller.read_text(encoding='utf-8')
    assert '@GetMapping({"/register.do", "/form.do"})' in body
    assert '@PostMapping({"/actionRegister.do", "/save.do"})' in body


def test_rewrite_auth_alias_collection_jsp_top_level_login_list_uses_real_domain_routes(tmp_path: Path):
    root = tmp_path / 'project'
    jsp = root / 'src/main/webapp/WEB-INF/views/LoginList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<html><body>placeholder</body></html>', encoding='utf-8')

    vo = root / 'src/main/java/egovframework/test/login/service/vo/LoginVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        'package egovframework.test.login.service.vo;\n'
        'public class LoginVO {\n'
        '  private String login_id;\n'
        '  private String approval_status;\n'
        '  private String use_yn;\n'
        '}\n',
        encoding='utf-8',
    )

    controller = root / 'src/main/java/egovframework/test/member/web/MemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller @RequestMapping("/member") public class MemberController {\n'
        '  @GetMapping("/list.do") public String list(){ return "login/LoginList"; }\n'
        '  @GetMapping("/detail.do") public String detail(){ return "login/LoginDetail"; }\n'
        '  @GetMapping("/form.do") public String form(){ return "login/LoginForm"; }\n'
        '  @PostMapping("/delete.do") public String delete(){ return "redirect:/member/list.do"; }\n'
        '}\n',
        encoding='utf-8',
    )

    changed = _rewrite_auth_alias_collection_jsp(jsp, root)
    body = jsp.read_text(encoding='utf-8')
    assert changed is True
    assert '/member/detail.do' in body
    assert '/views/detail.do' not in body
    assert '/views/delete.do' not in body


def test_repair_jsp_vo_property_mismatch_removes_forbidden_member_calendar(tmp_path: Path):
    root = tmp_path / 'project'
    jsp = root / 'src/main/webapp/WEB-INF/views/tbMember/tbMemberCalendar.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<html>${item.memberName}</html>', encoding='utf-8')

    issue = {'details': {'missing_props': ['memberName'], 'available_props': ['loginId'], 'mapper_props': []}}
    assert _repair_jsp_vo_property_mismatch(jsp, issue, root) is True
    assert not jsp.exists()


def test_repair_jsp_missing_route_reference_rewrites_admin_member_controller_to_standard_crud(tmp_path: Path):
    root = tmp_path / 'project'
    jsp = root / 'src/main/webapp/WEB-INF/views/adminMember/adminMemberList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        "<a href=\"<c:url value='/adminMember/detail.do'/>\">상세</a><a href=\"<c:url value='/adminMember/form.do'/>\">수정</a><form action=\"<c:url value='/adminMember/delete.do'/>\"></form>",
        encoding='utf-8',
    )
    controller = root / 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.adminMember.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller\n@RequestMapping("/adminMember")\npublic class AdminMemberController {\n'
        '  @GetMapping("/login.do") public String loginForm(){ return "adminMember/adminMemberForm"; }\n'
        '}\n',
        encoding='utf-8',
    )
    issue = {'details': {'missing_routes': ['/adminMember/detail.do', '/adminMember/form.do', '/adminMember/delete.do'], 'discovered_routes': []}}
    _repair_jsp_missing_route_reference(jsp, issue, root)
    body = controller.read_text(encoding='utf-8')
    assert '@GetMapping("/detail.do")' in body
    assert '@PostMapping("/delete.do")' in body
    assert '@GetMapping({"/list.do", "/approval/list.do", "/admin/list.do"})' in body
