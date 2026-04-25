from pathlib import Path

from app.ui.state import ProjectConfig
from app.validation.project_manifest import build_generation_manifest
from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_generated_project_validator_detects_core_regressions(tmp_path: Path):
    _write(tmp_path / 'pom.xml', '<project/>')
    _write(
        tmp_path / 'src/main/java/egovframework/demo/mysql/web/MysqlController.java',
        '''package egovframework.demo.mysql.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.*;
@Controller
@RequestMapping("/mysql")
public class MysqlController {
  @GetMapping("/list.do") public String list() { return "mysql/mysqlList"; }
  @PostMapping("/delete.do") public String delete(@RequestParam("id") Long id) { return "redirect:/mysql/list.do"; }
}
''',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/demo/mysql/service/vo/MysqlVO.java',
        '''package egovframework.demo.mysql.service.vo;
public class MysqlVO {
  private String id;
  private Boolean allDayYn;
  public String getId() { return id; }
  public void setId(String id) { this.id = id; }
  public Boolean getAllDayYn() { return allDayYn; }
  public Boolean isAllDayYn() { return allDayYn; }
}
''',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/demo/mysql/service/mapper/MysqlMapper.java',
        '''package egovframework.demo.mysql.service.mapper;
import org.apache.ibatis.annotations.Param;
public interface MysqlMapper { void deleteMysql(@Param("id") String id); }
''',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/mysql/mysqlForm.jsp',
        '<html><body><form><input name="startDate" type="text"/><form><button>bad</button></form></form></body></html>',
    )
    _write(
        tmp_path / 'src/main/resources/schema.sql',
        'CREATE TABLE users (id VARCHAR(64), room_name VARCHAR(50));',
    )
    _write(
        tmp_path / 'src/main/resources/db/schema.sql',
        'CREATE TABLE users (id INT, name VARCHAR(50));',
    )

    cfg = ProjectConfig(project_name='demo', frontend_key='jsp', backend_key='egov_spring', database_key='mysql')
    manifest = build_generation_manifest(tmp_path, cfg=cfg, report=None, file_ops=None, use_execution_core=False)
    report = validate_generated_project(tmp_path, cfg=cfg, manifest=manifest, run_runtime=True)

    codes = {item['code'] for item in report['issues']}
    assert 'missing_service_interface' in codes
    assert 'missing_service_impl' in codes
    assert 'missing_view_jsp' in codes
    assert 'missing_mapper_xml' in codes
    assert 'ambiguous_boolean_getter' in codes
    assert 'controller_vo_type_mismatch' in codes
    assert 'missing_delete_ui' in codes
    assert 'nested_form' in codes
    assert 'temporal_input_type_mismatch' in codes
    assert 'schema_conflict' in codes
    assert report['runtime_smoke']['skipped']


def test_generated_project_auto_repair_fixes_repairable_jsp_and_vo_issues(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/demo/sample/service/vo/SampleVO.java',
        '''package egovframework.demo.sample.service.vo;
public class SampleVO {
  private Boolean allDayYn;
  public Boolean getAllDayYn() { return allDayYn; }
  public Boolean isAllDayYn() { return allDayYn; }
}
''',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/sample/sampleForm.jsp'
    _write(jsp, '<html><body><form><input name="startDate" type="text"/><form><button>bad</button></form></form></body></html>')

    validation_report = {
        'issues': [
            {'code': 'ambiguous_boolean_getter', 'path': 'src/main/java/egovframework/demo/sample/service/vo/SampleVO.java', 'repairable': True, 'details': {'property': 'allDayYn'}},
            {'code': 'temporal_input_type_mismatch', 'path': 'src/main/webapp/WEB-INF/views/sample/sampleForm.jsp', 'repairable': True, 'details': {'field': 'startDate'}},
            {'code': 'nested_form', 'path': 'src/main/webapp/WEB-INF/views/sample/sampleForm.jsp', 'repairable': True, 'details': {}},
            {'code': 'missing_delete_ui', 'path': 'src/main/webapp/WEB-INF/views/sample/sampleForm.jsp', 'repairable': True, 'details': {'delete_routes': ['/sample/delete.do'], 'field': 'sampleId'}},
        ]
    }

    repair = apply_generated_project_auto_repair(tmp_path, validation_report)
    assert repair['changed_count'] >= 2
    vo_body = (tmp_path / 'src/main/java/egovframework/demo/sample/service/vo/SampleVO.java').read_text(encoding='utf-8')
    jsp_body = jsp.read_text(encoding='utf-8')
    assert 'isAllDayYn()' not in vo_body
    assert 'type="date"' in jsp_body
    assert '/sample/delete.do' in jsp_body
