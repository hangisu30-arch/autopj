from pathlib import Path

from app.io.execution_core_apply import _patch_generated_jsp_assets, _patch_auth_sql_init_properties
from execution_core.project_patcher import patch_application_properties, write_database_initializer


class _ScheduleSchema:
    entity_var = "schedule"
    feature_kind = "CRUD"
    routes = {"calendar": "/schedule/calendar.do", "list": "/schedule/list.do"}


def test_patch_application_properties_prefers_initializer_over_spring_sql_init(tmp_path: Path):
    res = tmp_path / "src/main/resources"
    res.mkdir(parents=True, exist_ok=True)
    (res / "application.properties").write_text("", encoding="utf-8")

    patch_application_properties(tmp_path, "egovframework.demo", "jsp")

    body = (res / "application.properties").read_text(encoding="utf-8")
    assert "spring.sql.init.mode=never" in body
    assert "optional:classpath:schema.sql" in body
    assert "optional:classpath:data.sql" in body


def test_auth_sql_init_properties_follow_initializer_strategy(tmp_path: Path):
    props = tmp_path / "src/main/resources/application.properties"
    props.parent.mkdir(parents=True, exist_ok=True)
    _patch_auth_sql_init_properties(tmp_path)
    body = props.read_text(encoding="utf-8")
    assert "spring.sql.init.mode=never" in body
    assert "optional:classpath:login-schema.sql" in body
    assert "optional:classpath:login-data.sql" in body


def test_write_database_initializer_bootstraps_schema_and_data_resources(tmp_path: Path):
    path = write_database_initializer(tmp_path, "egovframework.demo")
    body = path.read_text(encoding="utf-8")
    assert 'new String[] {"schema.sql", "data.sql", "login-schema.sql", "login-data.sql"}' in body
    assert 'populator.addScript(resource);' in body


def test_patch_generated_jsp_assets_mirrors_css_and_js_to_static(tmp_path: Path):
    view = tmp_path / "src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp"
    view.parent.mkdir(parents=True, exist_ok=True)
    view.write_text('<html><head><meta charset="UTF-8"/></head><body><div>ok</div></body></html>', encoding="utf-8")

    report = _patch_generated_jsp_assets(
        tmp_path,
        ["src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp"],
        "Schedule",
        {"Schedule": _ScheduleSchema()},
    )

    common_css = tmp_path / report["common_css"]
    common_js = tmp_path / report["common_js"]
    schedule_css = tmp_path / report["schedule_css"]
    schedule_js = tmp_path / report["schedule_js"]
    static_common_css = tmp_path / "src/main/resources/static/css/common.css"
    static_common_js = tmp_path / "src/main/resources/static/js/common.js"
    static_schedule_css = tmp_path / "src/main/resources/static/css/schedule.css"
    static_schedule_js = tmp_path / "src/main/resources/static/js/schedule.js"

    assert common_css.exists() and static_common_css.exists()
    assert common_js.exists() and static_common_js.exists()
    assert schedule_css.exists() and static_schedule_css.exists()
    assert schedule_js.exists() and static_schedule_js.exists()
    assert common_css.read_text(encoding="utf-8") == static_common_css.read_text(encoding="utf-8")
    assert common_js.read_text(encoding="utf-8") == static_common_js.read_text(encoding="utf-8")
