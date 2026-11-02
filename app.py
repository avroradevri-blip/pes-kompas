import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, session, url_for

from db import (
    execute,
    nick_fold,
    norm_nick,
    notice_word,
    query,
    query_one,
    unread_count,
)

load_dotenv()

PORT = int(os.environ.get("PORT", "8080"))
SITE = os.environ.get("SITE_URL", "http://127.0.0.1:8080").rstrip("/")
TOKEN = os.environ.get("BOT_TOKEN", "").strip()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "pes-kompas-local")


class KeepPath:
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO") or "/"
        for prefix in ("/api/index", "/api"):
            if path == prefix or path == prefix + "/":
                path = "/"
                break
            if path.startswith(prefix + "/"):
                path = path[len(prefix):] or "/"
                break
        environ["PATH_INFO"] = path or "/"
        return self.wsgi_app(environ, start_response)


app.wsgi_app = KeepPath(app.wsgi_app)

MONTHS = (
    "января февраля марта апреля мая июня июля августа "
    "сентября октября ноября декабря"
).split()

REQUEST_FIELDS = (
    ("owner_name", "Имя"),
    ("owner_nick", "Ник Telegram"),
    ("dog_name", "Кличка"),
    ("breed", "Порода"),
    ("district", "Район"),
    ("walk_date", "Дата"),
    ("walk_time", "Время"),
)


def ru_date(iso):
    try:
        year, month, day = iso.split("-")
        return f"{int(day)} {MONTHS[int(month) - 1]} {year}"
    except (ValueError, IndexError):
        return iso


def count_word(n):
    n = abs(int(n))
    tail = n % 100
    last = n % 10
    if 11 <= tail <= 19:
        return "заявок"
    if last == 1:
        return "заявка"
    if 2 <= last <= 4:
        return "заявки"
    return "заявок"


app.jinja_env.filters["rudate"] = ru_date


def load_request(rid):
    return query_one("SELECT * FROM requests WHERE id = ?", (rid,))


def load_messages(rid):
    return query(
        "SELECT * FROM messages WHERE request_id = ? ORDER BY id",
        (rid,),
    )


def check_fields(form, fields, nick_keys):
    data = {}
    errors = {}
    for key, label in fields:
        value = (form.get(key) or "").strip()
        if key in nick_keys:
            value = norm_nick(value)
        if not value:
            errors[key] = f"Заполните поле «{label}»."
        data[key] = value
    return data, errors


def valid_date(value):
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def valid_time(value):
    try:
        datetime.strptime(value, "%H:%M")
        return True
    except ValueError:
        return False


def remember_person(name, nick):
    session["name"] = name
    session["nick"] = nick
    session.permanent = True


def send_notice(nick, request_id):
    fold = nick_fold(nick)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    execute(
        """
        INSERT INTO notices (nick, nick_fold, request_id, seen, created_at)
        VALUES (?, ?, ?, 0, ?)
        """,
        (norm_nick(nick), fold, request_id, now),
    )
    user = query_one("SELECT chat_id FROM bot_users WHERE username = ?", (fold[1:],))
    if not user or not TOKEN:
        return
    n = unread_count(nick)
    text = f"У вас {n} {notice_word(n)}.\nНовое сообщение в заявке №{request_id}."
    link = f"{SITE}/request/{request_id}/chat?nick={urllib.parse.quote(norm_nick(nick))}"
    payload = {
        "chat_id": user["chat_id"],
        "text": text,
        "reply_markup": json.dumps(
            {"inline_keyboard": [[{"text": "Открыть чат", "url": link}]]}
        ),
    }
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        data=urllib.parse.urlencode(payload).encode(),
    )
    try:
        urllib.request.urlopen(req, timeout=8)
    except (urllib.error.URLError, TimeoutError):
        pass


def post_message(item, name, nick, text):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    execute(
        """
        INSERT INTO messages (request_id, author_name, author_nick, body, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (item["id"], name, nick, text, now),
    )
    people = {item["owner_nick"]}
    for message in load_messages(item["id"]):
        people.add(message["author_nick"])
    me = nick_fold(nick)
    for person in people:
        if nick_fold(person) == me:
            continue
        send_notice(person, item["id"])


def mark_seen(nick, request_id):
    fold = nick_fold(nick)
    if not fold:
        return
    execute(
        "UPDATE notices SET seen = 1 WHERE nick_fold = ? AND request_id = ? AND seen = 0",
        (fold, request_id),
    )


@app.get("/")
def index():
    n = query_one("SELECT COUNT(*) AS n FROM requests WHERE status = 'open'")
    count = n["n"] if n else 0
    return render_template("index.html", count=count, caption=count_word(count))


@app.route("/new", methods=["GET", "POST"])
def new_request():
    data = {key: "" for key, _ in REQUEST_FIELDS}
    data["comment"] = ""
    errors = {}
    if request.method == "POST":
        data, errors = check_fields(request.form, REQUEST_FIELDS, {"owner_nick"})
        data["comment"] = (request.form.get("comment") or "").strip()
        if data.get("walk_date") and not valid_date(data["walk_date"]):
            errors["walk_date"] = "Укажите дату."
        if data.get("walk_time") and not valid_time(data["walk_time"]):
            errors["walk_time"] = "Укажите время."
        if not errors:
            new_id = execute(
                """
                INSERT INTO requests (
                    owner_name, owner_nick, dog_name, breed, district, district_fold,
                    walk_date, walk_time, comment, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
                """,
                (
                    data["owner_name"],
                    data["owner_nick"],
                    data["dog_name"],
                    data["breed"],
                    data["district"],
                    data["district"].casefold(),
                    data["walk_date"],
                    data["walk_time"],
                    data["comment"],
                    datetime.now().strftime("%Y-%m-%d %H:%M"),
                ),
            )
            remember_person(data["owner_name"], data["owner_nick"])
            return redirect(url_for("listing", added=new_id))
    return render_template("new.html", data=data, errors=errors)


@app.get("/list")
def listing():
    district = (request.args.get("district") or "").strip()
    rows = query(
        """
        SELECT * FROM requests
        WHERE status = 'open'
        ORDER BY walk_date, walk_time, id
        """
    )
    if district:
        needle = district.casefold()
        rows = [row for row in rows if needle in row["district_fold"]]
    added = request.args.get("added", "")
    return render_template("list.html", rows=rows, district=district, added=added)


@app.route("/request/<int:rid>/chat", methods=["GET", "POST"])
def chat(rid):
    item = load_request(rid)
    if not item:
        return render_template("404.html"), 404
    incoming = norm_nick(request.args.get("nick") or "")
    if incoming:
        remember_person(session.get("name") or incoming, incoming)
    errors = {}
    if request.method == "POST":
        name = (request.form.get("name") or session.get("name") or "").strip()
        nick = norm_nick(request.form.get("nick") or session.get("nick") or "")
        text = (request.form.get("text") or "").strip()
        if item["status"] != "open":
            errors["text"] = "Заявка закрыта. Написать уже нельзя."
        else:
            if not name:
                errors["name"] = "Заполните поле «Имя»."
            if not nick:
                errors["nick"] = "Заполните поле «Ник Telegram»."
            if not text:
                errors["text"] = "Напишите сообщение."
        if not errors:
            remember_person(name, nick)
            post_message(item, name, nick, text)
            return redirect(url_for("chat", rid=rid))
    me = session.get("nick", "")
    if me:
        mark_seen(me, rid)
    return render_template(
        "chat.html",
        item=item,
        messages=load_messages(rid),
        errors=errors,
        me=me,
        name=session.get("name", ""),
    )


@app.get("/request/<int:rid>/reply")
def old_reply(rid):
    return redirect(url_for("chat", rid=rid))


@app.get("/mine")
def mine():
    searched = "nick" in request.args
    nick = norm_nick(request.args.get("nick") or "")
    error = ""
    rows = []
    if searched and not nick:
        error = "Введите ник Telegram."
    elif searched:
        remember_person(session.get("name") or nick, nick)
        rows = query("SELECT * FROM requests ORDER BY id DESC")
        rows = [row for row in rows if nick_fold(row["owner_nick"]) == nick_fold(nick)]
        for row in rows:
            count = query_one(
                "SELECT COUNT(*) AS n FROM messages WHERE request_id = ?",
                (row["id"],),
            )
            fresh = query_one(
                """
                SELECT COUNT(*) AS n FROM notices
                WHERE request_id = ? AND nick_fold = ? AND seen = 0
                """,
                (row["id"], nick_fold(nick)),
            )
            row["msg_count"] = count["n"] if count else 0
            row["unread"] = fresh["n"] if fresh else 0
    return render_template(
        "mine.html",
        nick=nick,
        rows=rows,
        error=error,
        searched=searched,
        closed=request.args.get("closed") == "1",
        unread=unread_count(nick) if nick else 0,
    )


@app.post("/request/<int:rid>/close")
def close_request(rid):
    nick = norm_nick(request.form.get("nick") or "")
    item = load_request(rid)
    if not item or nick_fold(item["owner_nick"]) != nick_fold(nick):
        return render_template("404.html"), 404
    if item["status"] == "open":
        execute("UPDATE requests SET status = 'closed' WHERE id = ?", (rid,))
    return redirect(url_for("mine", nick=nick, closed=1))


@app.errorhandler(404)
def not_found(_err):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT)
