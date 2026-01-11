import bcrypt
from db import get_connection


def hash_password(password):
    password_bytes = password.encode("utf-8")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password, password_hash):
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def verify_user(username, password):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if not row:
        return None
    if verify_password(password, row["password_hash"]):
        return dict(row)
    return None


def seed_default_users():
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS total FROM users").fetchone()["total"]
        if count > 0:
            return
        users = [
            ("admin", hash_password("admin123"), "admin"),
            ("owner", hash_password("owner123"), "franchise_owner"),
        ]
        conn.executemany(
            "INSERT INTO users(username, password_hash, role) VALUES (?, ?, ?)",
            users,
        )
