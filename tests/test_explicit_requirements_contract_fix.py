from types import SimpleNamespace

from app.engine.analysis.schema_parser import SchemaParser
from app.validation.backend_compile_repair import _local_contract_repair
from app.validation.post_generation_repair import _normalize_jsp_layout_includes, _validate_jsp_include_consistency
from app.ui.fallback_builder import build_builtin_fallback_content


def _write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_schema_parser_explicit_columns_keep_single_preferred_pk():
    parser = SchemaParser()
    req = '''
DB 규칙:
- 테이블명은 schedule 로 사용한다
- 최소 컬럼은 아래를 사용한다
  - schedule_id
  - title
  - writer_id
  - reg_dt
'''
    tables = parser.infer_from_requirements(req, ['schedule'])
    assert len(tables) == 1
    fields = {f.column: f for f in tables[0].fields}
    assert fields['schedule_id'].pk is True
    assert fields['writer_id'].pk is False


def test_compile_repair_rebuilds_malformed_vo_from_bundle_specs(tmp_path):
    project_root = tmp_path
    vo_rel = 'src/main/java/egovframework/test12/schedule/service/vo/ScheduleVO.java'
    controller_rel = 'src/main/java/egovframework/test12/schedule/web/ScheduleController.java'

    _write(project_root / vo_rel, '''package egovframework.test12.schedule.service.vo;\n\npublic class ScheduleVO {\n    private String title;\n    @DateTimeFormat(pattern =)\n    private ;\n}\n''')
    _write(project_root / controller_rel, 'package egovframework.test12.schedule.web; public class ScheduleController {}')

    manifest = {
        controller_rel: {
            'spec': '''DB 규칙:\n- 테이블명은 schedule 로 사용한다\n- 최소 컬럼은 아래를 사용한다\n  - schedule_id\n  - title\n  - start_datetime\n  - end_datetime\n  - use_yn\n'''
        }
    }
    runtime_report = {
        'compile': {
            'errors': [
                {'path': vo_rel, 'message': '<identifier> expected'},
                {'path': vo_rel, 'message': 'illegal start of type'},
            ]
        }
    }

    changed = _local_contract_repair(project_root, SimpleNamespace(project_name='test12'), manifest, [vo_rel], runtime_report)
    assert any(item['path'] == vo_rel for item in changed)
    body = (project_root / vo_rel).read_text(encoding='utf-8')
    assert 'public class ScheduleVO' in body
    assert 'private String scheduleId;' in body
    assert 'private String startDatetime;' in body
    assert 'private ;' not in body


def test_jsp_include_normalizer_repairs_common_shortcuts(tmp_path):
    project_root = tmp_path
    header = project_root / 'src/main/webapp/WEB-INF/views/common/header.jsp'
    leftnav = project_root / 'src/main/webapp/WEB-INF/views/common/leftNav.jsp'
    jsp_rel = 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'
    jsp = project_root / jsp_rel

    _write(header, '<div>header</div>')
    _write(leftnav, '<div>nav</div>')
    _write(jsp, '<%@ include file="/common/header.jsp" %>\n<%@ include file="common/leftNav.jsp" %>\n<div>ok</div>')

    changed = _normalize_jsp_layout_includes(project_root, [jsp_rel])
    assert jsp_rel in changed
    updated = jsp.read_text(encoding='utf-8')
    assert '/WEB-INF/views/common/header.jsp' in updated
    assert '/WEB-INF/views/common/leftNav.jsp' in updated
    issues = _validate_jsp_include_consistency(project_root, [jsp_rel])
    assert issues == []


def test_fallback_builder_uses_explicit_requirement_bullets_for_vo_fields():
    spec = """DB 규칙:
- 테이블명은 schedule 로 사용한다
- 최소 컬럼은 아래를 사용한다
  - schedule_id
  - title
  - owner_empno
  - start_datetime
  - end_datetime
  - use_yn
"""
    body = build_builtin_fallback_content('src/main/java/egovframework/test3/schedule/service/vo/ScheduleVO.java', spec, project_name='test3')
    assert 'private String scheduleId;' in body
    assert 'private String ownerEmpno;' in body
    assert 'private String startDatetime;' in body
    assert 'private String endDatetime;' in body
    assert 'private String useYn;' in body


def test_compile_repair_expands_related_bundle_for_broken_vo_to_use_controller_spec(tmp_path):
    project_root = tmp_path
    vo_rel = 'src/main/java/egovframework/test12/schedule/service/vo/ScheduleVO.java'
    controller_rel = 'src/main/java/egovframework/test12/schedule/web/ScheduleController.java'

    _write(project_root / vo_rel, """package egovframework.test12.schedule.service.vo;

public class ScheduleVO {
    private String title;
    @DateTimeFormat(pattern =)
    private ;
}
""")
    _write(project_root / controller_rel, 'package egovframework.test12.schedule.web; public class ScheduleController {}')

    manifest = {
        controller_rel: {
            'spec': """DB 규칙:
- 테이블명은 schedule 로 사용한다
- 최소 컬럼은 아래를 사용한다
  - schedule_id
  - owner_empno
  - start_datetime
  - end_datetime
"""
        }
    }
    runtime_report = {
        'compile': {
            'errors': [
                {'path': vo_rel, 'message': '<identifier> expected'},
                {'path': vo_rel, 'message': 'illegal start of type'},
            ]
        }
    }

    changed = _local_contract_repair(project_root, SimpleNamespace(project_name='test12'), manifest, [vo_rel], runtime_report)
    assert any(item['path'] == vo_rel for item in changed)
    body = (project_root / vo_rel).read_text(encoding='utf-8')
    assert 'private String ownerEmpno;' in body
    assert 'private String startDatetime;' in body
    assert 'private ;' not in body


def test_authoritative_analysis_field_specs_normalize_sql_like_types():
    from execution_core.builtin_crud import _authoritative_analysis_field_specs

    plan = {
        'domains': [
            {
                'name': 'schedule',
                'entity_name': 'Schedule',
                'source_table': 'schedule',
                'fields': [
                    {'name': 'scheduleId', 'column': 'schedule_id', 'java_type': 'bigint'},
                    {'name': 'title', 'column': 'title', 'java_type': 'varchar(200)'},
                    {'name': 'startDatetime', 'column': 'start_datetime', 'java_type': 'datetime'},
                    {'name': 'useYn', 'column': 'use_yn', 'java_type': 'varchar(1)'},
                ],
            }
        ]
    }

    fields = {col: jt for _prop, col, jt in _authoritative_analysis_field_specs(plan, 'Schedule')}
    assert fields['schedule_id'] == 'String'
    assert fields['title'] == 'String'
    assert fields['start_datetime'] == 'String'
    assert fields['use_yn'] == 'String'


def test_fallback_builder_skips_java_keyword_columns_from_explicit_requirements():
    spec = """DB 규칙:
- 테이블명은 sample 로 사용한다
- 최소 컬럼은 아래를 사용한다
  - class
  - title
"""
    body = build_builtin_fallback_content('src/main/java/egovframework/test3/sample/service/vo/SampleVO.java', spec, project_name='test3')
    assert 'private String class;' not in body
    assert 'private String title;' in body
