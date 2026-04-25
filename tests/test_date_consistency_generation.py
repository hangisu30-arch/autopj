from execution_core.builtin_crud import _guess_java_type, _java_type_from_sql_type, ddl, schema_for


def test_datetime_and_date_columns_map_to_java_util_date_and_ddl_matches():
    assert _java_type_from_sql_type('DATETIME', 'start_datetime') == 'String'
    assert _java_type_from_sql_type('DATE', 'start_date') == 'String'
    assert _guess_java_type('startDatetime', 'start_datetime') == 'String'
    assert _guess_java_type('startDate', 'start_date') == 'String'

    schema = schema_for('Schedule', [
        ('scheduleId', 'schedule_id', 'Long'),
        ('startDatetime', 'start_datetime', 'String'),
        ('startDate', 'start_date', 'String'),
        ('allDayYn', 'all_day_yn', 'String'),
    ], table='schedule', feature_kind='SCHEDULE')
    sql = ddl(schema)
    assert 'start_datetime DATETIME' in sql
    assert 'start_date DATE' in sql
    assert 'all_day_yn VARCHAR(1)' in sql
