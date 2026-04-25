from execution_core.builtin_crud import infer_schema_from_plan, schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH, FEATURE_KIND_CRUD


def test_schema_for_collapses_duplicate_semantic_columns_without_suffixing():
    schema = schema_for(
        'Member',
        [
            ('memberId', 'member_id', 'String'),
            ('loginId', 'login_id', 'String'),
            ('memberName', 'member_name', 'String'),
            ('useYn', 'use_yn', 'String'),
            ('memberStatusCd', 'member_status_cd', 'String'),
            ('memberId', 'member_id', 'String'),
            ('loginId', 'login_id', 'String'),
            ('memberName', 'member_name', 'String'),
            ('useYn', 'use_yn', 'String'),
            ('memberStatusCd', 'member_status_cd', 'String'),
            ('regDt', 'reg_dt', 'String'),
        ],
        table='TB_MEMBER',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )
    assert [col for _prop, col, _jt in schema.fields] == [
        'member_id', 'login_id', 'member_name', 'use_yn', 'member_status_cd', 'reg_dt'
    ]
    assert not any(col.endswith('_2') or col.endswith('_3') for _prop, col, _jt in schema.fields)


def test_auth_schema_recognizes_login_password_without_injecting_generic_password():
    schema = schema_for(
        'Login',
        [
            ('loginId', 'login_id', 'String'),
            ('loginPassword', 'login_password', 'String'),
        ],
        table='TB_MEMBER',
        feature_kind=FEATURE_KIND_AUTH,
        strict_fields=True,
    )
    columns = [col for _prop, col, _jt in schema.fields]
    assert 'login_id' in columns
    assert 'login_password' in columns
    assert 'password' not in columns


def test_infer_schema_from_plan_dedupes_repeated_requirement_columns_across_text_blobs():
    plan = {
        'requirements_text': '''
기능: 로그인과 회원가입과 회원관리
테이블명: TB_MEMBER
컬럼: member_id, login_id, member_name, use_yn, member_status_cd, reg_dt
''',
        'tasks': [
            {'content': '회원관리 화면 컬럼: member_id, login_id, member_name, use_yn, member_status_cd, reg_dt'},
            {'content': '회원가입 입력 컬럼: member_id, login_id, member_name, use_yn, member_status_cd, reg_dt'},
        ],
    }
    schema = infer_schema_from_plan(plan)
    columns = [col for _prop, col, _jt in schema.fields]
    assert columns == ['member_id', 'login_id', 'member_name', 'use_yn', 'member_status_cd', 'reg_dt']
    assert not any(col.endswith('_2') or col.endswith('_3') for col in columns)
