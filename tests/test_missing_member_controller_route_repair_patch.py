from pathlib import Path

from app.validation.project_auto_repair import _repair_jsp_missing_route_reference


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_repair_creates_missing_member_controller_for_member_jsp_routes(tmp_path: Path) -> None:
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java',
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @GetMapping("/login.do") public String login(){ return "login/login"; }\n'
        '}\n',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    _write(
        jsp,
        '<a href="<c:url value=\'/member/detail.do\'/>">상세</a>'
        '<a href="<c:url value=\'/member/form.do\'/>">수정</a>'
        '<form action="<c:url value=\'/member/delete.do\'/>" method="post"></form>',
    )

    changed = _repair_jsp_missing_route_reference(
        jsp,
        issue={
            'details': {
                'missing_routes': ['/member/detail.do', '/member/form.do', '/member/delete.do', '/member/list.do'],
                'discovered_routes': ['/login/login.do'],
            }
        },
        project_root=tmp_path,
    )

    assert changed is True
    controller = tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java'
    body = controller.read_text(encoding='utf-8')
    assert '@RequestMapping("/member")' in body
    assert '@GetMapping("/detail.do")' in body
    assert '@GetMapping({"/register.do", "/form.do"})' in body
    assert '@GetMapping("/list.do")' in body
    assert '@PostMapping({"/actionRegister.do", "/save.do"})' in body
    assert '@PostMapping("/delete.do")' in body
