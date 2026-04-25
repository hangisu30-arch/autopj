from pathlib import Path
from types import SimpleNamespace

from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair
from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_validator_detects_cert_login_jsp_missing_login_vo_property(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/service/vo/LoginVO.java',
        '''package egovframework.test.login.service.vo;
public class LoginVO {
    private String loginId;
    private String password;
    public String getLoginId(){ return loginId; }
    public void setLoginId(String loginId){ this.loginId = loginId; }
    public String getPassword(){ return password; }
    public void setPassword(String password){ this.password = password; }
}
''',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/login/certLogin.jsp',
        '''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<form>
  <input type="text" name="loginId" value="<c:out value='${item.loginId}'/>"/>
  <input type="text" name="userName" value="<c:out value='${item.userName}'/>"/>
</form>
''',
    )

    report = validate_generated_project(tmp_path, SimpleNamespace(frontend_key='jsp'), run_runtime=False)
    issues = [item for item in report['static_issues'] if item['type'] == 'jsp_vo_property_mismatch']
    assert issues
    assert issues[0]['details']['missing_props'] == ['userName']


def test_auto_repair_rewrites_cert_login_value_binding_when_name_prop_missing(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/login/service/vo/LoginVO.java',
        '''package egovframework.test.login.service.vo;
public class LoginVO {
    private String loginId;
    private String password;
    public String getLoginId(){ return loginId; }
    public void setLoginId(String loginId){ this.loginId = loginId; }
    public String getPassword(){ return password; }
    public void setPassword(String password){ this.password = password; }
}
''',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/login/certLogin.jsp'
    _write(
        jsp,
        '''<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<form>
  <input type="text" name="loginId" value="<c:out value='${item.loginId}'/>"/>
  <input type="text" name="userName" value="<c:out value='${item.userName}'/>"/>
</form>
''',
    )

    report = validate_generated_project(tmp_path, SimpleNamespace(frontend_key='jsp'), run_runtime=False)
    repair = apply_generated_project_auto_repair(tmp_path, report)
    assert repair['changed_count'] >= 1
    body = jsp.read_text(encoding='utf-8')
    assert '${item.userName}' not in body
    assert 'value=""' in body


def test_builtin_cert_login_template_avoids_missing_username_binding_when_schema_has_no_name_field():
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH, unified_auth=True, cert_login=True)
    jsp = builtin_file('jsp/login/certLogin.jsp', 'egovframework.test', schema)
    assert "${item.userName}" not in jsp
    assert 'name="userName"' in jsp
    assert 'name="loginId"' in jsp
