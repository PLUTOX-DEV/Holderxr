import os
import psycopg2
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL")  # Render/Render-like env var

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

CREATE INDEX IF NOT EXISTS idx_users_telegram_id
    ON users (telegram_id);

CREATE TABLE IF NOT EXISTS states (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL UNIQUE,
    state TEXT,
    payload TEXT
);
'''


@contextmanager
def db():
    """Context manager for Postgres connection with flexible sslmode."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")

    # Render usually provides sslmode=require, but if not, default to disable
    if "sslmode=" not in DATABASE_URL:
        dsn = f"{DATABASE_URL}?sslmode=disable"
    else:
        dsn = DATABASE_URL

    con = psycopg2.connect(dsn)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db():
    """Initialize schema if not exists."""
    with db() as con, con.cursor() as cur:
        cur.execute(SCHEMA)


def upsert_state(telegram_id: int, state: str | None, payload: str | None):
    """Save or delete per-user FSM state."""
    with db() as con, con.cursor() as cur:
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
    """Return (state, payload) for a user or (None, None)."""
    with db() as con, con.cursor() as cur:
        cur.execute("SELECT state, payload FROM states WHERE telegram_id=%s", (telegram_id,))
        row = cur.fetchone()
        return (row[0], row[1]) if row else (None, None)


def get_latest_project():
    """Return the most recently created project (id, network, contract, link, channel) or None."""
    with db() as con, con.cursor() as cur:
        cur.execute(
            "SELECT id, network, contract_address, group_invite_link, channel_chat_id "
            "FROM projects ORDER BY id DESC LIMIT 1"
        )
        return cur.fetchone()


def save_verified_user(telegram_id: int, username: str, project_id: int, wallet: str):
    """Insert a verified user record."""
    with db() as con, con.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (telegram_id, username, project_id, verified, wallet_address)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (telegram_id, username, project_id, 1, wallet),
        )
