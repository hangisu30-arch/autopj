from pathlib import Path

from app.io.execution_core_apply import _rewrite_form_jsp_from_schema, _rewrite_list_jsp_from_schema
from app.validation.generated_project_validator import _scan_search_fields_cover_all_columns
from app.validation.project_auto_repair import _rewrite_signup_jsp_to_safe_routes
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_CRUD


def test_search_validator_ignores_userpw_for_non_auth_search(tmp_path: Path) -> None:
    vo = tmp_path / 'src/main/java/egovframework/test/user/service/vo/UserVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        'package egovframework.test.user.service.vo;\n'
        'public class UserVO {\n'
        '  private String loginId;\n'
        '  private String userPw;\n'
        '  private String useYn;\n'
        '}\n',
        encoding='utf-8',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/user/userList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<form id="searchForm" method="get"><input name="loginId"/><select name="useYn"></select></form>', encoding='utf-8')
    issues = _scan_search_fields_cover_all_columns(tmp_path)
    assert not any('userPw' in str(issue.get('message') or '') for issue in issues)


def test_rewrite_form_keeps_useyn_and_createdat_visible(tmp_path: Path) -> None:
    rel = 'src/main/webapp/WEB-INF/views/user/userForm.jsp'
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<html><body>broken</body></html>', encoding='utf-8')
    schema = schema_for(
        'User',
        inferred_fields=[
            ('userId', 'user_id', 'String'),
            ('loginId', 'login_id', 'String'),
            ('userPw', 'user_pw', 'String'),
            ('useYn', 'use_yn', 'String'),
            ('createdAt', 'created_at', 'String'),
        ],
        table='tb_user',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )
    assert _rewrite_form_jsp_from_schema(tmp_path, rel, schema) is True
    body = path.read_text(encoding='utf-8')
    assert 'name="useYn"' in body
    assert 'name="createdAt"' in body


def test_signup_rewrite_does_not_emit_empty_hidden_values(tmp_path: Path) -> None:
    signup = tmp_path / 'src/main/webapp/WEB-INF/views/user/userSignup.jsp'
    signup.parent.mkdir(parents=True, exist_ok=True)
    signup.write_text('<html><body>broken</body></html>', encoding='utf-8')
    controller = tmp_path / 'src/main/java/egovframework/test/user/web/UserController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.user.web;\n'
        '@org.springframework.stereotype.Controller\n'
        '@org.springframework.web.bind.annotation.RequestMapping("/user")\n'
        'public class UserController {\n'
        '  @org.springframework.web.bind.annotation.PostMapping("/save.do") public String save(){ return "redirect:/login/login.do"; }\n'
        '}\n',
        encoding='utf-8',
    )
    vo = tmp_path / 'src/main/java/egovframework/test/user/service/vo/UserSignupVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        'package egovframework.test.user.service.vo;\n'
        'public class UserSignupVO {\n'
        '  private String loginId;\n'
        '  private String userPw;\n'
        '  private String useYn;\n'
        '  private String createdAt;\n'
        '}\n',
        encoding='utf-8',
    )
    assert _rewrite_signup_jsp_to_safe_routes(signup, tmp_path) is True
    body = signup.read_text(encoding='utf-8')
    assert 'value=""' not in body
    assert 'type="hidden" name="useYn"/>' in body or 'type="hidden" name="createdAt"/>' in body


def test_rewrite_list_avoids_row_id_when_schema_has_no_id(tmp_path: Path) -> None:
    rel = 'src/main/webapp/WEB-INF/views/user/userList.jsp'
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<html><body>broken</body></html>', encoding='utf-8')
    schema = schema_for(
        'User',
        inferred_fields=[
            ('loginId', 'login_id', 'String'),
            ('useYn', 'use_yn', 'String'),
        ],
        table='tb_user',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )
    assert _rewrite_list_jsp_from_schema(tmp_path, rel, schema) is True
    body = path.read_text(encoding='utf-8')
    assert '${row.id}' not in body
