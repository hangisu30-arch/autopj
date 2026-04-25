from pathlib import Path

from app.validation.project_auto_repair import (
    _repair_missing_view,
    _rewrite_membership_controller_to_safe_routes,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_missing_view_repair_rewrites_memberadmin_controller_to_own_views(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/memberAdmin/web/MemberAdminController.java'
    _write(
        controller,
        'package egovframework.test.memberAdmin.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n'
        '@RequestMapping("/memberAdmin")\n'
        'public class MemberAdminController {\n'
        '  @GetMapping("/form.do") public String form(){ return "member/memberForm"; }\n'
        '}\n',
    )
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/memberAdmin/memberAdminForm.jsp', '<form></form>')
    issue = {'details': {'missing_view': 'member/memberForm'}}

    changed = _repair_missing_view(controller, issue, tmp_path)

    assert changed is True
    body = controller.read_text(encoding='utf-8')
    assert 'return "memberAdmin/memberAdminForm";' in body
    assert 'return "member/memberForm";' not in body


def test_rewrite_membership_controller_uses_member_id_for_memberadmin(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/memberAdmin/web/MemberAdminController.java'
    _write(controller, 'package egovframework.test.memberAdmin.web;\npublic class MemberAdminController {}\n')
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/memberAdmin/memberAdminList.jsp',
        '<a href="<c:url value=\'/memberAdmin/detail.do\'/>?memberId=${row.memberId}">상세</a>'
        '<form action="${pageContext.request.contextPath}/memberAdmin/delete.do" method="post">'
        '<input type="hidden" name="memberId" value="${row.memberId}" />'
        '</form>',
    )

    changed = _rewrite_membership_controller_to_safe_routes(controller, 'memberAdmin', tmp_path)

    assert changed is True
    body = controller.read_text(encoding='utf-8')
    assert '@RequestMapping("/memberAdmin")' in body
    assert 'return "memberAdmin/memberAdminForm";' in body
    assert 'return "memberAdmin/memberAdminDetail";' in body
    assert '@RequestParam(value = "memberId", required = false) String memberId' in body
    assert '@RequestParam(value = "id", required = false) String id' not in body
