from pathlib import Path

from app.io.execution_core_apply import _rewrite_form_jsp_from_schema
from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.feature_rules import FEATURE_KIND_CRUD


def _account_schema():
    return schema_for(
        'User',
        inferred_fields=[
            ('userId', 'user_id', 'String'),
            ('loginId', 'login_id', 'String'),
            ('loginPassword', 'login_password', 'String'),
            ('userName', 'user_name', 'String'),
            ('email', 'email', 'String'),
            ('phone', 'phone', 'String'),
            ('roleCd', 'role_cd', 'String'),
            ('useYn', 'use_yn', 'String'),
            ('regDt', 'reg_dt', 'String'),
            ('updDt', 'upd_dt', 'String'),
        ],
        table='tb_user',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )


def test_builtin_form_locks_string_primary_key_on_edit_and_preserves_original_id():
    body = builtin_file('jsp/user/userForm.jsp', 'egovframework.test', _account_schema())
    assert body is not None
    assert 'name="userId"' in body
    assert 'name="_originalUserId"' in body
    assert 'data-autopj-id-lock' in body
    assert 'readonly' in body
    assert 'name="loginPassword"' in body


def test_builtin_controller_detail_is_safe_when_id_parameter_is_missing():
    body = builtin_file('java/controller/UserController.java', 'egovframework.test', _account_schema())
    assert body is not None
    assert '@GetMapping("/detail.do")' in body
    assert '@RequestParam(value="userId", required=false) String userId' in body
    assert 'model.addAttribute("item", null);' in body


def test_rewrite_form_jsp_from_schema_keeps_original_id_hidden_for_string_key(tmp_path: Path):
    rel = 'src/main/webapp/WEB-INF/views/user/userForm.jsp'
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<html><body>broken</body></html>', encoding='utf-8')

    changed = _rewrite_form_jsp_from_schema(tmp_path, rel, _account_schema())
    body = path.read_text(encoding='utf-8')

    assert changed is True
    assert 'name="userId"' in body
    assert 'name="_originalUserId"' in body
    assert 'data-autopj-id-lock' in body
    assert 'name="loginPassword"' in body
