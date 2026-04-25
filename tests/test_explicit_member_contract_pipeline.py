from execution_core.builtin_crud import ddl, builtin_file, infer_schema_from_plan

REQ = '''
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


def _schema():
    return infer_schema_from_plan(
        {
            'requirements_text': REQ,
            'database_type': 'mysql',
            'tasks': [{'content': '회원가입 후 로그인 가능하고 회원관리 CRUD도 함께 제공한다.'}],
        }
    )


def test_explicit_member_contract_preserves_table_columns_and_metadata():
    schema = _schema()
    assert schema.table == 'tb_member'
    assert schema.table_comment == '회원 정보 관리 테이블'
    assert [col for _prop, col, _jt in schema.fields] == [
        'member_id', 'login_id', 'login_password', 'member_name', 'email', 'phone_no',
        'use_yn', 'member_status_cd', 'last_login_dt', 'reg_dt', 'upd_dt'
    ]
    assert schema.field_db_types['member_id'] == 'VARCHAR(50)'
    assert schema.field_db_types['login_id'] == 'VARCHAR(100)'
    assert schema.field_db_types['login_password'] == 'VARCHAR(255)'
    assert schema.field_db_types['member_name'] == 'VARCHAR(100)'
    assert schema.field_db_types['email'] == 'VARCHAR(200)'
    assert schema.field_db_types['phone_no'] == 'VARCHAR(30)'
    assert schema.field_db_types['use_yn'] == 'CHAR(1)'
    assert schema.field_db_types['member_status_cd'] == 'VARCHAR(20)'
    assert schema.field_db_types['last_login_dt'] == 'DATETIME'
    assert schema.field_db_types['reg_dt'] == 'DATETIME'
    assert schema.field_db_types['upd_dt'] == 'DATETIME'
    assert schema.field_unique['login_id'] is True
    assert schema.field_nullable['member_id'] is False
    assert schema.field_nullable['login_id'] is False
    assert schema.field_nullable['login_password'] is False
    assert schema.field_nullable['member_name'] is False
    assert schema.field_nullable['email'] is True
    assert schema.field_nullable['phone_no'] is True
    assert schema.field_nullable['use_yn'] is False
    assert schema.field_nullable['member_status_cd'] is False
    assert schema.field_nullable['last_login_dt'] is True
    assert schema.field_nullable['reg_dt'] is False
    assert schema.field_nullable['upd_dt'] is True
    assert schema.field_defaults['use_yn'] == "'Y'"
    assert schema.field_defaults['member_status_cd'] == "'ACTIVE'"
    assert schema.field_comments['member_id'] == '회원 고유 ID'
    assert schema.field_comments['login_id'] == '로그인 아이디'
    assert schema.field_comments['login_password'] == '로그인 비밀번호'
    assert schema.field_comments['member_name'] == '회원명'
    assert schema.field_comments['email'] == '이메일'
    assert schema.field_comments['phone_no'] == '휴대폰번호'
    assert schema.field_comments['use_yn'] == '사용 여부'
    assert schema.field_comments['member_status_cd'] == '회원 상태 코드'
    assert schema.field_comments['last_login_dt'] == '최종 로그인 일시'
    assert schema.field_comments['reg_dt'] == '등록 일시'
    assert schema.field_comments['upd_dt'] == '수정 일시'


def test_mysql_ddl_includes_exact_column_contract_defaults_and_comments():
    schema = _schema()
    sql = ddl(schema)
    assert 'CREATE TABLE IF NOT EXISTS tb_member (' in sql
    assert "member_id VARCHAR(50) NOT NULL PRIMARY KEY COMMENT '회원 고유 ID'" in sql
    assert "login_id VARCHAR(100) UNIQUE NOT NULL COMMENT '로그인 아이디'" in sql
    assert "login_password VARCHAR(255) NOT NULL COMMENT '로그인 비밀번호'" in sql
    assert "member_name VARCHAR(100) NOT NULL COMMENT '회원명'" in sql
    assert "email VARCHAR(200) COMMENT '이메일'" in sql
    assert "phone_no VARCHAR(30) COMMENT '휴대폰번호'" in sql
    assert "use_yn CHAR(1) NOT NULL DEFAULT 'Y' COMMENT '사용 여부'" in sql
    assert "member_status_cd VARCHAR(20) NOT NULL DEFAULT 'ACTIVE' COMMENT '회원 상태 코드'" in sql
    assert "last_login_dt DATETIME COMMENT '최종 로그인 일시'" in sql
    assert "reg_dt DATETIME NOT NULL COMMENT '등록 일시'" in sql
    assert "upd_dt DATETIME COMMENT '수정 일시'" in sql
    assert "COMMENT='회원 정보 관리 테이블'" in sql


def test_crud_mapper_insert_and_update_cover_all_contract_columns():
    schema = _schema()
    mapper = builtin_file('mapper/LoginMapper.xml', 'egovframework.test', schema)
    assert mapper is not None
    assert 'INSERT INTO tb_member (member_id, login_id, login_password, member_name, email, phone_no, use_yn, member_status_cd, last_login_dt, reg_dt, upd_dt)' in mapper
    assert 'VALUES (#{memberId}, #{loginId}, #{loginPassword}, #{memberName}, #{email}, #{phoneNo}, #{useYn}, #{memberStatusCd},' in mapper
    assert 'login_id = #{loginId},' in mapper
    assert 'login_password = #{loginPassword},' in mapper
    assert 'member_name = #{memberName},' in mapper
    assert 'email = #{email},' in mapper
    assert 'phone_no = #{phoneNo},' in mapper
    assert 'use_yn = #{useYn},' in mapper
    assert 'member_status_cd = #{memberStatusCd},' in mapper
    assert 'last_login_dt = STR_TO_DATE' in mapper
    assert 'reg_dt = STR_TO_DATE' in mapper
    assert 'upd_dt = STR_TO_DATE' in mapper
    assert 'WHERE member_id = #{memberId}' in mapper
