from pathlib import Path

from execution_core.builtin_crud import builtin_file, schema_for
from app.ui.generated_content_validator import validate_generated_content
from app.validation.post_generation_repair import _normalize_boolean_getters


def test_builtin_vo_uses_single_getter_for_boolean_property():
    schema = schema_for(
        'Schedule',
        [
            ('scheduleId', 'schedule_id', 'Long'),
            ('allDayYn', 'all_day_yn', 'Boolean'),
        ],
        table='schedule',
        feature_kind='SCHEDULE',
    )
    body = builtin_file('java/service/vo/ScheduleVO.java', 'egovframework.stest', schema)
    assert body is not None
    assert 'public Boolean getAllDayYn()' in body
    assert 'public Boolean isAllDayYn()' not in body


def test_validator_rejects_ambiguous_boolean_getters():
    body = '''package egovframework.stest.schedule.service.vo;

public class ScheduleVO {
    private Boolean allDayYn;

    public Boolean getAllDayYn() {
        return this.allDayYn;
    }

    public Boolean isAllDayYn() {
        return this.allDayYn;
    }
}
'''
    ok, reason = validate_generated_content(
        'src/main/java/egovframework/stest/schedule/service/vo/ScheduleVO.java',
        body,
        frontend_key='jsp',
    )
    assert ok is False
    assert 'allDayYn' in reason


def test_post_generation_repair_removes_is_getter_for_boolean_vo(tmp_path: Path):
    vo_path = tmp_path / 'src/main/java/egovframework/stest/schedule/service/vo/ScheduleVO.java'
    vo_path.parent.mkdir(parents=True, exist_ok=True)
    vo_path.write_text(
        '''package egovframework.stest.schedule.service.vo;

public class ScheduleVO {
    private Boolean allDayYn;

    public Boolean getAllDayYn() {
        return this.allDayYn;
    }

    public Boolean isAllDayYn() {
        return this.allDayYn;
    }
}
''',
        encoding='utf-8',
    )
    changed = _normalize_boolean_getters(tmp_path)
    body = vo_path.read_text(encoding='utf-8')
    assert 'src/main/java/egovframework/stest/schedule/service/vo/ScheduleVO.java' in changed
    assert 'public Boolean getAllDayYn()' in body
    assert 'public Boolean isAllDayYn()' not in body
