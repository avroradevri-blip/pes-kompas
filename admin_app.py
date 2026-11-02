import os

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, request, session, url_for

from db import query, query_one

load_dotenv()

PORT = int(os.environ.get("ADMIN_PORT", "8081"))
PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

app = Flask(__name__, template_folder="templates/admin")
app.secret_key = os.environ.get("FLASK_SECRET", "pes-kompas-local")


def logged_in():
    return bool(session.get("admin"))


@app.get("/")
def home():
    if not logged_in():
        return render_template("login.html", error="")
    needle = (request.args.get("number") or "").strip()
    missing = False
    if needle:
        if needle.isdigit() and query_one("SELECT id FROM requests WHERE id = ?", (int(needle),)):
            return redirect(url_for("thread", rid=int(needle)))
        missing = True
    rows = query(
        """
        SELECT
            r.id, r.dog_name, r.owner_name, r.owner_nick, r.district, r.status,
            (SELECT COUNT(*) FROM messages m WHERE m.request_id = r.id) AS msgs,
            (SELECT MAX(created_at) FROM messages m WHERE m.request_id = r.id) AS last_at
        FROM requests AS r
        ORDER BY r.id DESC
        """
    )
    return render_template("home.html", rows=rows, number=needle, missing=missing)


@app.post("/login")
def login():
    given = request.form.get("password") or ""
    if PASSWORD and given == PASSWORD:
        session["admin"] = True
        session.permanent = True
        return redirect(url_for("home"))
    return render_template("login.html", error="Неверный пароль.")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.get("/chat/<int:rid>")
def thread(rid):
    if not logged_in():
        return redirect(url_for("home"))
    item = query_one("SELECT * FROM requests WHERE id = ?", (rid,))
    if not item:
        return redirect(url_for("home", number=rid))
    messages = query(
        "SELECT * FROM messages WHERE request_id = ? ORDER BY id",
        (rid,),
    )
    return render_template("thread.html", item=item, messages=messages)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT)
