from app.engine.analysis import AnalysisContext, AnalysisEngine


def test_analysis_emits_ir_for_calendar_schedule():
    requirements = """
    달력 기반 일정관리 화면을 만든다.
    목록/상세/등록/수정/삭제가 필요하지만 메인 화면은 월간 달력이어야 한다.
    컬럼은 schedule_id, title, start_datetime, end_datetime, writer_id, use_yn, reg_dt, upd_dt 이다.
    schedule_id 는 기본키이다.
    """
    ctx = AnalysisContext.from_inputs(
        project_root='demo',
        project_name='worktest',
        frontend_mode='jsp',
        database_type='mysql',
        requirements_text=requirements,
        schema_text='',
    )
    data = AnalysisEngine().run(ctx).to_dict()
    domain = data['domains'][0]
    ir = domain['ir']
    assert data['ir_version'] == '1.0'
    assert data['generation_policy']['modifyExistingOnly'] is True
    assert domain['feature_kind'] == 'schedule'
    assert ir['classification']['primaryPattern'] == 'calendar'
    assert ir['mainEntry']['route'] == '/schedule/calendar.do'
    assert 'writerId' in ir['validationRules']['formHiddenFields']
    assert 'useYn' in ir['validationRules']['formHiddenFields']
    assert any(f['name'] == 'title' and f['visibleInForm'] for f in ir['dataModel']['fields'])
