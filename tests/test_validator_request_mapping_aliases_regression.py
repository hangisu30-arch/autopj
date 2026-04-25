from pathlib import Path
from types import SimpleNamespace

from app.validation.generated_project_validator import validate_generated_project


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def _cfg(**kwargs):
    base = dict(
        frontend_key='jsp',
        backend_key='springboot',
        project_name='demo',
        auth_cert_login=False,
        auth_jwt_login=False,
        auth_unified_auth=False,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_validator_accepts_class_and_method_requestmapping_alias_arrays_for_member_routes(tmp_path: Path) -> None:
    _write(
        tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java',
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.ui.Model;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller\n@RequestMapping({"/member", "/tbMember"})\n'
        'public class MemberController {\n'
        '  @GetMapping("/list.do") public String list(Model model){ return "member/memberList"; }\n'
        '  @GetMapping({"/form.do", "/register.do"}) public String form(Model model){ return "member/memberForm"; }\n'
        '  @GetMapping({"/detail.do", "/view.do"}) public String detail(@RequestParam("memberId") String memberId, Model model){ return "member/memberDetail"; }\n'
        '  @PostMapping({"/save.do", "/actionRegister.do"}) public String save(){ return "redirect:/member/list.do"; }\n'
        '  @PostMapping("/delete.do") public String delete(@RequestParam("memberId") String memberId){ return "redirect:/member/list.do"; }\n'
        '}\n',
    )
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/member/memberList.jsp', '<a href="<c:url value=\'/member/detail.do\'/>?memberId=${item.memberId}">상세</a>')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/member/memberForm.jsp', '<form action="<c:url value=\'/member/save.do\'/>" method="post"><a href="<c:url value=\'/member/list.do\'/>">목록</a></form>')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/member/memberDetail.jsp', '<a href="<c:url value=\'/member/form.do\'/>?memberId=${item.memberId}">수정</a><form action="<c:url value=\'/member/delete.do\'/>" method="post"><input type="hidden" name="memberId" value="${item.memberId}"/></form>')

    report = validate_generated_project(tmp_path, _cfg(), include_runtime=False)
    messages = [i.get('message') or i.get('reason') or '' for i in (report.get('issues') or report.get('static_issues') or [])]
    assert not any('jsp references routes with no matching controller mapping' in msg for msg in messages)


def test_validator_accepts_route_param_scan_for_method_alias_arrays(tmp_path: Path) -> None:
    _write(
        tmp_path / 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java',
        'package egovframework.test.adminMember.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.ui.Model;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller\n@RequestMapping({"/adminMember", "/memberAdmin"})\n'
        'public class AdminMemberController {\n'
        '  @GetMapping("/list.do") public String list(Model model){ return "adminMember/adminMemberList"; }\n'
        '  @GetMapping({"/detail.do", "/view.do"}) public String detail(@RequestParam("memberId") String memberId, Model model){ return "adminMember/adminMemberDetail"; }\n'
        '  @GetMapping({"/form.do", "/edit.do"}) public String form(@RequestParam(value="memberId", required=false) String memberId, Model model){ return "adminMember/adminMemberForm"; }\n'
        '  @PostMapping("/delete.do") public String delete(@RequestParam("memberId") String memberId){ return "redirect:/adminMember/list.do"; }\n'
        '}\n',
    )
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/adminMember/adminMemberList.jsp', '<a href="<c:url value=\'/adminMember/detail.do\'/>?memberId=${item.memberId}">상세</a><a href="<c:url value=\'/adminMember/form.do\'/>?memberId=${item.memberId}">수정</a><form action="<c:url value=\'/adminMember/delete.do\'/>" method="post"><input type="hidden" name="memberId" value="${item.memberId}"/></form>')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/adminMember/adminMemberForm.jsp', '<a href="<c:url value=\'/adminMember/list.do\'/>">목록</a>')
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/adminMember/adminMemberDetail.jsp', '<a href="<c:url value=\'/adminMember/form.do\'/>?memberId=${item.memberId}">수정</a>')

    report = validate_generated_project(tmp_path, _cfg(), include_runtime=False)
    messages = [i.get('message') or i.get('reason') or '' for i in (report.get('issues') or report.get('static_issues') or [])]
    assert not any('controller request params do not match jsp route parameters in adminMember' in msg for msg in messages)
