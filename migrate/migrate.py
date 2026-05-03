import os
from pathlib import Path

import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]
SCHEMA_PATH = Path("/app/db/init.sql")


def main():
    sql = SCHEMA_PATH.read_text()

    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

    print("Database schema initialized successfully.")


if __name__ == "__main__":
    main()
