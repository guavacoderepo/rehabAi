"""SQLite access layer for RehabAI."""

import os
import shutil
import sqlite3
import click

from flask import current_app, g


# ---------------------------------------------------------------------------
# Database paths
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_DB = os.path.join(BASE_DIR, "rehadai.db")

# Vercel's deployed filesystem is read-only.
# /tmp is writable, so use a copy of the bundled database there.
if os.environ.get("VERCEL"):
    DB_PATH = "/tmp/rehadai.db"

    if not os.path.exists(DB_PATH):
        if os.path.exists(SOURCE_DB):
            shutil.copy2(SOURCE_DB, DB_PATH)
else:
    DB_PATH = SOURCE_DB


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

def get_db():
    """Return one SQLite connection per request."""

    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )

        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db


def close_db(e=None):
    """Close the database connection at the end of the request."""

    db = g.pop("db", None)

    if db is not None:
        db.close()


# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------

def init_db():
    """Create all tables from schema.sql."""

    db = get_db()

    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf8"))

    db.commit()


def database_ready():
    """Check whether the patients table already exists."""

    db = get_db()

    result = db.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        AND name = 'patients'
        """
    ).fetchone()

    return result is not None


# ---------------------------------------------------------------------------
# Flask CLI commands
# ---------------------------------------------------------------------------

@click.command("init-db")
def init_db_command():
    """flask init-db — build the database."""

    init_db()

    click.echo(
        f"Initialised database: {current_app.config['DATABASE']}"
    )


@click.command("seed-db")
def seed_db_command():
    """flask seed-db — initialise and load dummy patients."""

    from seed import seed

    if not database_ready():
        init_db()

    db = get_db()

    count = db.execute(
        "SELECT COUNT(*) FROM patients"
    ).fetchone()[0]

    if count == 0:
        n_patients, n_assessments = seed(db)

        click.echo(
            f"Seeded {n_patients} patients "
            f"and {n_assessments} assessments."
        )
    else:
        click.echo(
            f"Database already contains {count} patients. "
            "Skipping seed."
        )


# ---------------------------------------------------------------------------
# Flask initialisation
# ---------------------------------------------------------------------------

def init_app(app):
    """Register database functions and CLI commands with Flask."""

    app.teardown_appcontext(close_db)

    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_db_command)