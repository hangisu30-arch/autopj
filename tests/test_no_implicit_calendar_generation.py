from app.engine.analysis import AnalysisContext, AnalysisEngine


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


def test_schedule_like_domain_without_explicit_calendar_request_stays_crud_surface():
    data = _run(
        """
        회원 일정 관리 기능을 만든다.
        목록/상세/등록/수정/삭제가 필요하다.
        컬럼은 schedule_id, title, start_datetime, end_datetime, use_yn 이다.
        캘린더는 요청하지 않았다.
        """
    )
    domain = data['domains'][0]
    assert domain['feature_kind'] == 'schedule'
    assert domain['feature_types'][:2] == ['schedule', 'crud']
    assert domain['ir']['classification']['primaryPattern'] == 'crud'
    assert 'calendar' not in domain['pages']
    assert all('/calendar' not in endpoint for endpoint in domain['api_endpoints'])
    assert domain['contracts']['uiPolicy']['calendarContract']['enabled'] is False


