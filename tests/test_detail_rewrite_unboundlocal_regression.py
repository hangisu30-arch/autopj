from pathlib import Path

from app.io.execution_core_apply import _rewrite_detail_jsp_from_schema
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_CRUD


def _schema_without_explicit_detail_route():
    schema = schema_for(
        'Member',
        inferred_fields=[
            ('memberId', 'member_id', 'String'),
            ('memberName', 'member_name', 'String'),
            ('email', 'email', 'String'),
        ],
        table='tb_member',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )
    routes = dict(getattr(schema, 'routes', {}) or {})
    routes.pop('detail', None)
    schema.routes = routes
    return schema


def test_rewrite_detail_jsp_from_schema_does_not_crash_when_detail_route_missing(tmp_path: Path) -> None:
    rel = 'src/main/webapp/WEB-INF/views/member/memberDetail.jsp'
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<html><body>broken</body></html>', encoding='utf-8')

    changed = _rewrite_detail_jsp_from_schema(tmp_path, rel, _schema_without_explicit_detail_route())

    body = path.read_text(encoding='utf-8')
    assert changed is True
    assert '회원 상세' in body or 'Member 상세' in body or 'member 상세' in body.lower()
    assert '<c:if test="${not empty item}">' in body or '<c:if test="${{not empty item}}">' in body
