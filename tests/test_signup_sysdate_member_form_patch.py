from pathlib import Path

from app.validation.project_auto_repair import _rewrite_signup_jsp_to_safe_routes
from app.io.execution_core_apply import _rewrite_form_jsp_from_schema


class DummySchema:
    def __init__(self):
        self.entity = 'Member'
        self.entity_var = 'member'
        self.id_prop = 'memberId'
        self.id_column = 'member_id'
        self.routes = {
            'save': '/member/save.do',
            'list': '/member/list.do',
            'form': '/member/form.do',
        }
        self.fields = [
            ('memberId', 'member_id', 'String'),
            ('memberName', 'member_name', 'String'),
            ('roleCd', 'role_cd', 'String'),
            ('useYn', 'use_yn', 'String'),
            ('regDt', 'reg_dt', 'String'),
            ('sysdateValue', 'sysdate_value', 'String'),
        ]
        self.field_comments = {}


def test_signup_rewrite_does_not_emit_empty_hidden_values(tmp_path: Path):
    root = tmp_path
    jsp = root / 'src/main/webapp/WEB-INF/views/signup/signupForm.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<html></html>', encoding='utf-8')
    controller = root / 'src/main/java/demo/web/SignupController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text('@RequestMapping("/signup/save.do") class X {}', encoding='utf-8')

    # provide VO inferred by repair path
    vo = root / 'src/main/java/demo/service/vo/SignupVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text('''
package demo.service.vo;
public class SignupVO {
  private String loginId;
  private String loginPassword;
  private String roleCd;
}
''', encoding='utf-8')

    assert _rewrite_signup_jsp_to_safe_routes(jsp, root)
    text = jsp.read_text(encoding='utf-8')
    assert 'value=""' not in text
    assert 'name="roleCd"' in text


def test_form_rewrite_keeps_role_useyn_regdt_and_uses_date_for_sysdate(tmp_path: Path):
    root = tmp_path
    rel = 'src/main/webapp/WEB-INF/views/member/memberForm.jsp'
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<html></html>', encoding='utf-8')

    assert _rewrite_form_jsp_from_schema(root, rel, DummySchema())
    text = path.read_text(encoding='utf-8')
    assert 'name="roleCd"' in text
    assert 'name="useYn"' in text
    assert 'name="regDt"' in text
    assert 'name="sysdateValue"' in text
    # rendered as date input, not text
    assert 'type="date" name="sysdateValue"' in text or 'name="sysdateValue"' in text and 'type="date"' in text
