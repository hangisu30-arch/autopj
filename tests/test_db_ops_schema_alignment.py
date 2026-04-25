from execution_core.builtin_crud import ddl, schema_for
from execution_core.generator import ensure_db_ops


def _reservation_schema():
    return schema_for(
        "Reservation",
        inferred_fields=[
            ("reservationId", "reservation_id", "Long"),
            ("roomId", "room_id", "Long"),
            ("startDate", "start_date", "java.util.Date"),
            ("endDate", "end_date", "java.util.Date"),
        ],
        table="reservation",
    )


def test_ensure_db_ops_rewrites_mismatched_target_table_columns_but_keeps_other_tables():
    schema = _reservation_schema()
    plan = {
        "db_ops": [
            {
                "sql": """
                CREATE TABLE reservation (
                  reservation_id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  room_id BIGINT,
                  title VARCHAR(255),
                  reserver_name VARCHAR(255)
                );
                """
            },
            {
                "sql": """
                CREATE TABLE room (
                  room_id BIGINT PRIMARY KEY AUTO_INCREMENT,
                  name VARCHAR(255)
                );
                """
            },
        ]
    }

    ensure_db_ops(plan, schema)

    assert len(plan["db_ops"]) == 2
    reservation_sql = plan["db_ops"][0]["sql"]
    room_sql = plan["db_ops"][1]["sql"]

    assert "CREATE TABLE IF NOT EXISTS reservation" in reservation_sql
    assert "start_date" in reservation_sql
    assert "end_date" in reservation_sql
    assert "title" not in reservation_sql
    assert "reserver_name" not in reservation_sql
    assert "CREATE TABLE room" in room_sql


def test_ensure_db_ops_keeps_matching_schema_sql_without_duplication():
    schema = _reservation_schema()
    matching_sql = ddl(schema)
    plan = {"db_ops": [{"sql": matching_sql}]}

    ensure_db_ops(plan, schema)

    assert plan["db_ops"] == [{"sql": matching_sql}]
