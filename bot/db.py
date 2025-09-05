import os
import psycopg2
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL")  # Render/Pxxl will set this in env vars

SCHEMA = '''
CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    owner_username TEXT NOT NULL,
    network TEXT NOT NULL,
    contract_address TEXT NOT NULL,
    group_invite_link TEXT,
    channel_chat_id TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_network_contract
ON projects (network, contract_address);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    username TEXT,
    project_id INT REFERENCES projects(id) ON DELETE CASCADE,
    verified INT DEFAULT 0,
    wallet_address TEXT,
    joined_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS states (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL UNIQUE,
    state TEXT,
    payload TEXT
);
'''


def init_db():
    """Initialize schema if not exists"""
    with db() as con:
        with con.cursor() as cur:
            cur.execute(SCHEMA)


@contextmanager
def db():
    # Make sslmode flexible:
    if DATABASE_URL and "?sslmode=" not in DATABASE_URL:
        dsn = f"{DATABASE_URL}?sslmode=disable"  # works with Pxxl
    else:
        dsn = DATABASE_URL

    con = psycopg2.connect(dsn)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def upsert_state(telegram_id: int, state: str | None, payload: str | None):
    with db() as con:
        with con.cursor() as cur:
            if state is None:
                cur.execute("DELETE FROM states WHERE telegram_id=%s", (telegram_id,))
            else:
                cur.execute("""
                    INSERT INTO states (telegram_id, state, payload)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (telegram_id) DO UPDATE
                    SET state = EXCLUDED.state, payload = EXCLUDED.payload
                """, (telegram_id, state, payload or ""))


def get_state(telegram_id: int):
    with db() as con:
        with con.cursor() as cur:
            cur.execute("SELECT state, payload FROM states WHERE telegram_id=%s", (telegram_id,))
            row = cur.fetchone()
            return (row[0], row[1]) if row else (None, None)
