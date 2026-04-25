from pathlib import Path

from app.io.execution_core_apply import _rewrite_detail_jsp_from_schema, _rewrite_form_jsp_from_schema, _rewrite_list_jsp_from_schema
from app.ui.ui_sanitize_common import sanitize_frontend_ui_text
from app.validation.project_auto_repair import _rewrite_signup_jsp_to_safe_routes
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_CRUD


def _user_schema():
    return schema_for(
        'User',
        inferred_fields=[
            ('userId', 'user_id', 'String'),
            ('userName', 'user_name', 'String'),
            ('roleCd', 'role_cd', 'String'),
            ('useYn', 'use_yn', 'String'),
            ('createdAt', 'created_at', 'String'),
            ('updatedAt', 'updated_at', 'String'),
            ('createdBy', 'created_by', 'String'),
            ('db', 'db', 'String'),
            ('schemaName', 'schema_name', 'String'),
            ('tableName', 'table_name', 'String'),
            ('packageName', 'package_name', 'String'),
        ],
        table='tb_user',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )


def test_user_jsp_rewriters_skip_generation_metadata_and_keep_audit_fields(tmp_path: Path):
    schema = _user_schema()
    rels = [
        'src/main/webapp/WEB-INF/views/user/userForm.jsp',
        'src/main/webapp/WEB-INF/views/user/userList.jsp',
        'src/main/webapp/WEB-INF/views/user/userDetail.jsp',
    ]
    for rel in rels:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('<html><body>broken</body></html>', encoding='utf-8')

    assert _rewrite_form_jsp_from_schema(tmp_path, rels[0], schema)
    assert _rewrite_list_jsp_from_schema(tmp_path, rels[1], schema)
    assert _rewrite_detail_jsp_from_schema(tmp_path, rels[2], schema)

    form_body = (tmp_path / rels[0]).read_text(encoding='utf-8')
    list_body = (tmp_path / rels[1]).read_text(encoding='utf-8')
    detail_body = (tmp_path / rels[2]).read_text(encoding='utf-8')

    for body in (form_body, list_body, detail_body):
        lowered = body.lower()
        assert 'schemaname' not in lowered
        assert 'table_name' not in lowered
        assert 'tablename' not in lowered
        assert 'packagename' not in lowered
        assert 'name="db"' not in lowered

    for field_name in ('roleCd', 'useYn', 'createdAt', 'updatedAt', 'createdBy'):
        assert f'name="{field_name}"' in form_body


def test_signup_rewrite_uses_hidden_inputs_without_empty_value_placeholders(tmp_path: Path):
    signup = tmp_path / 'src/main/webapp/WEB-INF/views/user/signup.jsp'
    signup.parent.mkdir(parents=True, exist_ok=True)
    signup.write_text('</form>broken', encoding='utf-8')

    controller = tmp_path / 'src/main/java/egovframework/test/user/web/UserController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.user.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.PostMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/user")\n'
        'public class UserController {\n'
        '  @GetMapping("/signup.do") public String signup(){ return "user/signup"; }\n'
        '  @PostMapping("/save.do") public String save(){ return "redirect:/login/login.do"; }\n'
        '  @GetMapping("/checkLoginId.do") public String check(){ return "jsonView"; }\n'
        '}\n',
        encoding='utf-8',
    )

    vo = tmp_path / 'src/main/java/egovframework/test/user/service/vo/UserVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        'package egovframework.test.user.service.vo;\n'
        'public class UserVO {\n'
        '  private String loginId;\n'
        '  private String password;\n'
        '  private String userName;\n'
        '  private String roleCd;\n'
        '  private String useYn;\n'
        '  private String createdBy;\n'
        '}\n',
        encoding='utf-8',
    )

    assert _rewrite_signup_jsp_to_safe_routes(signup, tmp_path)
    body = signup.read_text(encoding='utf-8')

    assert '<form' in body and '</form>' in body
    assert 'name="roleCd"' in body
    assert 'name="useYn"' in body
    assert 'name="createdBy"' in body
    assert 'type="hidden" name="roleCd"/>' in body
    assert 'type="hidden" name="useYn"/>' in body
    assert 'type="hidden" name="createdBy"/>' in body
    assert 'value=""' not in body


def test_sanitize_frontend_ui_text_balances_unclosed_form_and_layout_tags():
    body = '<section><form action="/save.do"><div><input name="userName"/></div>'
    sanitized = sanitize_frontend_ui_text(
        'src/main/webapp/WEB-INF/views/user/userForm.jsp',
        body,
        'non-auth UI must not expose generation metadata fields such as db/schemaName/tableName/packageName',
    )
    assert sanitized.count('<form') == sanitized.count('</form>')
    assert sanitized.count('<section') == sanitized.count('</section>')
    assert sanitized.count('<div') == sanitized.count('</div>')
