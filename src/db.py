import os
import sqlite3
from datetime import datetime
import pandas as pd

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DB_PATH = os.path.join(BASE_DIR, "db", "jvl.db")


def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS startups (
                id INTEGER PRIMARY KEY,
                startup_name TEXT UNIQUE,
                sector TEXT,
                city TEXT,
                year INTEGER,
                amount REAL,
                website TEXT,
                leadership TEXT,
                source_link TEXT,
                address TEXT,
                contact TEXT,
                raw_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE,
                password_hash TEXT,
                role TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ratings (
                id INTEGER PRIMARY KEY,
                startup_id INTEGER,
                user_id INTEGER,
                rating INTEGER,
                comment TEXT,
                updated_at TEXT,
                UNIQUE(startup_id, user_id),
                FOREIGN KEY(startup_id) REFERENCES startups(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shortlists (
                id INTEGER PRIMARY KEY,
                startup_id INTEGER,
                user_id INTEGER,
                created_at TEXT,
                UNIQUE(startup_id, user_id),
                FOREIGN KEY(startup_id) REFERENCES startups(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ratings_startup ON ratings(startup_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ratings_user ON ratings(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_shortlists_user ON shortlists(user_id)")


def get_meta(key):
    with get_connection() as conn:
        row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(key, value):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO app_meta(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


def replace_startups(records):
    with get_connection() as conn:
        conn.execute("DELETE FROM startups")
        conn.executemany(
            """
            INSERT INTO startups(
                startup_name, sector, city, year, amount,
                website, leadership, source_link, address, contact, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(startup_name) DO UPDATE SET
                sector = excluded.sector,
                city = excluded.city,
                year = excluded.year,
                amount = excluded.amount,
                website = excluded.website,
                leadership = excluded.leadership,
                source_link = excluded.source_link,
                address = excluded.address,
                contact = excluded.contact,
                raw_json = excluded.raw_json
            """,
            [
                (
                    r["startup_name"],
                    r.get("sector"),
                    r.get("city"),
                    r.get("year"),
                    r.get("amount"),
                    r.get("website"),
                    r.get("leadership"),
                    r.get("source_link"),
                    r.get("address"),
                    r.get("contact"),
                    r.get("raw_json"),
                )
                for r in records
            ],
        )


def get_startups_df():
    with get_connection() as conn:
        df = pd.read_sql_query("SELECT * FROM startups", conn)
    return df


def get_startup_by_id(startup_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM startups WHERE id = ?", (startup_id,)).fetchone()
        return dict(row) if row else None


def get_user_rating(startup_id, user_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM ratings WHERE startup_id = ? AND user_id = ?",
            (startup_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def upsert_rating(startup_id, user_id, rating, comment):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO ratings(startup_id, user_id, rating, comment, updated_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(startup_id, user_id) DO UPDATE SET
                rating = excluded.rating,
                comment = excluded.comment,
                updated_at = excluded.updated_at
            """,
            (startup_id, user_id, rating, comment, datetime.utcnow().isoformat()),
        )


def toggle_shortlist(startup_id, user_id):
    with get_connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM shortlists WHERE startup_id = ? AND user_id = ?",
            (startup_id, user_id),
        ).fetchone()
        if exists:
            conn.execute(
                "DELETE FROM shortlists WHERE startup_id = ? AND user_id = ?",
                (startup_id, user_id),
            )
            return False
        conn.execute(
            "INSERT INTO shortlists(startup_id, user_id, created_at) VALUES (?, ?, ?)",
            (startup_id, user_id, datetime.utcnow().isoformat()),
        )
        return True


def get_user_shortlist_df(user_id):
    query = """
        SELECT s.*, sh.created_at
        FROM shortlists sh
        JOIN startups s ON s.id = sh.startup_id
        WHERE sh.user_id = ?
        ORDER BY sh.created_at DESC
    """
    with get_connection() as conn:
        df = pd.read_sql_query(query, conn, params=(user_id,))
    return df


def get_user_ratings_df(user_id):
    query = """
        SELECT s.startup_name, r.rating, r.comment, r.updated_at
        FROM ratings r
        JOIN startups s ON s.id = r.startup_id
        WHERE r.user_id = ?
        ORDER BY r.updated_at DESC
    """
    with get_connection() as conn:
        df = pd.read_sql_query(query, conn, params=(user_id,))
    return df


def get_leaderboard_df():
    query = """
        SELECT s.startup_name,
               AVG(r.rating) AS avg_rating,
               COUNT(r.rating) AS rating_count
        FROM ratings r
        JOIN startups s ON s.id = r.startup_id
        GROUP BY s.startup_name
        ORDER BY avg_rating DESC, rating_count DESC
    """
    with get_connection() as conn:
        df = pd.read_sql_query(query, conn)
    if not df.empty:
        df["avg_rating"] = df["avg_rating"].round(2)
    return df


def get_ratings_export_df():
    query = """
        SELECT r.*, s.startup_name, u.username
        FROM ratings r
        JOIN startups s ON s.id = r.startup_id
        JOIN users u ON u.id = r.user_id
        ORDER BY r.updated_at DESC
    """
    with get_connection() as conn:
        df = pd.read_sql_query(query, conn)
    return df


def get_shortlists_export_df():
    query = """
        SELECT sh.*, s.startup_name, u.username
        FROM shortlists sh
        JOIN startups s ON s.id = sh.startup_id
        JOIN users u ON u.id = sh.user_id
        ORDER BY sh.created_at DESC
    """
    with get_connection() as conn:
        df = pd.read_sql_query(query, conn)
    return df
