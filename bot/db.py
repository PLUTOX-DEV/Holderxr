import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path("bot.db")

SCHEMA = '''
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_username TEXT NOT NULL,
    network TEXT NOT NULL,
    contract_address TEXT NOT NULL,
    group_invite_link TEXT,
    channel_chat_id TEXT,   -- 👈 added this
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_network_contract
ON projects (network, contract_address);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    username TEXT,
    project_id INTEGER,
    verified INTEGER DEFAULT 0,
    wallet_address TEXT,
    joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS states (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    state TEXT,
    payload TEXT
);
'''


def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.executescript(SCHEMA)

@contextmanager
def db():
    con = sqlite3.connect(DB_PATH)
    try:
        yield con
        con.commit()
    finally:
        con.close()

def upsert_state(telegram_id: int, state: str | None, payload: str | None):
    with db() as con:
        cur = con.cursor()
        if state is None:
            cur.execute("DELETE FROM states WHERE telegram_id=?", (telegram_id,))
        else:
            cur.execute(
                "INSERT INTO states (telegram_id, state, payload) VALUES (?, ?, ?) "
                "ON CONFLICT(telegram_id) DO UPDATE SET state=excluded.state, payload=excluded.payload",
                (telegram_id, state, payload or ""),
            )

def get_state(telegram_id: int):
    with db() as con:
        cur = con.cursor()
        cur.execute("SELECT state, payload FROM states WHERE telegram_id=?", (telegram_id,))
        row = cur.fetchone()
        return (row[0], row[1]) if row else (None, None)
