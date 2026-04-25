from __future__ import annotations

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.engine.analysis import AnalysisContext, AnalysisEngine


REQ = """회원 관리 목록/상세/등록/수정/삭제 화면과 기능 생성.
회원 엔티티 컬럼은 member_id, member_name, email 이다.
member_id 는 기본키이다.
JSP 기반 화면을 생성하고, eGovFrame MVC 패턴에 맞춰 Controller, Service, Mapper, Mapper.xml, VO, JSP 파일을 함께 생성한다.
목록, 상세, 등록/수정 form 흐름이 연결되어야 한다.
로그인/인증 기능으로 해석하지 말고 일반 CRUD로 처리한다.
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
    Path('tests/smoke_test_analysis_upload_false_positive_output.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    domain = result['domains'][0]
    assert domain['name'] == 'member', domain
    assert domain['feature_kind'] == 'crud', domain
    assert domain['pages'] == ['list', 'detail', 'form'], domain
    print('Smoke test passed: analysis false-positive upload prevented')


if __name__ == '__main__':
    main()
