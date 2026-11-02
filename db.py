import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
load_dotenv(BASE / ".env")

if os.environ.get("VERCEL"):
    DB_PATH = Path("/tmp/kompas.sqlite3")
else:
    DB_PATH = BASE / "data" / "kompas.sqlite3"


def norm_nick(value):
    value = "".join((value or "").split())
    if not value:
        return ""
    value = value.lstrip("@")
    if not value:
        return ""
    return "@" + value


def nick_fold(value):
    nick = norm_nick(value)
    return nick.casefold() if nick else ""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_name TEXT NOT NULL,
                owner_nick TEXT NOT NULL,
                dog_name TEXT NOT NULL,
                breed TEXT NOT NULL,
                district TEXT NOT NULL,
                district_fold TEXT NOT NULL,
                walk_date TEXT NOT NULL,
                walk_time TEXT NOT NULL,
                comment TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                walker_name TEXT NOT NULL,
                walker_nick TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                author_name TEXT NOT NULL,
                author_nick TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nick TEXT NOT NULL,
                nick_fold TEXT NOT NULL,
                request_id INTEGER NOT NULL,
                seen INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS bot_users (
                username TEXT PRIMARY KEY,
                chat_id INTEGER NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO messages (request_id, author_name, author_nick, body, created_at)
            SELECT request_id, walker_name, walker_nick, message, created_at
            FROM responses
            WHERE NOT EXISTS (
                SELECT 1 FROM messages AS m
                WHERE m.request_id = responses.request_id
                  AND m.author_nick = responses.walker_nick
                  AND m.body = responses.message
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def query(sql, args=()):
    conn = connect()
    try:
        return [dict(row) for row in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def query_one(sql, args=()):
    conn = connect()
    try:
        row = conn.execute(sql, args).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def execute(sql, args=()):
    conn = connect()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def save_bot_user(username, chat_id):
    username = (username or "").lstrip("@").casefold()
    if not username:
        return
    execute(
        """
        INSERT INTO bot_users (username, chat_id)
        VALUES (?, ?)
        ON CONFLICT(username) DO UPDATE SET chat_id = excluded.chat_id
        """,
        (username, int(chat_id)),
    )


def unread_count(nick):
    fold = nick_fold(nick)
    if not fold:
        return 0
    row = query_one(
        "SELECT COUNT(*) AS n FROM notices WHERE nick_fold = ? AND seen = 0",
        (fold,),
    )
    return row["n"] if row else 0


def notice_word(n):
    n = abs(int(n))
    tail = n % 100
    last = n % 10
    if 11 <= tail <= 19:
        return "уведомлений"
    if last == 1:
        return "уведомление"
    if 2 <= last <= 4:
        return "уведомления"
    return "уведомлений"


init_db()
