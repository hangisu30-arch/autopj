from pathlib import Path

from app.io.execution_core_apply import (
    _compact_frontend_content,
    _rewrite_detail_jsp_from_schema,
    _rewrite_form_jsp_from_schema,
    _rewrite_list_jsp_from_schema,
)
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_CRUD


def _member_schema():
    return schema_for(
        'TbMember',
        inferred_fields=[
            ('memberId', 'member_id', 'String'),
            ('memberNm', 'member_nm', 'String'),
            ('approvalStatus', 'approval_status', 'String'),
            ('useYn', 'use_yn', 'String'),
            ('regDt', 'reg_dt', 'String'),
        ],
        table='tb_member',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )


def test_compact_frontend_content_dedupes_duplicate_headers() -> None:
    body = (
        '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>\n'
        '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>\n\n\n'
        '<%@ include file="/WEB-INF/views/common/header.jsp" %>\n'
        '<%@ include file="/WEB-INF/views/common/header.jsp" %>\n'
    )
    compacted = _compact_frontend_content('src/main/webapp/WEB-INF/views/member/memberList.jsp', body)
    assert compacted.count('<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>') == 1
    assert compacted.count('<%@ include file="/WEB-INF/views/common/header.jsp" %>') == 1
    assert '\n\n\n' not in compacted


def test_rewrite_jsp_templates_drop_decorative_wrappers(tmp_path: Path) -> None:
    schema = _member_schema()
    rels = [
        'src/main/webapp/WEB-INF/views/tbMember/tbMemberForm.jsp',
        'src/main/webapp/WEB-INF/views/tbMember/tbMemberList.jsp',
        'src/main/webapp/WEB-INF/views/tbMember/tbMemberDetail.jsp',
    ]
    for rel in rels:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('<html><body>broken</body></html>', encoding='utf-8')

    assert _rewrite_form_jsp_from_schema(tmp_path, rels[0], schema)
    assert _rewrite_list_jsp_from_schema(tmp_path, rels[1], schema)
    assert _rewrite_detail_jsp_from_schema(tmp_path, rels[2], schema)

    combined = '\n'.join((tmp_path / rel).read_text(encoding='utf-8') for rel in rels)
    assert 'autopj-eyebrow' not in combined
    assert 'autopj-form-hero__meta' not in combined
    assert 'autopj-form-section-header' not in combined
    assert '데이터 없음' in combined
