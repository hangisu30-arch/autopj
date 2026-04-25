from app.io.execution_core_apply import _build_common_js, _build_autopj_theme_css
from execution_core.builtin_crud import builtin_file, schema_for


def test_vo_has_datetime_format_annotations_for_temporal_fields():
    schema = schema_for(
        'Schedule',
        [
            ('scheduleId', 'schedule_id', 'Long'),
            ('startDatetime', 'start_datetime', 'java.util.Date'),
            ('endDate', 'end_date', 'java.util.Date'),
        ],
        table='schedule',
        feature_kind='SCHEDULE',
    )
    body = builtin_file('java/service/vo/ScheduleVO.java', 'egovframework.demo', schema)
    assert body is not None
    assert 'import org.springframework.format.annotation.DateTimeFormat;' in body
    assert "@DateTimeFormat(pattern = \"yyyy-MM-dd'T'HH:mm:ss\")" in body
    assert '@DateTimeFormat(pattern = "yyyy-MM-dd")' in body
    assert 'private Date startDatetime;' in body
    assert 'private Date endDate;' in body


def test_common_nav_assets_support_dynamic_active_state():
    js = _build_common_js()
    css = _build_autopj_theme_css()
    assert 'markActiveNav' in js
    assert '.autopj-header__link, .autopj-leftnav__link' in js
    assert '.autopj-header__link.is-active' in css
    assert '.autopj-leftnav__link.is-active' in css
