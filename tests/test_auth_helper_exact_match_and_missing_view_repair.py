from pathlib import Path

from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH
from app.validation.post_generation_repair import _materialize_missing_controller_views


def test_builtin_file_keeps_cert_login_helper_distinct_from_main_login_service():
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH, unified_auth=True, cert_login=True)
    body = builtin_file('java/service/CertLoginService.java', 'egovframework.test.login', schema)

    assert 'public interface CertLoginService' in body
    assert 'authenticateCertificate(' in body
    assert 'public interface LoginService' not in body


def test_builtin_file_keeps_integrated_auth_helper_distinct_from_main_login_service_impl():
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH, unified_auth=True, cert_login=True)
    body = builtin_file('java/service/impl/IntegratedAuthServiceImpl.java', 'egovframework.test.login', schema)

    assert 'public class IntegratedAuthServiceImpl implements IntegratedAuthService' in body
    assert 'import egovframework.test.login.service.vo.LoginVO;' in body
    assert 'login.integratedAuth.service.vo' not in body
    assert 'public class LoginServiceImpl' not in body


def test_materialize_missing_controller_views_creates_detail_jsp_from_controller_returns(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/schedule/web/ScheduleController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.schedule.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n'
        '@RequestMapping("/schedule")\n'
        'public class ScheduleController {\n'
        '  @GetMapping("/view.do")\n'
        '  public String view() {\n'
        '    return "schedule/scheduleDetail";\n'
        '  }\n'
        '}\n',
        encoding='utf-8',
    )
    form = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleForm.jsp'
    form.parent.mkdir(parents=True, exist_ok=True)
    form.write_text(
        '<input name="scheduleId"/>\n<input name="title"/>\n<textarea name="content"></textarea>',
        encoding='utf-8',
    )

    changed = _materialize_missing_controller_views(tmp_path)

    detail_jsp = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleDetail.jsp'
    assert detail_jsp.exists()
    body = detail_jsp.read_text(encoding='utf-8')
    assert 'scheduleId' in body
    assert 'title' in body
    assert 'content' in body
    assert 'src/main/webapp/WEB-INF/views/schedule/scheduleDetail.jsp' in changed
