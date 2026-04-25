from execution_core.builtin_crud import infer_schema_from_file_ops
from app.io.execution_core_apply import _schema_map_from_file_ops, _mysql_schema_sync_statements


REQ = """
테이블명: room
컬럼 명:
- room_id (회의실 ID, varchar(50), Primary Key)
- room_name (회의실명, varchar(200), not null)
- room_location (위치, varchar(200), nullable)
"""

ROOM_MAPPER = """<!DOCTYPE mapper
  PUBLIC '-//mybatis.org//DTD Mapper 3.0//EN'
  'http://mybatis.org/dtd/mybatis-3-mapper.dtd'>
<mapper namespace='egovframework.demo.room.service.mapper.RoomMapper'>
  <resultMap id='RoomMap' type='egovframework.demo.room.service.vo.RoomVO'>
    <id property='roomId' column='room_id'/>
    <result property='roomName' column='room_name'/>
    <result property='roomLocation' column='room_location'/>
  </resultMap>
  <select id='selectRoomList' resultMap='RoomMap'>
    SELECT room_id, room_name, room_location FROM room
  </select>
</mapper>
"""


def test_infer_schema_prefers_mapper_xml_over_wrong_schema_sql():
    file_ops = [
        {
            'path': 'src/main/resources/schema.sql',
            'content': 'CREATE TABLE IF NOT EXISTS room (id VARCHAR(64) PRIMARY KEY, name VARCHAR(100));',
        },
        {
            'path': 'src/main/resources/egovframework/mapper/room/RoomMapper.xml',
            'content': ROOM_MAPPER,
        },
    ]

    schema = infer_schema_from_file_ops(file_ops, entity='Room')

    assert schema.authority == 'mapper'
    assert schema.table == 'room'
    assert [col for _prop, col, _jt in schema.fields] == ['room_id', 'room_name', 'room_location']
    assert 'id' not in [col for _prop, col, _jt in schema.fields]


def test_schema_map_keeps_requirement_comments_when_mapper_contract_wins():
    file_ops = [
        {
            'path': 'src/main/resources/schema.sql',
            'content': 'CREATE TABLE IF NOT EXISTS room (id VARCHAR(64) PRIMARY KEY, name VARCHAR(100));',
        },
        {
            'path': 'src/main/resources/egovframework/mapper/room/RoomMapper.xml',
            'content': ROOM_MAPPER,
        },
    ]

    schema_map = _schema_map_from_file_ops(file_ops, REQ)
    room = schema_map['Room']

    assert room.table == 'room'
    assert room.field_comments['room_id'] == '회의실 ID'
    assert room.field_comments['room_name'] == '회의실명'
    assert room.field_db_types['room_name'] == 'VARCHAR(200)'
    assert room.field_nullable['room_name'] is False


def test_mysql_schema_sync_statements_adds_missing_columns_and_comment_updates():
    schema_map = _schema_map_from_file_ops([
        {
            'path': 'src/main/resources/egovframework/mapper/room/RoomMapper.xml',
            'content': ROOM_MAPPER,
        },
    ], REQ)
    room = schema_map['Room']

    existing = {
        'room_id': {
            'column_type': 'varchar(64)',
            'is_nullable': 'NO',
            'column_key': 'PRI',
            'extra': '',
            'column_comment': '',
        },
        'room_name': {
            'column_type': 'varchar(100)',
            'is_nullable': 'YES',
            'column_key': '',
            'extra': '',
            'column_comment': '',
        },
    }

    statements = _mysql_schema_sync_statements(room, existing)

    assert any('MODIFY COLUMN `room_id` VARCHAR(50) NOT NULL PRIMARY KEY COMMENT \'회의실 ID\'' in stmt for stmt in statements)
    assert any('MODIFY COLUMN `room_name` VARCHAR(200) NOT NULL COMMENT \'회의실명\'' in stmt for stmt in statements)
    assert any('ADD COLUMN `room_location` VARCHAR(200) COMMENT \'위치\'' in stmt for stmt in statements)
