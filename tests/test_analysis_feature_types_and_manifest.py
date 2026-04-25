from app.engine.analysis import AnalysisContext, AnalysisEngine
from app.ui.analysis_bridge import analysis_result_to_prompt_text


def _run(requirements: str, frontend: str = 'jsp') -> dict:
    ctx = AnalysisContext.from_inputs(
        project_root='demo',
        project_name='worktest',
        frontend_mode=frontend,
        database_type='mysql',
        requirements_text=requirements,
        schema_text='',
    )
    return AnalysisEngine().run(ctx).to_dict()


def test_schedule_domain_emits_feature_types_contracts_and_manifest():
    data = _run(
        """
        회의실 예약 기능을 만든다.
        목록/상세/등록/수정/삭제와 월간 캘린더 화면이 필요하다.
        컬럼은 reservation_id, room_id, reservation_title, start_datetime, end_datetime, status_cd, use_yn, reg_dt, upd_dt 이다.
        reservation_id 는 기본키이다.
        """
    )
    domain = data['domains'][0]
    assert domain['feature_kind'] == 'schedule'
    assert domain['feature_types'][:2] == ['schedule', 'crud']
    assert domain['contracts']['temporal']['enabled'] is True
    assert domain['contracts']['status']['enabled'] is True
    backend_manifest = {item['artifact_type'] for item in domain['artifact_manifest']['backend']}
    frontend_manifest = {item['artifact_type'] for item in domain['artifact_manifest']['frontend']}
    assert 'calendar_query' in backend_manifest
    assert 'calendar_jsp' in frontend_manifest


def test_auth_domain_keeps_auth_only_manifest_even_without_feature_name():
    data = _run(
        """
        사용자 아이디와 비밀번호로 로그인하고 로그아웃할 수 있어야 한다.
        세션 인증이 필요하고 CRUD 화면은 만들지 않는다.
        컬럼은 user_id, password 이다.
        user_id 는 기본키이다.
        """
    )
    domain = data['domains'][0]
    assert domain['feature_kind'] == 'auth'
    assert domain['feature_types'] == ['auth']
    backend_manifest = {item['artifact_type'] for item in domain['artifact_manifest']['backend']}
    assert 'controller' in backend_manifest
    assert 'mapper' not in backend_manifest
    assert domain['contracts']['auth']['enabled'] is True


def test_analysis_prompt_text_contains_feature_types_contracts_and_manifest():
    data = _run(
        """
        조회전용 예약 보고서 화면이 필요하다.
        검색, 상세조회, 보고서 출력, 엑셀 다운로드가 필요하다.
        컬럼은 report_id, report_title, start_date, end_date, status_cd 이다.
        report_id 는 기본키이다.
        """
    )
    prompt_text = analysis_result_to_prompt_text(data)
    assert 'feature_types=' in prompt_text
    assert 'contracts=' in prompt_text
    assert 'artifact_manifest=' in prompt_text
