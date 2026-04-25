from pathlib import Path

from app.validation.project_auto_repair import auto_repair_generated_project
from app.validation.post_generation_repair import _repair_timed_out_edit_endpoints


def test_search_fields_incomplete_adds_useyn_and_regdt_into_search_form(tmp_path: Path):
    jsp_path = tmp_path / 'src/main/webapp/WEB-INF/views/room/roomList.jsp'
    jsp_path.parent.mkdir(parents=True, exist_ok=True)
    jsp_path.write_text('<html><body><div>조회</div></body></html>', encoding='utf-8')
    report = {
        'static_issues': [
            {
                'type': 'search_fields_incomplete',
                'path': str(jsp_path.relative_to(tmp_path)).replace('\\', '/'),
                'repairable': True,
                'details': {'missing_fields': ['useYn', 'regDt']},
            }
        ]
    }
    result = auto_repair_generated_project(tmp_path, report)
    body = jsp_path.read_text(encoding='utf-8')
    assert result['changed_count'] == 1
    assert 'name="useYn"' in body
    assert 'name="regDt"' in body
    assert 'searchForm' in body


def test_repair_timed_out_edit_endpoints_rewrites_controller_and_writes_safe_jsp(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/demo/reservation/web/ReservationController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.demo.reservation.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.ui.Model;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n'
        '@RequestMapping("/reservation")\n'
        'public class ReservationController {\n'
        '    @GetMapping("/edit.do")\n'
        '    public String edit(Model model) throws Exception {\n'
        '        model.addAttribute("item", reservationService.selectReservationDetail(null));\n'
        '        return "reservation/reservationForm";\n'
        '    }\n'
        '}\n',
        encoding='utf-8',
    )
    runtime_validation = {
        'endpoint_smoke': {
            'status': 'failed',
            'results': [{'route': '/reservation/edit.do', 'ok': False, 'error': 'timed out'}],
        }
    }
    changed = _repair_timed_out_edit_endpoints(tmp_path, runtime_validation)
    body = controller.read_text(encoding='utf-8')
    jsp = (tmp_path / 'src/main/webapp/WEB-INF/views/reservation/reservationForm.jsp').read_text(encoding='utf-8')
    assert changed
    assert 'return "reservation/reservationForm";' in body
    assert 'reservationService' not in body
    assert 'AUTOPJ smoke-safe edit page' in jsp
