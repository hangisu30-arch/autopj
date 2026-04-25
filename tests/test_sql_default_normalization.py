from execution_core.builtin_crud import ddl, schema_for


def test_mysql_ddl_strips_default_keyword_from_explicit_default_values():
    schema = schema_for(
        'User',
        inferred_fields=[
            ('userId', 'user_id', 'String'),
            ('roleCd', 'role_cd', 'String'),
            ('useYn', 'use_yn', 'String'),
            ('regDt', 'reg_dt', 'String'),
        ],
        table='tb_user',
        db_vendor='mysql',
        field_db_types={
            'user_id': 'VARCHAR(64)',
            'role_cd': 'VARCHAR(20)',
            'use_yn': 'CHAR(1)',
            'reg_dt': 'DATETIME',
        },
        field_nullable={
            'user_id': False,
            'role_cd': False,
            'use_yn': False,
            'reg_dt': False,
        },
        field_defaults={
            'role_cd': "DEFAULT 'USER'",
            'use_yn': "default 'Y'",
            'reg_dt': 'DEFAULT CURRENT_TIMESTAMP()',
        },
        field_comments={
            'user_id': '사용자 고유 ID',
            'role_cd': '권한코드',
            'use_yn': '사용여부',
            'reg_dt': '등록일시',
        },
    )

    assert schema.field_defaults['role_cd'] == "'USER'"
    assert schema.field_defaults['use_yn'] == "'Y'"
    assert schema.field_defaults['reg_dt'] == 'CURRENT_TIMESTAMP'

    sql = ddl(schema)
    assert "role_cd VARCHAR(20) NOT NULL DEFAULT 'USER' COMMENT '권한코드'" in sql
    assert "use_yn CHAR(1) NOT NULL DEFAULT 'Y' COMMENT '사용여부'" in sql
    assert "reg_dt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '등록일시'" in sql
    assert "DEFAULT 'DEFAULT ''USER'''" not in sql
    assert "DEFAULT 'DEFAULT ''Y'''" not in sql
