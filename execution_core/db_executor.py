import re
import mysql.connector

def _get_db_conf(config: dict) -> dict:
    # support both config["database"] and config["db"]
    if "database" in config:
        return config["database"]
    if "db" in config:
        # normalize
        d = config["db"]
        return {
            "enabled": True,
            "host": d.get("host","localhost"),
            "port": int(d.get("port",3306)),
            "username": d.get("user") or d.get("username") or "",
            "password": d.get("password") or "",
            "database": d.get("database") or d.get("name") or "",
        }
    return {"enabled": False}

def _split_sql(sql: str):
    # naive split by ; excluding empty
    parts = [s.strip() for s in re.split(r";\s*", sql) if s.strip()]
    return parts

def apply_db_ops(db_ops: list, config: dict):
    db_conf = _get_db_conf(config)
    if not db_conf.get("enabled", False):
        print("DB apply disabled")
        return

    host = db_conf["host"]
    port = db_conf.get("port", 3306)
    user = db_conf.get("username") or db_conf.get("user")
    password = db_conf.get("password", "")
    database = db_conf.get("database")

    bootstrap = mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
    )
    bootstrap_cursor = bootstrap.cursor()
    if database:
        bootstrap_cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci")
    bootstrap.commit()
    bootstrap_cursor.close()
    bootstrap.close()

    conn = mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )
    cursor = conn.cursor()

    for op in db_ops:
        sql = op.get("sql") if isinstance(op, dict) else None
        if not sql:
            continue
        for stmt in _split_sql(sql):
            print("Executing SQL:", stmt)
            cursor.execute(stmt)

    conn.commit()
    cursor.close()
    conn.close()
