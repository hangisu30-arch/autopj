from execution_core.builtin_crud import builtin_file, extract_explicit_requirement_schemas, infer_schema_from_file_ops, schema_for


def test_mapper_and_form_include_all_non_auto_columns():
    schema = schema_for(
        'User',
        inferred_fields=[
            ('id', 'id', 'Long'),
            ('loginId', 'login_id', 'String'),
            ('password', 'password', 'String'),
            ('createdAt', 'created_at', 'String'),
            ('useYn', 'use_yn', 'String'),
        ],
        table='users',
        strict_fields=True,
    )

    mapper = builtin_file('mapper/UserMapper.xml', 'egovframework.test', schema)
    form = builtin_file('jsp/user/UserForm.jsp', 'egovframework.test', schema)

    assert mapper is not None
    assert form is not None
    assert 'INSERT INTO users (id, login_id, password, created_at, use_yn)' in mapper
    assert "#{id}, #{loginId}, #{password}, STR_TO_DATE(NULLIF(REPLACE(#{createdAt}, 'T', ' '), ''), '%Y-%m-%d %H:%i:%s'), #{useYn}" in mapper
    assert 'created_at = STR_TO_DATE(NULLIF(REPLACE(#{createdAt}, \'T\', \' \'), \'\'), \'%Y-%m-%d %H:%i:%s\'),' in mapper
    assert 'use_yn = #{useYn},' in mapper
    assert 'name="createdAt"' in form
    assert 'name="useYn"' in form


def test_explicit_requirement_comments_flow_into_schema_and_ddl():
    requirements = '''
    테이블 이름: users
    최소 컬럼은 아래를 사용한다.
    - login_id (로그인 아이디)
    - password (비밀번호)
    - created_at (생성 일시)
    '''
    schemas = extract_explicit_requirement_schemas(requirements)
    schema = schemas['Login'] if 'Login' in schemas else schemas['User']
    assert schema.field_comments['login_id'] == '로그인 아이디'
    assert schema.field_comments['password'] == '비밀번호'
    assert schema.field_comments['created_at'] == '생성 일시'

    inferred = infer_schema_from_file_ops([{'path': 'requirements.txt', 'content': requirements}], entity='Users')
    assert inferred.field_comments['login_id'] == '로그인 아이디'
    assert inferred.field_comments['password'] == '비밀번호'
    assert inferred.field_comments['created_at'] == '생성 일시'
