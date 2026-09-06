"""SQLite access layer for RehadAI (standard-library sqlite3, no ORM)."""

import os
import sqlite3
import click
from flask import current_app, g

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "rehadai.db")


def get_db():
    """One connection per request, stored on Flask's `g`."""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row          # rows behave like dicts
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create all tables from schema.sql (drops existing ones first)."""
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf8"))
    db.commit()


@click.command("init-db")
def init_db_command():
    """flask init-db — build an empty database."""
    init_db()
    click.echo(f"Initialised {current_app.config['DATABASE']}")


@click.command("seed-db")
def seed_db_command():
    """flask seed-db — build the database and load 5 dummy patients."""
    from seed import seed
    init_db()
    n_patients, n_assessments = seed(get_db())
    click.echo(f"Seeded {n_patients} patients and {n_assessments} assessments.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_db_command)
