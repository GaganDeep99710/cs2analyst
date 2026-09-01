"""
store.py — accounts + saved reports (SQLite, stdlib only).

A file-backed database so users persist and their reports survive server
restarts (which the in-memory job model did not). Passwords hashed with
PBKDF2-SHA256. One connection per call keeps it thread-safe under the worker
pool without locking headaches; WAL mode allows concurrent reads.
"""

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

# Persist to DATA_DIR if set (point this at a mounted volume so data survives
# redeploys); otherwise default to <repo>/data == /app/data in the container.
DATA = Path(os.getenv("DATA_DIR") or (Path(__file__).parents[2] / "data"))
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / "app.db"


def stats() -> dict:
    """Small health snapshot so we can verify the volume is persisting."""
    info = {"data_dir": str(DATA), "db_exists": DB.exists(), "users": None}
    if DB.exists():
        try:
            with _conn() as c:
                info["users"] = c.execute(
                    "SELECT COUNT(*) FROM users").fetchone()[0]
        except sqlite3.Error:
            pass
    return info


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
            summary TEXT, html TEXT, skills TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """)
        # migrate older DBs that predate the skills column
        try:
            c.execute("ALTER TABLE reports ADD COLUMN skills TEXT")
        except sqlite3.OperationalError:
            pass
        # connected FACEIT account (added later)
        for col in ("faceit_nickname TEXT", "faceit_player_id TEXT"):
            try:
                c.execute(f"ALTER TABLE users ADD COLUMN {col}")
            except sqlite3.OperationalError:
                pass
        # one row per FACEIT match we've pulled, so we never re-pull/re-spend
        c.execute("""
        CREATE TABLE IF NOT EXISTS faceit_matches(
            user_id INTEGER NOT NULL,
            match_id TEXT NOT NULL,
            report_id TEXT,
            status TEXT,
            created_at REAL,
            PRIMARY KEY(user_id, match_id)
        )""")
        # anonymous, cookie-free traffic log (IPs are hashed before storage)
        c.execute("""
        CREATE TABLE IF NOT EXISTS pageviews(
            ts REAL, day TEXT, path TEXT, ref TEXT, visitor TEXT
        )""")
        for idx in ("CREATE INDEX IF NOT EXISTS ix_pv_day ON pageviews(day)",
                    "CREATE INDEX IF NOT EXISTS ix_pv_ref ON pageviews(ref)"):
            c.execute(idx)


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


# ---- FACEIT connection -------------------------------------------------
def set_faceit(uid: int, nickname: str, player_id: str) -> None:
    with _conn() as c:
        c.execute("UPDATE users SET faceit_nickname=?, faceit_player_id=? "
                  "WHERE id=?", (nickname, player_id, uid))


def clear_faceit(uid: int) -> None:
    with _conn() as c:
        c.execute("UPDATE users SET faceit_nickname=NULL, "
                  "faceit_player_id=NULL WHERE id=?", (uid,))


def synced_match_ids(uid: int) -> set[str]:
    with _conn() as c:
        rows = c.execute("SELECT match_id FROM faceit_matches WHERE user_id=?",
                         (uid,)).fetchall()
        return {r[0] for r in rows}


def mark_faceit_match(uid: int, match_id: str, report_id: str | None,
                      status: str) -> None:
    """Record a pulled match (even failures) so a sync never re-pulls it."""
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO faceit_matches"
                  "(user_id,match_id,report_id,status,created_at) "
                  "VALUES(?,?,?,?,?)",
                  (uid, match_id, report_id, status, time.time()))


# ---- reports -----------------------------------------------------------
def save_report(rid: str, uid: int, meta: dict, html: str) -> None:
    with _conn() as c:
        c.execute(
            """INSERT OR REPLACE INTO reports
            (id,user_id,created_at,map,player,kd,adr,hs,rounds,deaths,summary,html,skills)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (rid, uid, time.time(), meta.get("map"), meta.get("player"),
             meta.get("kd"), meta.get("adr"), meta.get("hs"),
             meta.get("rounds"), meta.get("deaths"), meta.get("summary"), html,
             json.dumps(meta.get("skills") or {})))


def list_reports(uid: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            """SELECT id,created_at,map,player,kd,adr,hs,rounds,deaths,summary,skills
            FROM reports WHERE user_id=? ORDER BY created_at DESC""",
            (uid,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["skills"] = json.loads(d.get("skills") or "{}")
            except (ValueError, TypeError):
                d["skills"] = {}
            out.append(d)
        return out


def get_report(rid: str, uid: int) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM reports WHERE id=? AND user_id=?",
                      (rid, uid)).fetchone()
        return dict(r) if r else None


def delete_report(rid: str, uid: int) -> None:
    with _conn() as c:
        c.execute("DELETE FROM reports WHERE id=? AND user_id=?", (rid, uid))


# ---- traffic analytics -------------------------------------------------
def record_view(ts: float, day: str, path: str, ref: str, visitor: str) -> None:
    with _conn() as c:
        c.execute("INSERT INTO pageviews(ts,day,path,ref,visitor) "
                  "VALUES(?,?,?,?,?)", (ts, day, path, ref, visitor))


def traffic_stats() -> dict:
    with _conn() as c:
        tot = c.execute("SELECT COUNT(*) v, COUNT(DISTINCT visitor) u "
                        "FROM pageviews").fetchone()
        by_day = {r["day"]: {"v": r["v"], "u": r["u"]} for r in c.execute(
            "SELECT day, COUNT(*) v, COUNT(DISTINCT visitor) u "
            "FROM pageviews GROUP BY day").fetchall()}
        refs = [(r["ref"], r["v"], r["u"]) for r in c.execute(
            "SELECT ref, COUNT(*) v, COUNT(DISTINCT visitor) u FROM pageviews "
            "GROUP BY ref ORDER BY u DESC, v DESC LIMIT 12").fetchall()]
        paths = [(r["path"], r["v"], r["u"]) for r in c.execute(
            "SELECT path, COUNT(*) v, COUNT(DISTINCT visitor) u FROM pageviews "
            "GROUP BY path ORDER BY v DESC LIMIT 12").fetchall()]
        signups = {r["d"]: r["n"] for r in c.execute(
            "SELECT strftime('%Y-%m-%d', created_at, 'unixepoch') d, "
            "COUNT(*) n FROM users GROUP BY d").fetchall()}
        users_total = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        reports_total = c.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
    return {
        "total_views": tot["v"], "total_visitors": tot["u"],
        "by_day": by_day, "top_referrers": refs, "top_paths": paths,
        "signups_by_day": signups, "users_total": users_total,
        "reports_total": reports_total,
    }
