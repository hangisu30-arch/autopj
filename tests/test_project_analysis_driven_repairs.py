from pathlib import Path

from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import _repair_search_fields_incomplete


class _Cfg:
    frontend_key = 'jsp'
    database_key = 'mysql'


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_validator_flags_generic_login_shortcut_and_orphan_closing_layout(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/demo/login/web/LoginController.java',
        'package demo.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/login")\n'
        'public class LoginController {\n'
        '  @GetMapping("/login.do") public String loginForm(){ return "login/login"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/common/leftNav.jsp',
        '<a href="<c:url value=\'/login.do\' />">로그인</a>',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/member/memberList.jsp',
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<body>\n'
        '<%@ include file="/WEB-INF/views/common/header.jsp" %>\n'
        '<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>\n'
        '</div>\n'
        '<table></table>\n'
        '</body>',
    )
    report = validate_generated_project(tmp_path, _Cfg(), include_runtime=False)
    issue_types = {item.get('type') for item in report.get('static_issues') or []}
    assert 'auth_nav_route_mismatch' in issue_types
    assert 'malformed_jsp_structure' in issue_types


def test_search_field_repair_creates_dedicated_search_form_not_inside_delete_form(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    _write(
        jsp,
        '<html><body>\n'
        '<table><tr><td>\n'
        '<form action="<c:url value=\'/member/delete.do\'/>" method="post">\n'
        '<input type="hidden" name="loginId" value="${row.loginId}"/>\n'
        '<button type="submit">삭제</button>\n'
        '</form>\n'
        '</td></tr></table>\n'
        '<c:choose><c:when test="${not empty list}"></c:when></c:choose>\n'
        '</body></html>',
    )
    issue = {'details': {'missing_fields': ['memberName', 'useYn']}}
    assert _repair_search_fields_incomplete(jsp, issue, tmp_path)
    body = jsp.read_text(encoding='utf-8')
    assert 'id="searchForm"' in body
    assert body.index('id="searchForm"') < body.index('/member/delete.do')
    delete_form_start = body.index('/member/delete.do')
    delete_form_end = body.index('</form>', delete_form_start)
    delete_form = body[delete_form_start:delete_form_end]
    assert 'autopj-search-fields' not in delete_form
    assert 'name="memberName"' in body
    assert 'name="useYn"' in body
