from pathlib import Path
from types import SimpleNamespace

from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _cfg():
    return SimpleNamespace(frontend_key='jsp', backend_key='springboot')


def test_mapper_table_repair_handles_if_not_exists_and_tb_alias(tmp_path: Path):
    _write(
        tmp_path / 'src/main/resources/egovframework/mapper/reservation/ReservationMapper.xml',
        '''<mapper namespace="egovframework.demo.reservation.service.impl.ReservationMapper">
  <resultMap id="reservationMap" type="egovframework.demo.reservation.service.ReservationVO">
    <id property="reservationId" column="reservation_id"/>
    <result property="roomId" column="room_id"/>
    <result property="statusCd" column="status_cd"/>
  </resultMap>
  <select id="selectReservationList" resultMap="reservationMap">
    SELECT reservation_id, room_id, status_cd FROM tb_reservation
  </select>
</mapper>
''',
    )
    _write(
        tmp_path / 'src/main/resources/schema.sql',
        '''CREATE TABLE IF NOT EXISTS tb_reservation (
    reservation_id VARCHAR(255) COMMENT '예약ID'
);
''',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/demo/reservation/service/ReservationVO.java',
        'package egovframework.demo.reservation.service; public class ReservationVO { private String reservationId; private String roomId; private String statusCd; }',
    )

    report = validate_generated_project(tmp_path, _cfg(), include_runtime=False)
    assert any(i['type'] == 'mapper_table_column_mismatch' for i in report['static_issues'])
    apply_generated_project_auto_repair(tmp_path, report)
    schema = (tmp_path / 'src/main/resources/schema.sql').read_text(encoding='utf-8')
    assert 'CREATE TABLE IF NOT EXISTS tb_reservation' in schema
    assert 'reservation_id VARCHAR(255) COMMENT ' in schema
    assert 'room_id VARCHAR(255) COMMENT ' in schema
    assert 'status_cd VARCHAR(255) COMMENT ' in schema
