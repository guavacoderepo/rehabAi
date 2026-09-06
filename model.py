"""
RehadAI — scoring instruments, WPI calculation and the outcome model.

This module is the single source of truth for:
  * the 28 UK ROC admission items and their scales
  * the WPI (Walking Prediction Index) calculation
  * the outcome prediction and its clinical interpretation

IMPORTANT — before clinical use
-------------------------------
The scale ranges and anchor wording in SCALES are PLACEHOLDERS. Replace them
with the official UK ROC data-dictionary definitions. The predict() function is
a transparent stand-in for a trained classifier — swap its body for a call to
your own model (see predict_with_model() at the bottom for the pattern).
"""

import math

# ---------------------------------------------------------------------------
# Scales
#   dir = +1  higher score means MORE independence (FIM/FAM)
#   dir = -1  higher score means MORE impairment / dependency (NPDS, NIS)
# ---------------------------------------------------------------------------
SCALES = {
    "fim": {
        "min": 1, "max": 7, "dir": 1, "tag": "FIM",
        "anchors": {
            1: "Needs total assistance",
            2: "Needs maximal assistance",
            3: "Needs moderate assistance",
            4: "Needs minimal assistance",
            5: "Needs supervision or set-up",
            6: "Independent with aids or extra time",
            7: "Fully independent",
        },
    },
    "npds": {
        "min": 0, "max": 5, "dir": -1, "tag": "NPDS",
        "anchors": {
            0: "No help needed",
            1: "Minimal help",
            2: "Low dependency",
            3: "Moderate dependency",
            4: "High dependency",
            5: "Total dependency",
        },
    },
    "nis": {
        "min": 0, "max": 4, "dir": -1, "tag": "NIS",
        "anchors": {
            0: "No impairment",
            1: "Mild impairment",
            2: "Moderate impairment",
            3: "Severe impairment",
            4: "Complete loss",
        },
    },
}

# ---------------------------------------------------------------------------
# The 28 admission items, grouped into clinical domains
# ---------------------------------------------------------------------------
DOMAINS = [
    {
        "id": "mob", "name": "Moving around", "short": "Moving",
        "question": "How much help does {name} need to move and transfer?",
        "items": [
            ("fimfam_transfer_bed_adm", "Getting in and out of bed or a chair", "fim"),
            ("fimfam_transfer_toilet_adm", "Getting on and off the toilet", "fim"),
            ("fimfam_transfer_bath_adm", "Getting in and out of the bath or shower", "fim"),
            ("fimfam_transfer_car_adm", "Getting in and out of a car", "fim"),
            ("npds_mobility_adm", "Overall mobility dependency", "npds"),
        ],
    },
    {
        "id": "adl", "name": "Daily care", "short": "Daily care",
        "question": "How is {name} managing washing, dressing and continence?",
        "items": [
            ("fimfam_dress_upper_adm", "Dressing the upper body", "fim"),
            ("fimfam_dress_lower_adm", "Dressing the lower body", "fim"),
            ("fimfam_bathing_adm", "Bathing and washing", "fim"),
            ("fimfam_bladder_adm", "Bladder management", "fim"),
            ("fimfam_bowel_adm", "Bowel management", "fim"),
            ("fimfam_toileting_adm", "Toileting", "fim"),
            ("npds_bathing_adm", "Washing support needed", "npds"),
            ("npds_skin_pressure_adm", "Skin care needs", "npds"),
            ("npds_pressure_adm", "Pressure-relief needs", "npds"),
        ],
    },
    {
        "id": "com", "name": "Talking and thinking", "short": "Communication",
        "question": "How is {name} communicating and processing information?",
        "items": [
            ("fimfam_speech_adm", "Speech and expression", "fim"),
            ("fimfam_writing_adm", "Writing", "fim"),
            ("nis_cognitive_adm", "Cognitive impairment", "nis"),
            ("nis_perceptual_adm", "Perceptual impairment", "nis"),
        ],
    },
    {
        "id": "saf", "name": "Safety and energy", "short": "Safety",
        "question": "How much supervision does {name} need, and how is their energy?",
        "items": [
            ("npds_safety_adm", "Supervision for safety", "npds"),
            ("npds_specialing_adm", "Specialing (1:1 nursing)", "npds"),
            ("nis_fatigue_adm", "Fatigue", "nis"),
        ],
    },
    {
        "id": "neu", "name": "Neurological findings", "short": "Neurological",
        "question": "What did the neurological examination show?",
        "items": [
            ("nis_motor_upper_left_adm", "Motor power — left arm", "nis"),
            ("nis_motor_upper_right_adm", "Motor power — right arm", "nis"),
            ("nis_motor_lower_left_adm", "Motor power — left leg", "nis"),
            ("nis_motor_lower_right_adm", "Motor power — right leg", "nis"),
            ("nis_motor_trunk_adm", "Trunk control", "nis"),
            ("nis_sensation_adm", "Sensation", "nis"),
            ("nis_tone_adm", "Tone and spasticity", "nis"),
        ],
    },
]

# Flat item list: {key, label, scale, domain}
ITEMS = [
    {"key": k, "label": lbl, "scale": sc, "domain": d["id"]}
    for d in DOMAINS
    for (k, lbl, sc) in d["items"]
]
ITEM_KEYS = [i["key"] for i in ITEMS]
assert len(ITEM_KEYS) == 28, f"expected 28 items, found {len(ITEM_KEYS)}"

# Convenience: domains rendered with resolved scale objects, for templates
DOMAIN_VIEW = [
    {
        "id": d["id"], "name": d["name"], "short": d["short"], "question": d["question"],
        "items": [
            {
                "key": k, "label": lbl, "scale": sc,
                "tag": SCALES[sc]["tag"],
                "values": list(range(SCALES[sc]["min"], SCALES[sc]["max"] + 1)),
                "anchors": SCALES[sc]["anchors"],
            }
            for (k, lbl, sc) in d["items"]
        ],
    }
    for d in DOMAINS
]


# ---------------------------------------------------------------------------
# WPI
# ---------------------------------------------------------------------------
def raw_wpi(values):
    """Straight sum of all 28 item scores, exactly as entered."""
    return sum(int(values.get(i["key"], 0)) for i in ITEMS)


def adjusted_wpi(values):
    """
    Direction-adjusted WPI. NPDS and NIS items are reverse-coded so that every
    item points the same way: a HIGHER adjusted WPI always means better
    function. This is the score plotted on the progress chart.
    """
    total = 0
    for i in ITEMS:
        s = SCALES[i["scale"]]
        x = int(values.get(i["key"], s["min"]))
        total += (x - s["min"]) if s["dir"] > 0 else (s["max"] - x)
    return total


RAW_WPI_MAX = sum(SCALES[i["scale"]]["max"] for i in ITEMS)                     # 154
RAW_WPI_MIN = sum(SCALES[i["scale"]]["min"] for i in ITEMS)                     # 12
ADJ_WPI_MAX = sum(SCALES[i["scale"]]["max"] - SCALES[i["scale"]]["min"] for i in ITEMS)  # 142


def domain_score(values, domain_id):
    """Proportion of achievable function attained within one domain (0..1)."""
    got = mx = 0
    for i in ITEMS:
        if i["domain"] != domain_id:
            continue
        s = SCALES[i["scale"]]
        x = int(values.get(i["key"], s["min"]))
        got += (x - s["min"]) if s["dir"] > 0 else (s["max"] - x)
        mx += s["max"] - s["min"]
    return got / mx if mx else 0.0


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------
DOMAIN_WEIGHTS = {"mob": 0.34, "adl": 0.20, "com": 0.10, "saf": 0.12, "neu": 0.24}


def predict(values):
    """
    Stand-in outcome model: a weighted capability index pushed through a
    logistic. Deterministic and inspectable, so the UI can be built and
    demonstrated before the real classifier is ready.

    Returns a dict with wpi_raw, wpi_adj, walk_prob (%), risk_score (%) and
    per-domain attainment percentages.
    """
    capability = sum(domain_score(values, d) * w for d, w in DOMAIN_WEIGHTS.items())
    walk = 1 / (1 + math.exp(-(capability * 11 - 5)))
    risk = max(0.0, min(1.0, (1 - walk) * 0.65 + (1 - capability) * 0.35))
    return {
        "wpi_raw": raw_wpi(values),
        "wpi_adj": adjusted_wpi(values),
        "walk_prob": round(walk * 100, 1),
        "risk_score": round(risk * 100, 1),
        "domains": {d["id"]: round(domain_score(values, d["id"]) * 100) for d in DOMAINS},
    }


def risk_band(risk):
    return "low" if risk < 30 else "moderate" if risk < 60 else "high"


def risk_class(risk):
    return "p-good" if risk < 30 else "p-warn" if risk < 60 else "p-bad"


def risk_var(risk):
    return "good" if risk < 30 else "warn" if risk < 60 else "bad"


# ---------------------------------------------------------------------------
# Clinical interpretation
# ---------------------------------------------------------------------------
def interpret(pred, previous, patient_name):
    """
    Build a plain-English reading of a prediction.
    `previous` is the patient's prior assessment row (or None for baseline).
    Returns {"lead": str, "body": str, "recs": [str, ...]}.
    """
    first = patient_name.split()[0]
    band = risk_band(pred["risk_score"])
    dom = pred["domains"]

    ranked = sorted(DOMAINS, key=lambda d: dom[d["id"]])
    weak1, weak2, strong = ranked[0], ranked[1], ranked[-1]

    lead = {
        "low": f"{first} is on track to walk independently by discharge.",
        "moderate": f"{first} can realistically get walking, but it will depend on targeted work.",
        "high": f"Independent walking is a stretch for {first} at this point.",
    }[band]

    body = (
        f"There is a {pred['walk_prob']:.1f}% chance of walking independently or with "
        f"supervision by discharge, which places {first} in the {band}-risk group "
        f"({pred['risk_score']:.1f}%). What is holding things back most is "
        f"{weak1['name'].lower()} — currently at {dom[weak1['id']]}% of what is achievable — "
        f"followed by {weak2['name'].lower()} at {dom[weak2['id']]}%. "
        f"{strong['name']} is the strongest area at {dom[strong['id']]}%."
    )

    recs = []
    if dom["mob"] < 45:
        recs.append("Build up sit-to-stand and transfer practice first; body-weight-supported "
                    "gait training is worth considering.")
    else:
        recs.append("Push gait work toward distance and stamina rather than technique.")
    if dom["neu"] < 45:
        recs.append("Motor and tone findings are limiting — review for spasticity management "
                    "and an orthotics assessment.")
    if dom["saf"] < 55:
        recs.append("Supervision needs are high. Review falls risk and the specialing "
                    "requirement each week.")
    if dom["com"] < 55:
        recs.append("Communication or cognitive difficulties may affect carryover between "
                    "sessions — loop in SLT or neuropsychology.")
    if dom["adl"] < 45:
        recs.append("Continence and skin care are limiting progress — escalate the nursing "
                    "care plan.")

    if previous is None:
        recs.append("This is the baseline. Re-score every two weeks to see a trajectory.")
    else:
        delta = pred["wpi_adj"] - previous["wpi_adj"]
        if delta > 0:
            recs.append(f"Function is up {delta} WPI points since last time — the current "
                        "plan is working.")
        elif delta < 0:
            recs.append(f"WPI has dropped {abs(delta)} points. Check for infection, pain or "
                        "deconditioning before adjusting the programme.")
        else:
            recs.append("No change in WPI since last time — worth revisiting the programme.")

    return {"lead": lead, "body": body, "recs": recs}


# ---------------------------------------------------------------------------
# Swapping in your trained model
# ---------------------------------------------------------------------------
def predict_with_model(values, clf=None):
    """
    Pattern for replacing the stand-in with a real classifier.

        import joblib
        clf = joblib.load("walking_model.joblib")
        X = [[int(values[k]) for k in ITEM_KEYS]]     # column order fixed by ITEM_KEYS
        walk = float(clf.predict_proba(X)[0][1]) * 100

    Keep the return shape identical to predict() and nothing else in the app
    needs to change.
    """
    if clf is None:
        return predict(values)
    X = [[int(values[k]) for k in ITEM_KEYS]]
    walk = float(clf.predict_proba(X)[0][1]) * 100
    return {
        "wpi_raw": raw_wpi(values),
        "wpi_adj": adjusted_wpi(values),
        "walk_prob": round(walk, 1),
        "risk_score": round(100 - walk, 1),
        "domains": {d["id"]: round(domain_score(values, d["id"]) * 100) for d in DOMAINS},
    }
