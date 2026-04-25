from execution_core.builtin_crud import builtin_file, infer_schema_from_file_ops


SCHEMA_SQL = """
CREATE TABLE `room` (
  `room_id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(50) NOT NULL,
  PRIMARY KEY (`room_id`)
);

CREATE TABLE `reservation` (
  `reservation_id` int NOT NULL AUTO_INCREMENT,
  `room_id` int NOT NULL,
  `start_date` date NOT NULL,
  `end_date` date NOT NULL,
  PRIMARY KEY (`reservation_id`),
  KEY `FK_reservation_room` (`room_id`),
  CONSTRAINT `FK_reservation_room` FOREIGN KEY (`room_id`) REFERENCES `room` (`room_id`)
);
"""


WRONG_RESERVATION_VO = """
package egovframework.test.reservation.service.vo;

public class ReservationVO {
    private Long reservationId;
    private Long roomId;
    private String title;
    private String reserverName;
    private java.util.Date startDatetime;
    private java.util.Date endDatetime;
}
"""


WRONG_RESERVATION_MAPPER = """
<mapper namespace="egovframework.test.reservation.service.mapper.ReservationMapper">
  <resultMap id="ReservationMap" type="egovframework.test.reservation.service.vo.ReservationVO">
    <id property="reservationId" column="reservation_id"/>
    <result property="roomId" column="room_id"/>
    <result property="title" column="title"/>
    <result property="reserverName" column="reserver_name"/>
    <result property="startDatetime" column="start_datetime"/>
    <result property="endDatetime" column="end_datetime"/>
  </resultMap>
</mapper>
"""


def test_infer_schema_uses_matching_schema_sql_table_columns_over_leaked_vo_and_mapper_fields():
    file_ops = [
        {"path": "src/main/resources/schema.sql", "content": SCHEMA_SQL},
        {"path": "src/main/java/egovframework/test/reservation/service/vo/ReservationVO.java", "content": WRONG_RESERVATION_VO},
        {"path": "src/main/resources/egovframework/mapper/reservation/ReservationMapper.xml", "content": WRONG_RESERVATION_MAPPER},
    ]

    schema = infer_schema_from_file_ops(file_ops, entity="Reservation")

    assert schema.table == "reservation"
    assert [col for _, col, _ in schema.fields] == ["reservation_id", "room_id", "start_date", "end_date"]
    assert "title" not in {col for _, col, _ in schema.fields}
    assert "reserver_name" not in {col for _, col, _ in schema.fields}


def test_builtin_mapper_rewrites_sql_from_authoritative_schema_sql_columns():
    file_ops = [
        {"path": "src/main/resources/schema.sql", "content": SCHEMA_SQL},
        {"path": "src/main/java/egovframework/test/reservation/service/vo/ReservationVO.java", "content": WRONG_RESERVATION_VO},
        {"path": "src/main/resources/egovframework/mapper/reservation/ReservationMapper.xml", "content": WRONG_RESERVATION_MAPPER},
    ]

    schema = infer_schema_from_file_ops(file_ops, entity="Reservation")
    mapper_xml = builtin_file("mapper/reservation/ReservationMapper.xml", "egovframework.test", schema)

    assert mapper_xml is not None
    assert "reservation_id, room_id, start_date, end_date" in mapper_xml
    assert "title" not in mapper_xml
    assert "reserver_name" not in mapper_xml
    assert "start_datetime" not in mapper_xml
    assert "end_datetime" not in mapper_xml
