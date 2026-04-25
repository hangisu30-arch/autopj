from pathlib import Path
from types import SimpleNamespace

from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_auth_helper_pages_with_action_bar_are_not_flagged_as_broken_forms(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/web/LoginController.java',
        'package egovframework.test.login.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        '@Controller\n'
        'public class LoginController {\n'
        '  @GetMapping("/login/login.do") public String login(){ return "login/login"; }\n'
        '  @GetMapping("/login/main.do") public String main(){ return "login/main"; }\n'
        '  @GetMapping("/login/integrationGuide.do") public String guide(){ return "login/integrationGuide"; }\n'
        '}\n',
    )
    helper_body = '''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<div class="autopj-form-actions">
  <a class="btn" href="<c:url value='/login/login.do'/>">일반 로그인으로 돌아가기</a>
</div>
'''
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/login/integrationGuide.jsp', helper_body)
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/login/main.jsp', helper_body)

    report = validate_generated_project(tmp_path, SimpleNamespace(frontend_key='jsp'), include_runtime=False)
    broken = [i for i in report.get('issues', []) if (i.get('type') or i.get('code')) == 'broken_form_submission']
    assert not [i for i in broken if i['path'].endswith('integrationGuide.jsp') or i['path'].endswith('main.jsp')]


def test_list_search_form_without_action_is_not_treated_as_save_form(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/foo/web/FooController.java',
        'package egovframework.test.foo.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        '@Controller\n'
        'public class FooController {\n'
        '  @GetMapping("/foo/list.do") public String list(){ return "foo/fooList"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/foo/fooList.jsp',
        '''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<form id="searchForm" method="get">
  <input type="text" name="name"/>
  <button type="submit">검색</button>
</form>
''',
    )

    report = validate_generated_project(tmp_path, SimpleNamespace(frontend_key='jsp'), include_runtime=False)
    broken = [i for i in report.get('issues', []) if (i.get('type') or i.get('code')) == 'broken_form_submission' and i['path'].endswith('foo/fooList.jsp')]
    assert not broken


def test_missing_crud_routes_on_list_jsp_are_rewritten_without_cross_domain_links(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/foo/web/FooController.java',
        'package egovframework.test.foo.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        '@Controller\n'
        'public class FooController {\n'
        '  @GetMapping("/foo/list.do") public String list(){ return "foo/fooList"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/foo/service/vo/FooVO.java',
        'package egovframework.test.foo.service.vo;\n'
        'public class FooVO { private String fooId; private String fooName; public String getFooId(){return fooId;} public void setFooId(String v){fooId=v;} public String getFooName(){return fooName;} public void setFooName(String v){fooName=v;} }\n',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/foo/fooList.jsp',
        '''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<a href="<c:url value='/foo/detail.do'/>?fooId=${row.fooId}">상세</a>
<a href="<c:url value='/foo/form.do'/>?fooId=${row.fooId}">수정</a>
<form action="<c:url value='/foo/delete.do'/>" method="post"><button type="submit">삭제</button></form>
''',
    )

    report = validate_generated_project(tmp_path, SimpleNamespace(frontend_key='jsp'), include_runtime=False)
    route_issues = [i for i in report.get('issues', []) if (i.get('type') or i.get('code')) == 'jsp_missing_route_reference']
    assert route_issues

    repaired = apply_generated_project_auto_repair(tmp_path, report)
    assert repaired['changed_count'] >= 1

    post = validate_generated_project(tmp_path, SimpleNamespace(frontend_key='jsp'), include_runtime=False)
    remaining = [i for i in post.get('issues', []) if (i.get('type') or i.get('code')) == 'jsp_missing_route_reference' and i['path'].endswith('foo/fooList.jsp')]
    assert not remaining
    body = (tmp_path / 'src/main/webapp/WEB-INF/views/foo/fooList.jsp').read_text(encoding='utf-8')
    assert '/foo/detail.do' not in body
    assert '/foo/form.do' not in body
    assert '/foo/delete.do' not in body
