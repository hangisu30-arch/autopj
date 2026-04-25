from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.engine.analysis import AnalysisContext, AnalysisEngine


REQ = """회원 관리 목록/상세/등록/수정/삭제 화면과 기능 생성.
회원 엔티티 컬럼은 member_id, member_name, email 이다.
member_id 는 기본키이다.
JSP 기반 화면을 생성한다.
"""


def main() -> None:
    ctx = AnalysisContext.from_inputs(
        project_root=str(ROOT / 'demo_project'),
        project_name='fulljsp',
        frontend_mode='jsp',
        database_type='mysql',
        requirements_text=REQ,
        schema_text='',
    )
    result = AnalysisEngine().run(ctx).to_dict()
    Path('tests/smoke_test_analysis_schema_inference_output.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    domain = result['domains'][0]
    assert domain['feature_kind'] == 'crud', domain
    assert domain['primary_key'] == 'memberId', domain
    columns = [field['column'] for field in domain['fields']]
    assert columns == ['member_id', 'member_name', 'email'], columns
    assert any('inferred fields/pk' in w for w in result.get('warnings', [])), result
    print('Smoke test passed: schema inference from requirements')


if __name__ == '__main__':
    main()
