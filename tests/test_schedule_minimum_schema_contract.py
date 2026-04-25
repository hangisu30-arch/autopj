from execution_core.builtin_crud import ddl, infer_schema_from_plan, schema_for


def test_schedule_schema_defaults_enforce_minimum_required_columns():
    schema = schema_for('Schedule', [('title', 'title', 'String')], table='schedule', feature_kind='SCHEDULE')
    cols = [col for _prop, col, _jt in schema.fields]
    assert cols[:13] == [
        'schedule_id', 'title', 'content', 'start_datetime', 'end_datetime', 'all_day_yn',
        'status_cd', 'priority_cd', 'location', 'writer_id', 'use_yn', 'reg_dt', 'upd_dt'
    ]
    sql = ddl(schema)
    assert 'CREATE TABLE IF NOT EXISTS schedule' in sql
    assert 'schedule_id VARCHAR(64) NOT NULL PRIMARY KEY' in sql
    assert 'content TEXT' in sql
    assert 'all_day_yn VARCHAR(1)' in sql
    assert 'use_yn VARCHAR(1)' in sql


def test_schedule_schema_defaults_upgrade_weak_string_id_and_dates():
    schema = schema_for(
        'Schedule',
        [
            ('scheduleId', 'schedule_id', 'String'),
            ('title', 'title', 'String'),
            ('startDatetime', 'start_datetime', 'String'),
            ('endDatetime', 'end_datetime', 'String'),
        ],
        table='schedule',
        feature_kind='SCHEDULE',
    )
    type_map = {col: jt for _prop, col, jt in schema.fields}
    assert type_map['schedule_id'] == 'String'
    assert type_map['start_datetime'] == 'String'
    assert type_map['end_datetime'] == 'String'


def test_infer_schema_from_plan_schedule_requirements_keep_schedule_table_and_minimum_columns():
    plan = {
        'tasks': [
            {'path': 'src/main/java/egovframework/demo/schedule/web/ScheduleController.java'},
        ],
        'requirements_text': 'DB 규칙: 테이블명은 schedule 로 사용한다. 최소 컬럼은 schedule_id, title, content, start_datetime, end_datetime, all_day_yn, status_cd, priority_cd, location, writer_id, use_yn, reg_dt, upd_dt 를 사용한다.',
    }
    schema = infer_schema_from_plan(plan)
    assert schema.table == 'schedule'
    cols = {col for _prop, col, _jt in schema.fields}
    assert {
        'schedule_id', 'title', 'content', 'start_datetime', 'end_datetime', 'all_day_yn',
        'status_cd', 'priority_cd', 'location', 'writer_id', 'use_yn', 'reg_dt', 'upd_dt'
    }.issubset(cols)
