
import asyncio
import asyncpg
import os

# DB Config
DB_HOST = "localhost"
DB_PORT = 5432
DB_USER = "pocuser"
DB_PASS = "pocpass"
DB_NAME = "incidents"

INCIDENT_NUMBER = "INC0010048"

async def check_incident():
    try:
        conn = await asyncpg.connect(
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            host=DB_HOST,
            port=DB_PORT
        )
        print(f"Connected to database {DB_NAME}")

        # Check incident details
        row = await conn.fetchrow(
            """
            SELECT i.short_description, i.description, pr.status, pr.current_stage 
            FROM pipeline_runs pr
            JOIN incidents i ON pr.incident_number = i.number
            WHERE pr.incident_number = $1
            """,
            INCIDENT_NUMBER
        )
        
        if row:
            print(f"Incident {INCIDENT_NUMBER}:")
            print(f"  Short Description: {row['short_description']}")
            print(f"  Description: {row['description']}")
            print(f"  Status: {row['status']}")
            print(f"  Stage: {row['current_stage']}")
        else:
            print(f"No pipeline run found for {INCIDENT_NUMBER}.")

        await conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_incident())
