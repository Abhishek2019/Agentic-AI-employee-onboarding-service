from dotenv import load_dotenv
from fastmcp import FastMCP
from typing import Optional, List, Tuple
import os
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

load_dotenv(override=True)

mcp = FastMCP(name="Employee_Onboarding")

POOL: ConnectionPool = ConnectionPool(
    conninfo=os.getenv("DATABASE_URL"),
    min_size=1,
    max_size=5,
    kwargs={"row_factory": dict_row},
)

@mcp.tool
def assign_seating_space(seat_type: Optional[str] = None) -> dict:
    """
    Returns one available seat (seat_id, seat_type) or a message if none found.
    """
    sql = """
        SELECT ss.seat_id, ss.seat_type
        FROM onboarding.seating_space ss
        WHERE ss.employee_id IS NULL
        AND (%(seat_type)s IS NULL OR ss.seat_type = %(seat_type)s)
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

if __name__ == "__main__":
    try:
        mcp.run(transport="streamable-http")
    finally:
        POOL.close()
