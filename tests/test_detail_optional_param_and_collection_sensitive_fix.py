from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH, FEATURE_KIND_CRUD
from app.io.execution_core_apply import _schema_ui_fields


def _user_schema(feature_kind=FEATURE_KIND_AUTH):
    return schema_for(
        'User',
        inferred_fields=[
            ('userId', 'user_id', 'String'),
            ('loginId', 'login_id', 'String'),
            ('loginPassword', 'login_password', 'String'),
            ('userName', 'user_name', 'String'),
            ('useYn', 'use_yn', 'String'),
        ],
        table='tb_user',
        feature_kind=feature_kind,
    )


def test_string_detail_controller_uses_missing_expr_not_unary_bang():
    schema = _user_schema(FEATURE_KIND_CRUD)
    controller = builtin_file('java/controller/UserController.java', 'egovframework.test', schema)
    assert 'if (userId == null || userId.isBlank()) {' in controller
    assert 'if (!userId != null' not in controller
    assert 'if (!userId.isBlank())' not in controller


def test_auth_feature_list_ui_still_hides_password_columns():
    schema = _user_schema()
    list_jsp = builtin_file('jsp/user/userList.jsp', 'egovframework.test', schema)
    assert 'loginPassword' not in list_jsp
    assert 'login_password' not in list_jsp


def test_collection_ui_field_rewrite_excludes_password_even_for_auth_feature_kind():
    schema = _user_schema()
    list_fields = _schema_ui_fields('src/main/webapp/WEB-INF/views/user/userList.jsp', schema, include_id=False)
    form_fields = _schema_ui_fields('src/main/webapp/WEB-INF/views/user/userForm.jsp', schema, include_id=True)
    assert all(prop != 'loginPassword' for prop, _col, _jt in list_fields)
    assert any(prop == 'loginPassword' for prop, _col, _jt in form_fields)
