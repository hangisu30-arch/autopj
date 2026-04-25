from pathlib import Path

from app.validation.project_auto_repair import (
    _ensure_schema_column_comments,
    _repair_jsp_missing_route_reference,
    _repair_missing_view,
)


def test_repair_missing_register_view_rewrites_controller_to_existing_form(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.member.web;\n'
        'public class MemberController {\n'
        '  public String registerForm(){ return "member/register"; }\n'
        '}\n',
        encoding='utf-8',
    )
    form_jsp = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberForm.jsp'
    form_jsp.parent.mkdir(parents=True, exist_ok=True)
    form_jsp.write_text('<html>member form</html>', encoding='utf-8')

    changed = _repair_missing_view(
        controller,
        issue={'details': {'missing_view': 'member/register'}},
        project_root=tmp_path,
    )

    assert changed is True
    body = controller.read_text(encoding='utf-8')
    assert 'return "member/memberForm";' in body


def test_adminmember_jsp_route_repair_rewrites_controller_to_standard_routes(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/adminMember/web/AdminMemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.adminMember.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/adminMember")\n'
        'public class AdminMemberController {\n'
        '  @GetMapping("/login.do")\n'
        '  public String loginForm(){ return "adminMember/adminMemberForm"; }\n'
        '}\n',
        encoding='utf-8',
    )
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/adminMember/adminMemberList.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<a href="<c:url value="/adminMember/detail.do"/>">상세</a>'
        '<a href="<c:url value="/adminMember/form.do"/>">등록</a>'
        '<a href="<c:url value="/adminMember/delete.do"/>">삭제</a>',
        encoding='utf-8',
    )

    changed = _repair_jsp_missing_route_reference(
        jsp,
        issue={
            'details': {
                'missing_routes': [
                    '/adminMember/detail.do',
                    '/adminMember/form.do',
                    '/adminMember/delete.do',
                    '/adminMember/save.do',
                ],
                'discovered_routes': ['/adminMember/login.do'],
            }
        },
        project_root=tmp_path,
    )

    assert changed is True
    body = controller.read_text(encoding='utf-8')
    assert '@RequestMapping("/adminMember")' in body
    assert '@GetMapping("/detail.do")' in body
    assert '@GetMapping({"/register.do", "/form.do"})' in body
    assert '@GetMapping("/delete.do")' in body
    assert '@PostMapping({"/actionRegister.do", "/save.do"})' in body


def test_schema_comment_repair_syncs_mapper_columns_and_comments(tmp_path: Path):
    mapper = tmp_path / 'src/main/resources/egovframework/mapper/member/MemberMapper.xml'
    mapper.parent.mkdir(parents=True, exist_ok=True)
    mapper.write_text(
        '<mapper namespace="egovframework.test.member.service.mapper.MemberMapper">\n'
        '  <resultMap id="memberMap" type="egovframework.test.member.service.vo.MemberVO">\n'
        '    <id property="id" column="id"/>\n'
        '    <result property="memberId" column="member_id"/>\n'
        '    <result property="status" column="status"/>\n'
        '    <result property="requestParam" column="requestparam"/>\n'
        '  </resultMap>\n'
        '  <select id="selectMember" resultMap="memberMap">SELECT id, member_id, status, requestparam FROM tb_member</select>\n'
        '</mapper>\n',
        encoding='utf-8',
    )
    schema = tmp_path / 'src/main/resources/schema.sql'
    schema.parent.mkdir(parents=True, exist_ok=True)
    schema.write_text(
        'CREATE TABLE IF NOT EXISTS tb_member (\n'
        '  id VARCHAR(255),\n'
        '  member_id VARCHAR(255),\n'
        '  status VARCHAR(255),\n'
        '  requestparam VARCHAR(255)\n'
        ');\n',
        encoding='utf-8',
    )

    changed = _ensure_schema_column_comments(
        mapper,
        issue={
            'details': {
                'table': 'tb_member',
                'missing_comments': ['id', 'member_id', 'status', 'requestparam'],
                'mapper_columns': ['id', 'member_id', 'status', 'requestparam'],
                'schema_path': 'src/main/resources/schema.sql',
            }
        },
        project_root=tmp_path,
    )

    assert changed is True
    body = schema.read_text(encoding='utf-8').lower()
    assert "id varchar(255) comment 'id 컬럼'" in body
    assert "member_id varchar(255) comment 'member_id 컬럼'" in body
    assert "status varchar(255) comment 'status 컬럼'" in body
    assert "requestparam varchar(255) comment 'requestparam 컬럼'" in body
