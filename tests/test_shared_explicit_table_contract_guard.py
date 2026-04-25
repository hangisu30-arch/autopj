from pathlib import Path

from app.io.execution_core_apply import _augment_schema_map_with_auth, _write_auth_sql_artifacts
from app.ui.state import ProjectConfig
from execution_core.builtin_crud import ddl, infer_schema_from_plan

REQ = '''
기능: 로그인, 회원가입, 회원관리
회원가입 후 로그인되어야 하고 기존 로그인과 연동되어야 한다.
로그인, 회원가입, 회원관리는 같은 테이블과 같은 컬럼 체계를 사용한다.
테이블명:
- TB_MEMBER

테이블 설명(comment):
- 회원 정보 관리 테이블

컬럼은 최소 아래와 같이 생성하라.
1. member_id
- 타입: VARCHAR(50)
- 제약: PRIMARY KEY
- comment: 회원 고유 ID

2. login_id
- 타입: VARCHAR(100)
- 제약: NOT NULL, UNIQUE
- comment: 로그인 아이디

3. login_password
- 타입: VARCHAR(255)
- 제약: NOT NULL
- comment: 로그인 비밀번호

4. member_name
- 타입: VARCHAR(100)
- 제약: NOT NULL
- comment: 회원명

5. email
- 타입: VARCHAR(200)
- 제약: NULL 허용 가능
- comment: 이메일

6. phone_no
- 타입: VARCHAR(30)
- 제약: NULL 허용 가능
- comment: 휴대폰번호

7. use_yn
- 타입: CHAR(1)
- 제약: NOT NULL
- 기본값: 'Y'
- comment: 사용 여부

8. member_status_cd
- 타입: VARCHAR(20)
- 제약: NOT NULL
- 기본값: 'ACTIVE'
- comment: 회원 상태 코드

9. last_login_dt
- 타입: DATETIME
- 제약: NULL 허용 가능
- comment: 최종 로그인 일시

10. reg_dt
- 타입: DATETIME
- 제약: NOT NULL
- comment: 등록 일시

11. upd_dt
- 타입: DATETIME
- 제약: NULL 허용 가능
- comment: 수정 일시
'''


def _member_schema():
    return infer_schema_from_plan({'requirements_text': REQ, 'database_type': 'mysql'})


def test_shared_auth_request_keeps_explicit_member_table_contract():
    schema = _member_schema()
    assert schema.entity == 'Member'
    assert schema.feature_kind != 'AUTH'
    assert schema.table == 'tb_member'
    assert [c for _p, c, _j in schema.fields] == [
        'member_id', 'login_id', 'login_password', 'member_name', 'email', 'phone_no',
        'use_yn', 'member_status_cd', 'last_login_dt', 'reg_dt', 'upd_dt'
    ]


def test_auth_augmentation_reuses_explicit_member_table_instead_of_login_table(tmp_path: Path):
    member = _member_schema()
    cfg = ProjectConfig(extra_requirements=REQ, login_feature_enabled=True, auth_general_login=True, auth_primary_mode='general').normalize()
    out = _augment_schema_map_with_auth({'Member': member}, [], cfg)
    assert 'Login' in out
    assert out['Member'].table == 'tb_member'
    assert out['Login'].table == 'tb_member'
    assert 'login' not in {str(getattr(schema, 'table', '') or '').strip().lower() for schema in out.values()}
    patched = _write_auth_sql_artifacts(tmp_path, out, 'egovframework.test')
    assert patched == {}


def test_ddl_supports_explicit_foreign_key_reference():
    req = '''
테이블명:
- TB_MEMBER_ROLE

컬럼은 최소 아래와 같이 생성하라.
1. member_role_id
- 타입: VARCHAR(50)
- 제약: PRIMARY KEY
- comment: 회원 역할 ID
2. member_id
- 타입: VARCHAR(50)
- 제약: NOT NULL, FK: TB_MEMBER(member_id)
- comment: 회원 고유 ID
3. role_cd
- 타입: VARCHAR(20)
- 제약: NOT NULL
- comment: 역할 코드
'''
    schema = infer_schema_from_plan({'requirements_text': req, 'database_type': 'mysql'})
    sql = ddl(schema)
    assert 'CREATE TABLE IF NOT EXISTS tb_member_role (' in sql
    assert 'CONSTRAINT fk_tb_member_role_member_id FOREIGN KEY (member_id) REFERENCES tb_member(member_id)' in sql
