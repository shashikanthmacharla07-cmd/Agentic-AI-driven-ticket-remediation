
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

async def reset_incident():
    try:
        conn = await asyncpg.connect(
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            host=DB_HOST,
            port=DB_PORT
        )
        print(f"Connected to database {DB_NAME}")

        # Check current status
        row = await conn.fetchrow(
            "SELECT id, status, current_stage FROM pipeline_runs WHERE incident_number = $1",
            INCIDENT_NUMBER
        )
        
        if row:
            print(f"Found pipeline run for {INCIDENT_NUMBER}: ID={row['id']}, Status={row['status']}, Stage={row['current_stage']}")
            
            # Delete the row to reset
            await conn.execute("DELETE FROM pipeline_runs WHERE incident_number = $1", INCIDENT_NUMBER)
            print(f"Deleted pipeline run for {INCIDENT_NUMBER}. It should now be picked up by the scheduler.")
        else:
            print(f"No pipeline run found for {INCIDENT_NUMBER}.")

        await conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(reset_incident())
