from dotenv import load_dotenv
from fastmcp import FastMCP
from typing import Optional, List, Tuple
import os
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from langchain_core.tools import tool

load_dotenv(override=True)



POOL: ConnectionPool = ConnectionPool(
    conninfo=os.getenv("DATABASE_URL"),
    min_size=1,
    max_size=5,
    kwargs={"row_factory": dict_row},
)

@tool
def assign_seating_space(seat_type: Optional[str] = None) -> dict:
    """
    Assign me a available seat to employee as if optional seating type (seat_id, seat_type) or a message if none found.
    """

    print("seating type -------------------", seat_type)
    sql = """
        SELECT ss.seat_id, ss.seat_type
        FROM onboarding.seating_space ss
        WHERE ss.employee_id IS NULL
        AND (%(seat_type)s::text IS NULL OR ss.seat_type = %(seat_type)s::text)
        ORDER BY random()
        LIMIT 1;
    """
    with POOL.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, {"seat_type": seat_type})
            row = cur.fetchone()
            print("Console row: ", row)
            if not row:
                return {"ok": False, "message": "No available seating space."}
            return {"ok": True, "seat_id": row["seat_id"], "seat_type": row["seat_type"]}


def get_tools()->list:

    return [assign_seating_space]