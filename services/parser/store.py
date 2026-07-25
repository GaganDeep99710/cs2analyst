"""
store.py — accounts + saved reports (SQLite, stdlib only).

A file-backed database so users persist and their reports survive server
restarts (which the in-memory job model did not). Passwords hashed with
PBKDF2-SHA256. One connection per call keeps it thread-safe under the worker
pool without locking headaches; WAL mode allows concurrent reads.
"""

import hashlib
import hmac
import secrets
import sqlite3
import time
from pathlib import Path

DATA = Path(__file__).parents[2] / "data"
DATA.mkdir(exist_ok=True)
DB = DATA / "app.db"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init() -> None:
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            pw TEXT NOT NULL,
            ign TEXT,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS reports(
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at REAL,
            map TEXT, player TEXT,
            kd REAL, adr REAL, hs INTEGER, rounds INTEGER, deaths INTEGER,
            summary TEXT, html TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """)


# ---- auth --------------------------------------------------------------
def hash_pw(pw: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000)
    return f"{salt}${dk.hex()}"


def verify_pw(pw: str, stored: str) -> bool:
    try:
        salt, h = stored.split("$", 1)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000)
    return hmac.compare_digest(dk.hex(), h)


def session_secret() -> str:
    """Stable secret so sessions survive restarts."""
    f = DATA / "secret.key"
    if not f.exists():
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip()


# ---- users -------------------------------------------------------------
def create_user(email: str, pw: str, ign: str) -> int | None:
    try:
        with _conn() as c:
            cur = c.execute(
                "INSERT INTO users(email,pw,ign,created_at) VALUES(?,?,?,?)",
                (email.lower().strip(), hash_pw(pw), ign.strip(), time.time()))
            return cur.lastrowid
    except sqlite3.IntegrityError:
        return None  # email taken


def user_by_email(email: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM users WHERE email=?",
                      (email.lower().strip(),)).fetchone()
        return dict(r) if r else None


def user_by_id(uid: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return dict(r) if r else None


def set_ign(uid: int, ign: str) -> None:
    with _conn() as c:
        c.execute("UPDATE users SET ign=? WHERE id=?", (ign.strip(), uid))


# ---- reports -----------------------------------------------------------
def save_report(rid: str, uid: int, meta: dict, html: str) -> None:
    with _conn() as c:
        c.execute(
            """INSERT OR REPLACE INTO reports
            (id,user_id,created_at,map,player,kd,adr,hs,rounds,deaths,summary,html)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rid, uid, time.time(), meta.get("map"), meta.get("player"),
             meta.get("kd"), meta.get("adr"), meta.get("hs"),
             meta.get("rounds"), meta.get("deaths"), meta.get("summary"), html))


def list_reports(uid: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            """SELECT id,created_at,map,player,kd,adr,hs,rounds,deaths,summary
            FROM reports WHERE user_id=? ORDER BY created_at DESC""",
            (uid,)).fetchall()
        return [dict(r) for r in rows]


def get_report(rid: str, uid: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM reports WHERE id=? AND user_id=?",
                      (rid, uid)).fetchone()
        return dict(r) if r else None


def delete_report(rid: str, uid: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM reports WHERE id=? AND user_id=?", (rid, uid))
