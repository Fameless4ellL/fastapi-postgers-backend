


from sqlalchemy import create_engine, text

database_url: str = "postgresql+{mode}://postgres:postgres@db/postgres"


def create_extension():
    engine = create_engine(
        database_url.format(mode="psycopg2"),
        future=True
    )
    conn = engine.connect()
    try:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
        print("Extension pg_trgm created successfully.")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    create_extension()
