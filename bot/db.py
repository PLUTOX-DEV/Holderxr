import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from typing import Optional, List, Dict, Tuple

# Database URL from environment variables
DATABASE_URL = os.getenv("DATABASE_URL")

SCHEMA = """
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
"""

# Context manager for database connection
@contextmanager
def db():
    """PostgreSQL connection context manager with SSL enforcement."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable not set")

    dsn = f"{DATABASE_URL}?sslmode=require" if "sslmode=" not in DATABASE_URL else DATABASE_URL
    con = psycopg2.connect(dsn)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db():
    """Initialize database schema."""
    with db() as con, con.cursor() as cur:
        cur.execute(SCHEMA)


# ===== States (FSM) =====
def upsert_state(telegram_id: int, state: Optional[str], payload: Optional[str]):
    """Insert or update FSM state for a user."""
    with db() as con, con.cursor() as cur:
        if state is None:
            cur.execute("DELETE FROM states WHERE telegram_id = %s", (telegram_id,))
        else:
            cur.execute(
                """
                INSERT INTO states (telegram_id, state, payload)
                VALUES (%s, %s, %s)
                ON CONFLICT (telegram_id)
                DO UPDATE SET state = EXCLUDED.state, payload = EXCLUDED.payload
                """,
                (telegram_id, state, payload or ""),
            )


def get_state(telegram_id: int) -> Tuple[Optional[str], Optional[str]]:
    """Get FSM state for a user."""
    with db() as con, con.cursor() as cur:
        cur.execute("SELECT state, payload FROM states WHERE telegram_id = %s", (telegram_id,))
        row = cur.fetchone()
        return (row[0], row[1]) if row else (None, None)


# ===== Projects =====
def get_latest_project() -> Optional[Dict]:
    """Get the most recently created project."""
    with db() as con, con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, owner_username, network, contract_address, group_invite_link, channel_chat_id, created_at
            FROM projects
            ORDER BY id DESC
            LIMIT 1
            """
        )
        return cur.fetchone()


def get_all_projects() -> List[Dict]:
    """
    Return a list of all projects.
    Each project is a dict: {id, owner_username, network, contract_address, group_invite_link, channel_chat_id, created_at}
    """
    with db() as con, con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, owner_username, network, contract_address, group_invite_link, channel_chat_id, created_at
            FROM projects
            ORDER BY created_at DESC
            """
        )
        return cur.fetchall()


# ===== Users =====
def save_verified_user(telegram_id: int, username: str, project_id: int, wallet: str):
    """Save a verified Telegram user."""
    with db() as con, con.cursor() as cur:
        cur.execute(
            """
            INSERT INTO users (telegram_id, username, project_id, verified, wallet_address)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (telegram_id, username, project_id, 1, wallet),
        )


def get_verified_users(project_id: Optional[int] = None) -> List[Dict]:
    """
    Return list of verified users.
    Each user is a dict: {id, telegram_id, username, wallet_address, joined_at}
    Optional filter by project_id.
    """
    with db() as con, con.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        if project_id is not None:
            cur.execute(
                """
                SELECT id, telegram_id, username, wallet_address, joined_at
                FROM users
                WHERE verified = 1 AND project_id = %s
                ORDER BY joined_at DESC
                """,
                (project_id,),
            )
        else:
            cur.execute(
                """
                SELECT id, telegram_id, username, wallet_address, joined_at
                FROM users
                WHERE verified = 1
                ORDER BY joined_at DESC
                """
            )
        return cur.fetchall()


# ===== Project Deletion =====
def delete_project(project_id: int):
    """Delete a project by ID along with its associated users (cascade)."""
    with db() as con, con.cursor() as cur:
        cur.execute("DELETE FROM projects WHERE id = %s", (project_id,))

