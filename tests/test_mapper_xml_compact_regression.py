from execution_core.builtin_crud import builtin_file, infer_schema_from_plan, schema_for


def test_explicit_contract_target_does_not_merge_other_paragraph_columns():
    plan = {
        "requirements": """
테이블명: tb_member
컬럼: member_id, member_pw, member_nm, approval_status

보안 확장 안내:
컬럼: security_type, security_key, security_iv, security_algorithm, security_digest
        """
    }
    schema = infer_schema_from_plan(plan)
    cols = [col for _prop, col, _jt in schema.fields]
    assert schema.table == 'tb_member'
    assert cols == ['member_id', 'member_pw', 'member_nm', 'approval_status']
    assert 'security_type' not in cols
    assert 'security_key' not in cols


def test_builtin_mapper_uses_base_column_list_fragment():
    schema = schema_for(
        'TbMember',
        inferred_fields=[
            ('memberId', 'member_id', 'String'),
            ('memberPw', 'member_pw', 'String'),
            ('memberNm', 'member_nm', 'String'),
            ('email', 'email', 'String'),
            ('mobileNo', 'mobile_no', 'String'),
            ('approvalStatus', 'approval_status', 'String'),
            ('useYn', 'use_yn', 'String'),
            ('regDt', 'reg_dt', 'String'),
            ('modDt', 'mod_dt', 'String'),
        ],
        table='tb_member',
        strict_fields=True,
    )
    xml = builtin_file('mapper/tbmember/TbMemberMapper.xml', 'egovframework.test.tbMember', schema)
    assert '<sql id="BaseColumnList">' in xml
    assert xml.count('<include refid="BaseColumnList"/>') >= 2
    assert xml.count('SELECT member_id') == 0
