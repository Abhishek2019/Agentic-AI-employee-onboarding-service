import os
import sys
import asyncio
import sqlparse
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine

async def run_schema(sql_path: str):
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL not set (put it in .env or env).")

    if not os.path.isfile(sql_path):
        raise SystemExit(f"File not found: {sql_path}")

    # Read & split multi-statement SQL safely
    with open(sql_path, "r", encoding="utf-8") as f:
        sql_text = f.read()
    statements = [s.strip() for s in sqlparse.split(sql_text) if s.strip()]

    engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
    async with engine.begin() as conn:
        # Run inside a single transaction; failing stmt will rollback everything
        for i, stmt in enumerate(statements, 1):
            try:
                # exec_driver_sql allows raw DDL without parameter parsing issues
                await conn.exec_driver_sql(stmt)
            except Exception as e:
                print(f"\nError on statement #{i}:\n{stmt}\n\n{e}\n", file=sys.stderr)
                raise
    await engine.dispose()
    print(f"✅ Executed {len(statements)} SQL statements from {sql_path}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_schema_async.py path/to/schema.sql")
        sys.exit(1)
    asyncio.run(run_schema(sys.argv[1]))

#--------------------------------------------------
#CMD
# python run_schema.py schema.sql
