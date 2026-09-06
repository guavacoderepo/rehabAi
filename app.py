"""
RehadAI — Flask application.

Run:
    pip install -r requirements.txt
    flask seed-db          # creates rehadai.db with 5 dummy patients
    flask run              # http://127.0.0.1:5000

Routes
    /login                          sign in (username + email)
    /logout
    /patients                       list of patients            [main page]
    /patients/<code>                one patient's record + chart
    /patients/<code>/predict        new prediction form (28 items)
    /patients/<code>/a/<id>         a single prediction result
"""

import json
import os
from datetime import date, datetime
from functools import wraps

from flask import (Flask, flash, g, redirect, render_template, request,
                   session, url_for)

import db as database
from model import (ADJ_WPI_MAX, DOMAIN_VIEW, DOMAINS, ITEM_KEYS, RAW_WPI_MAX,
                   SCALES, adjusted_wpi, interpret, predict, raw_wpi,
                   risk_band, risk_class, risk_var)

app = Flask(__name__)
app.config.from_mapping(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-key-change-me"),
    DATABASE=database.DB_PATH,
)
database.init_app(app)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("username"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.before_request
def load_user():
    g.username = session.get("username")
    g.email = session.get("email")


@app.route("/")
def index():
    return redirect(url_for("patients" if session.get("username") else "login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip()

        error = None
        if not username:
            error = "Please enter your username."
        elif "@" not in email:
            error = "Please enter a valid email address."

        if error:
            flash(error)
        else:
            # No password in the prototype — add werkzeug.security before
            # anything resembling real deployment.
            conn = database.get_db()
            conn.execute(
                "INSERT INTO users (username, email) VALUES (?, ?) "
                "ON CONFLICT(username) DO UPDATE SET email = excluded.email",
                (username, email),
            )
            conn.commit()
            session.clear()
            session["username"] = username
            session["email"] = email
            return redirect(request.args.get("next") or url_for("patients"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Patient list — the main page
# ---------------------------------------------------------------------------
@app.route("/patients")
@login_required
def patients():
    conn = database.get_db()
    q = (request.args.get("q") or "").strip()
    flt = request.args.get("filter", "all")

    rows = conn.execute("SELECT * FROM patients ORDER BY name").fetchall()

    people = []
    for r in rows:
        history = conn.execute(
            "SELECT * FROM assessments WHERE patient_id = ? ORDER BY assessed_on",
            (r["id"],),
        ).fetchall()
        if not history:
            continue
        latest, first = history[-1], history[0]
        people.append({
            "row": r,
            "latest": latest,
            "delta": latest["wpi_adj"] - first["wpi_adj"],
            "trend": [h["wpi_adj"] for h in history],
            "count": len(history),
        })

    needs_review = sum(1 for p in people if risk_band(p["latest"]["risk_score"]) == "high")

    if q:
        ql = q.lower()
        people = [p for p in people
                  if ql in (p["row"]["name"] + p["row"]["code"] +
                            p["row"]["diagnosis"]).lower()]
    if flt == "high":
        people = [p for p in people if risk_band(p["latest"]["risk_score"]) == "high"]
    elif flt == "improving":
        people = [p for p in people if p["delta"] > 0]

    return render_template(
        "patients.html", people=people, q=q, filter=flt,
        total=len(rows), needs_review=needs_review,
    )


# ---------------------------------------------------------------------------
# One patient
# ---------------------------------------------------------------------------
def _get_patient(code):
    row = database.get_db().execute(
        "SELECT * FROM patients WHERE code = ?", (code,)
    ).fetchone()
    if row is None:
        from werkzeug.exceptions import NotFound
        raise NotFound(f"No patient with code {code}")
    return row


def _history(patient_id):
    return database.get_db().execute(
        "SELECT * FROM assessments WHERE patient_id = ? ORDER BY assessed_on",
        (patient_id,),
    ).fetchall()


@app.route("/patients/<code>")
@login_required
def patient(code):
    p = _get_patient(code)
    history = _history(p["id"])

    entries = []
    for i, a in enumerate(reversed(history)):
        entries.append({
            "row": a,
            "text": json.loads(a["interpretation"]),
            "index": len(history) - i,
            "is_latest": i == 0,
        })

    chart = [{
        "date": a["assessed_on"],
        "wpi_adj": a["wpi_adj"],
        "wpi_raw": a["wpi_raw"],
        "walk": a["walk_prob"],
        "risk": a["risk_score"],
    } for a in history]

    latest = history[-1] if history else None
    delta = (latest["wpi_adj"] - history[0]["wpi_adj"]) if history else 0

    return render_template(
        "patient.html", p=p, history=history, entries=entries, chart=chart,
        latest=latest, delta=delta, domains=DOMAINS, adj_max=ADJ_WPI_MAX,
    )


# ---------------------------------------------------------------------------
# New prediction
# ---------------------------------------------------------------------------
@app.route("/patients/<code>/predict", methods=["GET", "POST"])
@login_required
def new_prediction(code):
    p = _get_patient(code)
    history = _history(p["id"])

    if request.method == "POST":
        values, errors = {}, []
        for key in ITEM_KEYS:
            raw = request.form.get(key)
            if raw is None or raw == "":
                errors.append(key)
                continue
            values[key] = int(raw)

        assessed_on = request.form.get("assessed_on") or date.today().isoformat()

        if errors:
            flash(f"{len(errors)} of 28 items still need a score.")
            return render_template(
                "predict.html", p=p, domains=DOMAIN_VIEW, values=values,
                assessed_on=assessed_on, adj_max=ADJ_WPI_MAX,
                previous=history[-1] if history else None,
            )

        pred = predict(values)
        text = interpret(pred, history[-1] if history else None, p["name"])

        conn = database.get_db()
        columns = ["patient_id", "assessed_on", "clinician"] + ITEM_KEYS + [
            "wpi_raw", "wpi_adj", "walk_prob", "risk_score", "interpretation"]
        params = [p["id"], assessed_on, g.username] + \
                 [values[k] for k in ITEM_KEYS] + [
            pred["wpi_raw"], pred["wpi_adj"], pred["walk_prob"],
            pred["risk_score"],
            json.dumps({**text, "domains": pred["domains"]}),
        ]
        cur = conn.execute(
            f"INSERT INTO assessments ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' * len(columns))})",
            params,
        )
        conn.commit()
        return redirect(url_for("assessment", code=code, assessment_id=cur.lastrowid))

    # GET — optionally pre-fill from the last assessment
    values = {}
    if request.args.get("prefill") and history:
        values = {k: history[-1][k] for k in ITEM_KEYS}

    return render_template(
        "predict.html", p=p, domains=DOMAIN_VIEW, values=values,
        assessed_on=date.today().isoformat(), adj_max=ADJ_WPI_MAX,
        previous=history[-1] if history else None,
    )


@app.route("/patients/<code>/a/<int:assessment_id>")
@login_required
def assessment(code, assessment_id):
    p = _get_patient(code)
    a = database.get_db().execute(
        "SELECT * FROM assessments WHERE id = ? AND patient_id = ?",
        (assessment_id, p["id"]),
    ).fetchone()
    if a is None:
        from werkzeug.exceptions import NotFound
        raise NotFound("No such assessment for this patient")

    history = _history(p["id"])
    previous = None
    for h in history:
        if h["id"] == a["id"]:
            break
        previous = h

    return render_template(
        "result.html", p=p, a=a, text=json.loads(a["interpretation"]),
        previous=previous, domains=DOMAINS, adj_max=ADJ_WPI_MAX,
    )


# ---------------------------------------------------------------------------
# Template helpers
# ---------------------------------------------------------------------------
@app.template_filter("longdate")
def longdate(iso):
    return datetime.fromisoformat(str(iso)[:10]).strftime("%-d %B %Y")


@app.template_filter("shortdate")
def shortdate(iso):
    return datetime.fromisoformat(str(iso)[:10]).strftime("%d %b")


@app.template_filter("ago")
def ago(iso):
    days = (date.today() - date.fromisoformat(str(iso)[:10])).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 14:
        return "a week ago"
    return f"{round(days / 7)} weeks ago"


@app.template_filter("initials")
def initials(name):
    return "".join(w[0] for w in name.split()[:2]).upper()


@app.template_filter("tint")
def tint(code):
    return "t" + str(sum(ord(c) for c in str(code)) % 4)


@app.template_filter("signed")
def signed(n):
    return f"+{n}" if n > 0 else ("±0" if n == 0 else str(n))


@app.context_processor
def inject_helpers():
    return {
        "risk_band": risk_band,
        "risk_class": risk_class,
        "risk_var": risk_var,
        "greeting": ("Good morning" if datetime.now().hour < 12
                     else "Good afternoon" if datetime.now().hour < 18
                     else "Good evening"),
        "today_long": datetime.now().strftime("%A, %-d %B"),
        "adj_wpi_max": ADJ_WPI_MAX,
        "raw_wpi_max": RAW_WPI_MAX,
    }


if __name__ == "__main__":
    # Create and seed the database automatically on first run.
    if not os.path.exists(app.config["DATABASE"]):
        with app.app_context():
            from seed import seed
            database.init_db()
            n_p, n_a = seed(database.get_db())
            print(f"Created {app.config['DATABASE']} — {n_p} patients, {n_a} assessments")
    app.run(debug=True)
