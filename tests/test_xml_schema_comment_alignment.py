from execution_core.builtin_crud import extract_explicit_requirement_schemas, infer_schema_from_file_ops


def test_structured_bullet_contract_preserves_comments_and_db_types():
    requirements = '''
    테이블명: room
    컬럼정의:
    - room_id / 회의실ID / varchar(50) / 필수
    - room_name / 회의실명 / varchar(200) / 필수
    - room_location / 위치 / varchar(200) / nullable
    '''
    schemas = extract_explicit_requirement_schemas(requirements)
    schema = schemas['Room']
    assert schema.field_comments['room_id'] == '회의실ID'
    assert schema.field_comments['room_name'] == '회의실명'
    assert schema.field_db_types['room_id'] == 'VARCHAR(50)'
    assert schema.field_db_types['room_name'] == 'VARCHAR(200)'
    assert schema.field_nullable['room_id'] is False
    assert schema.field_nullable['room_location'] is True


def test_mapper_write_contract_ignores_display_alias_columns():
    file_ops = [
        {
            'path': 'src/main/resources/egovframework/mapper/room/RoomMapper.xml',
            'content': '''
            <mapper namespace="egovframework.test.room.service.mapper.RoomMapper">
              <resultMap id="RoomMap" type="egovframework.test.room.service.vo.RoomVO">
                <id property="roomId" column="room_id"/>
                <result property="roomName" column="room_name"/>
                <result property="buildingName" column="building_name"/>
              </resultMap>
              <select id="selectRoomList" resultMap="RoomMap">
                SELECT r.room_id, r.room_name, b.building_name
                  FROM room r
                  LEFT JOIN building b ON b.building_id = r.building_id
              </select>
              <insert id="insertRoom" parameterType="egovframework.test.room.service.vo.RoomVO">
                INSERT INTO room (room_id, room_name)
                VALUES (#{roomId}, #{roomName})
              </insert>
            </mapper>
            ''',
        }
    ]
    schema = infer_schema_from_file_ops(file_ops, entity='Room')
    cols = [col for _prop, col, _jt in schema.fields]
    assert cols == ['room_id', 'room_name']


def test_mapper_columns_merge_with_requirement_comments_and_db_types():
    requirements = '''
    테이블명: room
    컬럼정의:
    - room_id / 회의실ID / varchar(50) / 필수
    - room_name / 회의실명 / varchar(200) / 필수
    - room_location / 위치 / varchar(200) / nullable
    '''
    file_ops = [
        {'path': 'requirements.txt', 'content': requirements},
        {
            'path': 'src/main/resources/egovframework/mapper/room/RoomMapper.xml',
            'content': '''
            <mapper namespace="egovframework.test.room.service.mapper.RoomMapper">
              <insert id="insertRoom" parameterType="egovframework.test.room.service.vo.RoomVO">
                INSERT INTO room (room_id, room_name, room_location)
                VALUES (#{roomId}, #{roomName}, #{roomLocation})
              </insert>
            </mapper>
            ''',
        },
    ]
    schema = infer_schema_from_file_ops(file_ops, entity='Room')
    assert schema.table == 'room'
    assert [col for _prop, col, _jt in schema.fields] == ['room_id', 'room_name', 'room_location']
    assert schema.field_comments['room_id'] == '회의실ID'
    assert schema.field_comments['room_name'] == '회의실명'
    assert schema.field_db_types['room_location'] == 'VARCHAR(200)'
    assert schema.field_nullable['room_location'] is True
