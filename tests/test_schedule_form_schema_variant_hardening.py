from pathlib import Path
from types import SimpleNamespace

from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.project_patcher import write_schema_sql
from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair


def _cfg():
    return SimpleNamespace(frontend_key='jsp', backend_key='springboot')


def _schedule_schema():
    return schema_for(
        'Schedule',
        inferred_fields=[
            ('scheduleId', 'schedule_id', 'Long'),
            ('title', 'title', 'String'),
            ('content', 'content', 'String'),
            ('startDatetime', 'start_datetime', 'java.util.Date'),
            ('endDatetime', 'end_datetime', 'java.util.Date'),
            ('statusCd', 'status_cd', 'String'),
            ('priorityCd', 'priority_cd', 'String'),
            ('location', 'location', 'String'),
        ],
        feature_kind='SCHEDULE',
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_builtin_schedule_form_uses_single_form_for_delete_action():
    body = builtin_file('jsp/schedule/scheduleForm.jsp', 'egovframework.demo', _schedule_schema())
    assert body is not None
    assert body.count('<form') == 1
    assert 'formaction="<c:url value=' in body
    assert 'Delete</button>' in body


def test_write_schema_sql_keeps_common_variants_in_sync(tmp_path: Path):
    write_schema_sql(tmp_path, 'CREATE TABLE schedule (schedule_id BIGINT);')
    primary = tmp_path / 'src/main/resources/schema.sql'
    variant = tmp_path / 'src/main/resources/db/schema.sql'
    mysql_variant = tmp_path / 'src/main/resources/db/schema-mysql.sql'
    assert primary.exists()
    assert variant.exists()
    assert mysql_variant.exists()
    assert primary.read_text(encoding='utf-8') == variant.read_text(encoding='utf-8') == mysql_variant.read_text(encoding='utf-8')


def test_schema_conflict_and_nested_form_are_auto_repaired(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/demo/schedule/web/ScheduleController.java',
        '''package egovframework.demo.schedule.web;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
@Controller
@RequestMapping("/schedule")
public class ScheduleController {
  @GetMapping("/calendar.do") public String calendar(Model model) { return "schedule/scheduleCalendar"; }
}
''',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleForm.jsp',
        '''<html><body>
<form action="/schedule/save.do" method="post">
  <input type="hidden" name="scheduleId" value="1"/>
  <div class="autopj-form-actions">
    <form action="/schedule/remove.do" method="post">
      <input type="hidden" name="scheduleId" value="1"/>
      <button type="submit">삭제</button>
    </form>
  </div>
</form>
</body></html>''',
    )
    _write(tmp_path / 'src/main/resources/schema.sql', 'CREATE TABLE schedule (schedule_id BIGINT);\n')
    _write(tmp_path / 'src/main/resources/db/schema.sql', 'CREATE TABLE schedule (schedule_id VARCHAR(64));\n')

    report = validate_generated_project(tmp_path, _cfg(), include_runtime=False)
    codes = {item['code'] for item in report['issues']}
    assert 'nested_form' in codes
    assert 'schema_conflict' in codes or 'schema_variant_conflict' in codes

    repair = apply_generated_project_auto_repair(tmp_path, report)
    assert repair['changed_count'] >= 2

    repaired_report = validate_generated_project(tmp_path, _cfg(), include_runtime=False)
    repaired_codes = {item['code'] for item in repaired_report['issues']}
    assert 'nested_form' not in repaired_codes
    assert 'schema_conflict' not in repaired_codes
    assert 'schema_variant_conflict' not in repaired_codes

    form_body = (tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleForm.jsp').read_text(encoding='utf-8')
    assert form_body.count('<form') == 1
    assert 'formaction="/schedule/remove.do"' in form_body
    primary = (tmp_path / 'src/main/resources/schema.sql').read_text(encoding='utf-8')
    variant = (tmp_path / 'src/main/resources/db/schema.sql').read_text(encoding='utf-8')
    assert primary == variant
