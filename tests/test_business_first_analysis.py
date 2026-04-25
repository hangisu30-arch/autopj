from app.engine.analysis import AnalysisContext, AnalysisEngine
from app.ui.analysis_bridge import analysis_result_to_prompt_text


def test_analysis_infers_business_tables_for_room_reservation_requirements():
    requirements = """
    회의실 예약 관리 기능을 만든다.
    회의실 목록/등록/수정/삭제와 예약 목록/등록/수정/삭제가 필요하다.
    JSP 기반 화면을 생성한다.
    """
    ctx = AnalysisContext.from_inputs(
        project_root='demo',
        project_name='testbiz',
        frontend_mode='jsp',
        database_type='mysql',
        requirements_text=requirements,
        schema_text='',
    )
    data = AnalysisEngine().run(ctx).to_dict()
    names = [d['name'] for d in data['domains']]
    assert 'room' in names
    assert 'reservation' in names

    room = next(d for d in data['domains'] if d['name'] == 'room')
    reservation = next(d for d in data['domains'] if d['name'] == 'reservation')
    assert [f['column'] for f in room['fields']] == ['room_id', 'room_name', 'location', 'capacity', 'use_yn', 'reg_dt', 'upd_dt']
    assert [f['column'] for f in reservation['fields']] == ['reservation_id', 'room_id', 'reserver_name', 'purpose', 'start_datetime', 'end_datetime', 'status_cd', 'remark', 'reg_dt', 'upd_dt']
    assert room['primary_key_column'] == 'room_id'
    assert reservation['primary_key_column'] == 'reservation_id'


def test_analysis_prompt_text_exposes_authoritative_domain_fields():
    requirements = """
    회의실 예약 관리 기능을 만든다.
    회의실 목록/등록/수정/삭제와 예약 목록/등록/수정/삭제가 필요하다.
    JSP 기반 화면을 생성한다.
    """
    ctx = AnalysisContext.from_inputs(
        project_root='demo',
        project_name='testbiz',
        frontend_mode='jsp',
        database_type='mysql',
        requirements_text=requirements,
        schema_text='',
    )
    result = AnalysisEngine().run(ctx).to_dict()
    prompt_text = analysis_result_to_prompt_text(result)
    assert 'Authoritative generation order: business domain -> business table/columns -> SQL/Mapper -> backend -> frontend.' in prompt_text
    assert 'column=room_id' in prompt_text
    assert 'column=room_name' in prompt_text
    assert 'column=reservation_id' in prompt_text
    assert 'column=start_datetime' in prompt_text
