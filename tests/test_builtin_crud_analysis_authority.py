from execution_core.builtin_crud import infer_schema_from_plan


def test_infer_schema_from_plan_prefers_analysis_domain_fields_over_task_text():
    plan = {
        'domains': [
            {
                'name': 'reservation',
                'entity_name': 'Reservation',
                'source_table': 'reservation',
                'fields': [
                    {'name': 'reservationId', 'column': 'reservation_id', 'java_type': 'Long', 'pk': True},
                    {'name': 'roomId', 'column': 'room_id', 'java_type': 'Long'},
                    {'name': 'startDate', 'column': 'start_date', 'java_type': 'java.util.Date'},
                    {'name': 'endDate', 'column': 'end_date', 'java_type': 'java.util.Date'},
                ],
            }
        ],
        'tasks': [
            {
                'path': 'src/main/java/egovframework/test/reservation/service/vo/ReservationVO.java',
                'content': '컬럼: reservation_id, room_id, title, reserver_name, start_datetime, end_datetime',
            }
        ],
    }
    schema = infer_schema_from_plan(plan)
    assert schema.table == 'reservation'
    assert [col for _, col, _ in schema.fields] == ['reservation_id', 'room_id', 'start_date', 'end_date']
