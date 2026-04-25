from pathlib import Path
from types import SimpleNamespace

from app.engine.analysis.requirement_parser import RequirementParser
from app.validation.global_validator import validate_generation_context
from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_requirement_parser_ignores_entry_only_domain_tokens():
    hints = RequirementParser().parse("index 화면과 main 화면을 만들고 예약 관리도 만든다")
    assert 'index' not in hints.domain_candidates
    assert 'main' not in hints.domain_candidates
    assert 'reservation' in hints.domain_candidates


def test_global_validator_rejects_entry_only_domain_with_crud_artifacts():
    analysis = {
        'project': {'base_package': 'egovframework.demo', 'frontend_mode': 'jsp'},
        'ir_version': '1.0',
        'domains': [
            {
                'name': 'index',
                'feature_kind': 'crud',
                'pages': ['list', 'detail', 'form'],
                'api_endpoints': ['GET /api/index', 'POST /api/index'],
                'file_generation_plan': {
                    'backend': ['vo', 'service', 'service_impl', 'controller'],
                    'frontend': ['list_jsp', 'detail_jsp', 'form_jsp'],
                },
                'forbidden_artifacts': [],
                'ir': {
                    'classification': {'primaryPattern': 'list'},
                    'mainEntry': {'route': '/index/list.do', 'jsp': 'index/indexList.jsp'},
                    'dataModel': {'fields': [{'name': 'id'}]},
                    'backendArtifacts': {'controller': 'IndexController.java'},
                    'frontendArtifacts': {'mainJsp': 'index/indexList.jsp'},
                    'validationRules': {},
                },
            }
        ],
    }
    report = validate_generation_context(analysis, frontend_key='jsp')
    joined = '\n'.join(report['errors'])
    assert 'entry-only domain must not generate CRUD/service/vo artifacts' in joined


def test_generated_project_validator_and_auto_repair_fix_index_controller(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/rtest/index/web/IndexController.java'
    _write(
        controller,
        '''package egovframework.rtest.index.web;

import egovframework.rtest.index.service.IndexService;
import egovframework.rtest.index.service.vo.IndexVO;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;

@Controller
@RequestMapping("/index")
public class IndexController {
    private final IndexService indexService;
    public IndexController(IndexService indexService) { this.indexService = indexService; }

    @GetMapping("/list.do")
    public String list(IndexVO indexVO) {
        return "index/indexList";
    }
}
''',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/rtest/reservation/web/ReservationController.java',
        '''package egovframework.rtest.reservation.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
@Controller
public class ReservationController {
  @GetMapping("/reservation/calendar.do")
  public String calendar() { return "reservation/reservationCalendar"; }
}
''',
    )

    cfg = SimpleNamespace(frontend_key='jsp')
    report = validate_generated_project(tmp_path, cfg=cfg, manifest=None, run_runtime=False)
    codes = {item['code'] for item in report['issues']}
    assert 'index_entrypoint_miswired' in codes
    assert 'index_entrypoint_crud_leak' in codes

    repair = apply_generated_project_auto_repair(tmp_path, {'issues': report['issues']})
    assert repair['changed_count'] >= 1
    body = controller.read_text(encoding='utf-8')
    assert 'IndexVO' not in body
    assert 'IndexService' not in body
    assert '@GetMapping({"/", "/index.do"})' in body
    assert 'redirect:/reservation/calendar.do' in body
