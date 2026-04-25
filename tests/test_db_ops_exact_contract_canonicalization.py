from execution_core.builtin_crud import infer_schema_from_plan, canonicalize_db_ops


REQ = '''
테이블명:
- tb_member

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

3. use_yn
- 타입: CHAR(1)
- 제약: NOT NULL
- 기본값: 'Y'
- comment: 사용 여부
'''


def test_canonicalize_db_ops_replaces_same_column_wrong_metadata_contract():
    schema = infer_schema_from_plan({'requirements_text': REQ, 'database_type': 'mysql'})
    db_ops = [{
        'sql': """
        CREATE TABLE IF NOT EXISTS tb_member (
            member_id VARCHAR(64) NOT NULL PRIMARY KEY COMMENT '잘못된 코멘트',
            login_id VARCHAR(255) NOT NULL COMMENT '다른 코멘트',
            use_yn VARCHAR(1) COMMENT '다른 코멘트'
        ) COMMENT='다른 테이블 코멘트';
        """
    }]
    out = canonicalize_db_ops(db_ops, schema)
    assert len(out) == 1
    sql = out[0]['sql']
    assert "member_id VARCHAR(50) NOT NULL PRIMARY KEY COMMENT '회원 고유 ID'" in sql
    assert "login_id VARCHAR(100) UNIQUE NOT NULL COMMENT '로그인 아이디'" in sql
    assert "use_yn CHAR(1) NOT NULL DEFAULT 'Y' COMMENT '사용 여부'" in sql
    assert "COMMENT='회원 정보 관리 테이블'" in sql
