from execution_core.builtin_crud import infer_schema_from_plan, _extract_explicit_contract_for_target


REQ = '''
회원가입/로그인/회원관리 기능을 만든다.
관리자는 전체 회원을 볼 수 있고 일반 사용자는 본인 데이터만 볼 수 있다.
승인 화면도 필요하다.

DB 규칙:
- 테이블명: tb_member
- 컬럼 명:
  - member_id (회원ID, varchar(64), Primary Key)
  - member_name (회원명, varchar(100), not null)
  - password (비밀번호, varchar(200), not null)
  - approval_status (승인상태, varchar(20), nullable)

통합인증/인증서 로그인 설명:
- security_key
- security_iv
- security_algorithm
'''


def test_extract_explicit_contract_prefers_scoped_table_contract_over_whole_body_noise():
    table, specs, entries = _extract_explicit_contract_for_target(REQ, entity='TbMember', table='tb_member')
    assert table == 'tb_member'
    assert [col for _prop, col, _jt in specs] == ['member_id', 'member_name', 'password', 'approval_status']
    assert all(str(entry.get('col') or '') not in {'security_key', 'security_iv', 'security_algorithm'} for entry in entries)


def test_infer_schema_marks_admin_and_approval_routes_when_required():
    schema = infer_schema_from_plan({'requirements_text': REQ, 'schema_text': REQ, 'tasks': []})
    assert schema.table == 'tb_member'
    assert schema.approval_required is True
    assert schema.admin_required is True
    assert schema.routes['approval'].endswith('/approval/list.do')
    assert schema.routes['admin'].endswith('/admin/list.do')
    assert schema.views['approval'].endswith('ApprovalList')
    assert schema.views['admin'].endswith('AdminList')
    assert [col for _prop, col, _jt in schema.fields] == ['member_id', 'member_name', 'password', 'approval_status']
