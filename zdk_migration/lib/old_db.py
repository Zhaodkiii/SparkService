"""Read-only connection to legacy ZhaodkDream MySQL database."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

import pymysql
from pymysql.cursors import DictCursor

_TABLE_COLUMNS_CACHE: dict[str, frozenset[str]] = {}


def old_db_config() -> dict[str, Any]:
    return {
        "host": os.getenv("ZDK_OLD_DB_HOST", "127.0.0.1"),
        "port": int(os.getenv("ZDK_OLD_DB_PORT", "3306")),
        "user": os.getenv("ZDK_OLD_DB_USER", "root"),
        "password": os.getenv("ZDK_OLD_DB_PASSWORD", "Zhao1029*"),
        "database": os.getenv("ZDK_OLD_DB_NAME", "ZhaodkDream"),
        "charset": "utf8mb4",
        "cursorclass": DictCursor,
        "autocommit": True,
    }


@contextmanager
def old_db_connection() -> Iterator[pymysql.connections.Connection]:
    conn = pymysql.connect(**old_db_config())
    try:
        yield conn
    finally:
        conn.close()


from zdk_migration.lib.transforms import aware_datetime


def normalize_legacy_row(row: dict) -> dict:
    return {key: aware_datetime(value) for key, value in row.items()}


def old_fetch_all(sql: str, params: tuple | list | None = None) -> list[dict]:
    with old_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params or ())
            return [normalize_legacy_row(row) for row in cursor.fetchall()]


def old_fetch_one(sql: str, params: tuple | list | None = None) -> dict | None:
    rows = old_fetch_all(sql, params)
    return rows[0] if rows else None


def old_count(table: str, where: str = "1=1") -> int:
    row = old_fetch_one(f"SELECT COUNT(*) AS c FROM `{table}` WHERE {where}")
    return int(row["c"]) if row else 0


def old_table_exists(table: str) -> bool:
    cfg = old_db_config()
    row = old_fetch_one(
        """
        SELECT COUNT(*) AS c
        FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        (cfg["database"], table),
    )
    return bool(row and row["c"])


def old_ping() -> dict[str, Any]:
    cfg = old_db_config()
    with old_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 AS ok")
            row = cursor.fetchone()
    return {"ok": bool(row and row.get("ok") == 1), "database": cfg["database"], "host": cfg["host"]}


def old_table_columns(table: str) -> frozenset[str]:
    """Return actual column names for a legacy table (cached)."""
    if table not in _TABLE_COLUMNS_CACHE:
        cfg = old_db_config()
        rows = old_fetch_all(
            """
            SELECT COLUMN_NAME AS column_name
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            """,
            (cfg["database"], table),
        )
        _TABLE_COLUMNS_CACHE[table] = frozenset(r["column_name"] for r in rows)
    return _TABLE_COLUMNS_CACHE[table]


def old_pick_columns(table: str, columns: list[str]) -> list[str]:
    available = old_table_columns(table)
    return [col for col in columns if col in available]


def old_select(
    table: str,
    columns: list[str],
    *,
    where: str = "",
    order_by: str = "id",
    params: tuple | list | None = None,
) -> list[dict]:
    """SELECT only columns that exist on the legacy table."""
    picked = old_pick_columns(table, columns)
    if not picked:
        return []
    sql = f"SELECT {', '.join(f'`{c}`' for c in picked)} FROM `{table}`"
    if where:
        sql += f" WHERE {where}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    return old_fetch_all(sql, params)
