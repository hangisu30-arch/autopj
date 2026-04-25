from pathlib import Path
from types import SimpleNamespace

from app.validation.generated_project_validator import validate_generated_project
from app.validation.backend_compile_repair import _local_contract_repair
from execution_core.builtin_crud import schema_for


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _cfg():
    return SimpleNamespace(frontend_key="jsp", backend_key="springboot", project_name="demo")


def test_schema_for_normalizes_lowercase_entity_to_pascal_case():
    schema = schema_for('user')
    assert schema.entity == 'User'
    assert schema.entity_var == 'user'
    assert schema.table == 'user'


def test_generated_project_validator_ignores_infra_and_stray_calendar_dirs(tmp_path: Path):
    for rel in [
        'src/main/webapp/WEB-INF/views/generic/genericCalendar.jsp',
        'src/main/webapp/WEB-INF/views/loginInterceptor/loginInterceptorCalendar.jsp',
        'src/main/webapp/WEB-INF/views/views/viewsCalendar.jsp',
        'src/main/webapp/WEB-INF/views/webMvcConfig/webMvcConfigCalendar.jsp',
        'src/main/webapp/WEB-INF/views/user/userCalendar.jsp',
    ]:
        _write(tmp_path / rel, '<html><body>placeholder</body></html>')

    report = validate_generated_project(tmp_path, _cfg(), include_runtime=False)
    messages = [item['message'] for item in report['static_issues']]
    assert not any('controller missing for generic' in msg for msg in messages)
    assert not any('controller missing for loginInterceptor' in msg for msg in messages)
    assert not any('controller missing for views' in msg for msg in messages)
    assert not any('controller missing for webMvcConfig' in msg for msg in messages)
    assert not any('controller missing for user' in msg for msg in messages)


def test_generated_project_validator_still_flags_schedule_calendar_without_controller(tmp_path: Path):
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp', '<html><body>schedule</body></html>')
    _write(tmp_path / 'src/main/java/egovframework/demo/placeholder/Keep.java', 'package egovframework.demo.placeholder; public class Keep {}')

    report = validate_generated_project(tmp_path, _cfg(), include_runtime=False)
    messages = [item['message'] for item in report['static_issues']]
    assert any('controller missing for schedule' in msg for msg in messages)


def test_local_contract_repair_realigns_public_type_after_builtin_fallback(tmp_path: Path, monkeypatch):
    rel = 'src/main/java/egovframework/test/user/service/vo/UserVO.java'
    target = tmp_path / rel
    _write(target, '''package egovframework.test.user.service.vo;
public class broken {}
''')

    def _fake_builtin(path: str, spec: str, project_name: str = '') -> str:
        return '''package egovframework.test.user.service.vo;
public class userVO {}
'''

    monkeypatch.setattr('app.validation.backend_compile_repair.build_builtin_fallback_content', _fake_builtin)

    changed = _local_contract_repair(
        tmp_path,
        _cfg(),
        manifest={},
        targets=[rel],
        runtime_report={'compile': {'errors': []}},
    )

    body = target.read_text(encoding='utf-8')
    assert 'public class UserVO' in body
    assert any(item['reason'] == 'public type realigned after builtin fallback' for item in changed)
