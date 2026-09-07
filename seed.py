"""
Seed the database with 5 dummy patients and a plausible assessment history
for each. Run with:  flask seed-db
"""

import json
import math

from model import (ITEMS, SCALES, ITEM_KEYS, DOMAINS, predict, interpret, domain_score)


# ---------------------------------------------------------------------------
# 5 dummy patients.
# `history` is a list of (assessment date, recovery profile 0.0–1.0) pairs.
# The profile drives item scores: 0.0 = fully dependent, 1.0 = independent.
# ---------------------------------------------------------------------------
DUMMY_PATIENTS = [
    {
        "code": "ROC-4821", "name": "Margaret Whitfield", "age": 68, "sex": "F",
        "diagnosis": "Left MCA infarct", "admitted_on": "2026-06-02",
        "history": [("2026-06-03", 0.24), ("2026-06-17", 0.33), ("2026-07-01", 0.45),
                    ("2026-07-22", 0.58), ("2026-08-19", 0.66)],
    },
    {
        "code": "ROC-4835", "name": "Daniel Osei", "age": 41, "sex": "M",
        "diagnosis": "Traumatic brain injury", "admitted_on": "2026-06-14",
        "history": [("2026-06-15", 0.12), ("2026-07-02", 0.19), ("2026-07-28", 0.31),
                    ("2026-08-25", 0.42)],
    },
    {
        "code": "ROC-4840", "name": "Priya Raghavan", "age": 55, "sex": "F",
        "diagnosis": "Incomplete spinal cord injury", "admitted_on": "2026-05-20",
        "history": [("2026-05-21", 0.38), ("2026-06-11", 0.51), ("2026-07-09", 0.63),
                    ("2026-08-06", 0.74), ("2026-08-27", 0.79)],
    },
    {
        "code": "ROC-4852", "name": "Kenneth Ollerenshaw", "age": 73, "sex": "M",
        "diagnosis": "Right pontine haemorrhage", "admitted_on": "2026-07-01",
        "history": [("2026-07-02", 0.16), ("2026-07-23", 0.22), ("2026-08-13", 0.21),
                    ("2026-08-30", 0.28)],
    },
    {
        "code": "ROC-4861", "name": "Amelia Croft", "age": 29, "sex": "F",
        "diagnosis": "Guillain-Barré syndrome", "admitted_on": "2026-07-18",
        "history": [("2026-07-19", 0.31), ("2026-08-08", 0.55), ("2026-08-28", 0.72)],
    },
]


def make_scores(profile):
    """
    Build a plausible set of 28 item scores for a given recovery profile.
    Deterministic (seeded off a sine hash) so re-seeding reproduces the same
    demo data every time.
    """
    values = {}
    for idx, item in enumerate(ITEMS):
        s = SCALES[item["scale"]]
        jitter = (math.sin(idx * 12.9898 + profile * 78.233) * 43758.5453) % 1
        p = max(0.0, min(1.0, profile + (jitter - 0.5) * 0.28))
        span = s["max"] - s["min"]
        values[item["key"]] = (s["min"] + round(p * span) if s["dir"] > 0
                               else s["max"] - round(p * span))
    return values


def calculate_domain_scores(values):
    """Calculate domain scores (0-100) for all domains."""
    domains = {}
    for d in DOMAINS:
        domains[d["id"]] = round(domain_score(values, d["id"]) * 100)
    return domains


def insert_assessment(db, patient_id, patient_name, assessed_on, values,
                      previous=None, clinician="seed"):
    """Compute, interpret and store one assessment. Returns the prediction."""
    pred = predict(values)
    
    # Calculate domain scores if not already in pred
    if "domains" not in pred or not pred["domains"]:
        pred["domains"] = calculate_domain_scores(values)
    
    text = interpret(pred, previous, patient_name)

    columns = ["patient_id", "assessed_on", "clinician"] + ITEM_KEYS + [
        "wpi", "walk_prob", "risk_score", "interpretation"]
    params = [patient_id, assessed_on, clinician] + \
             [int(values[k]) for k in ITEM_KEYS] + [
        pred["wpi"], 
        pred["walk_prob"], 
        pred["risk_score"],
        json.dumps({**text, "domains": pred["domains"]}),
    ]
    db.execute(
        f"INSERT INTO assessments ({', '.join(columns)}) "
        f"VALUES ({', '.join('?' * len(columns))})",
        params,
    )
    return pred


def seed(db):
    """Populate an initialised database. Returns (patients, assessments)."""

    n_assessments = 0

    for p in DUMMY_PATIENTS:
        cur = db.execute(
            "INSERT INTO patients (code, name, age, sex, diagnosis, admitted_on) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (p["code"], p["name"], p["age"], p["sex"], p["diagnosis"],
             p["admitted_on"]),
        )
        patient_id = cur.lastrowid

        previous = None
        for assessed_on, profile in p["history"]:
            values = make_scores(profile)
            pred = insert_assessment(
                db,
                patient_id,
                p["name"],
                assessed_on,
                values,
                previous
            )
            previous = pred
            n_assessments += 1

    db.commit()
    return len(DUMMY_PATIENTS), n_assessments