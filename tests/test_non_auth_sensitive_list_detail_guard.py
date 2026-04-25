from pathlib import Path

from app.io.execution_core_apply import _rewrite_detail_jsp_from_schema, _rewrite_list_jsp_from_schema
from app.ui.generated_content_validator import validate_generated_content
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_CRUD


def _member_schema():
    return schema_for(
        'Member',
        inferred_fields=[
            ('memberId', 'member_id', 'String'),
            ('loginId', 'login_id', 'String'),
            ('loginPassword', 'login_password', 'String'),
            ('passwordHash', 'password_hash', 'String'),
            ('memberName', 'member_name', 'String'),
            ('email', 'email', 'String'),
        ],
        table='tb_member',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )


def test_rewrite_list_jsp_from_schema_excludes_auth_sensitive_fields_for_non_auth_list(tmp_path: Path) -> None:
    rel = 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<html><body>broken</body></html>', encoding='utf-8')

    changed = _rewrite_list_jsp_from_schema(tmp_path, rel, _member_schema())
    body = path.read_text(encoding='utf-8').lower()

    assert changed is True
    assert 'loginpassword' not in body
    assert 'password_hash' not in body
    assert 'membername' in body
    ok, reason = validate_generated_content(rel, path.read_text(encoding='utf-8'), frontend_key='jsp')
    assert ok, reason


def test_rewrite_detail_jsp_from_schema_excludes_auth_sensitive_fields_for_non_auth_detail(tmp_path: Path) -> None:
    rel = 'src/main/webapp/WEB-INF/views/member/memberDetail.jsp'
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<html><body>broken</body></html>', encoding='utf-8')

    changed = _rewrite_detail_jsp_from_schema(tmp_path, rel, _member_schema())
    body = path.read_text(encoding='utf-8').lower()

    assert changed is True
    assert 'loginpassword' not in body
    assert 'password_hash' not in body
    assert 'membername' in body
    ok, reason = validate_generated_content(rel, path.read_text(encoding='utf-8'), frontend_key='jsp')
    assert ok, reason


def test_validator_rejects_non_auth_sensitive_aliases() -> None:
    body = '<div>credential</div><input type="text" name="pinCode" value="${item.pinCode}"/>'
    ok, reason = validate_generated_content('src/main/webapp/WEB-INF/views/member/memberList.jsp', body, frontend_key='jsp')
    assert ok is False
    assert 'auth-sensitive' in reason
