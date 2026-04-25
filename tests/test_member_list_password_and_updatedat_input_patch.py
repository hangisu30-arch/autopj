from pathlib import Path

from app.io.execution_core_apply import _rewrite_form_jsp_from_schema
from app.validation.post_generation_repair import _sanitize_frontend_ui_file
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_CRUD


def _member_schema():
    return schema_for(
        'Member',
        inferred_fields=[
            ('memberId', 'member_id', 'String'),
            ('loginId', 'login_id', 'String'),
            ('loginPassword', 'login_password', 'String'),
            ('memberName', 'member_name', 'String'),
            ('updatedAt', 'updated_at', 'String'),
            ('useYn', 'use_yn', 'String'),
        ],
        table='tb_member',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )


def test_member_list_auth_sensitive_reason_rewrites_collection_without_password(tmp_path: Path) -> None:
    rel = 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '<table><tr><th>loginPassword</th></tr><tr><td><c:out value="${row.loginPassword}"/></td></tr></table>',
        encoding='utf-8',
    )

    changed = _sanitize_frontend_ui_file(path, 'non-auth UI must not expose auth-sensitive fields such as password/login_password')
    body = path.read_text(encoding='utf-8')

    assert changed is True
    assert 'loginPassword' not in body
    assert 'type="password"' not in body


def test_rewrite_form_uses_date_input_for_updated_at_name() -> None:
    rel = 'src/main/webapp/WEB-INF/views/login/loginForm.jsp'
    root = Path('/tmp/autopj-date-test')
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<html><body>broken</body></html>', encoding='utf-8')
    try:
        changed = _rewrite_form_jsp_from_schema(root, rel, _member_schema())
        body = path.read_text(encoding='utf-8')
        assert changed is True
        assert 'name="updatedAt"' in body
        assert 'type="date"' in body
    finally:
        if root.exists():
            import shutil
            shutil.rmtree(root)
