# RehadAI

Rehabilitation outcome prediction from UK ROC admission data. Flask + SQLite.

Score a patient's 28 UK ROC admission items, get a walking probability, a WPI
score, a risk score and a plain-English clinical interpretation. Every
prediction is stored, so the patient record shows a progress line over the
whole admission.

---

## Running it

```bash
cd rehadai
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

export FLASK_APP=app.py        # Windows PowerShell: $env:FLASK_APP="app.py"
flask seed-db                  # creates rehadai.db with 5 dummy patients
flask run
```

Open <http://127.0.0.1:5000> and sign in with any username and email
(`a.demo` / `a.demo@ntu.ac.uk` is already in the database).

`python app.py` also works and will create and seed the database automatically
on first run.

### CLI commands

| Command          | What it does                                    |
| ---------------- | ----------------------------------------------- |
| `flask init-db`  | Build an empty database (drops existing tables)  |
| `flask seed-db`  | Build it and load 5 dummy patients               |

---

## Screens

| Route                          | Screen                                            |
| ------------------------------ | ------------------------------------------------- |
| `/login`                       | Sign in with username + email                     |
| `/patients`                    | **Main page** — list of patients                  |
| `/patients/<code>`             | Patient record: tiles, progress chart, history    |
| `/patients/<code>/predict`     | New prediction — all 28 items                     |
| `/patients/<code>/a/<id>`      | A single stored prediction                        |

---

## Files

```
rehadai/
├── app.py              routes, session auth, template filters
├── model.py            the 28 items, scales, WPI, prediction, interpretation
├── db.py               sqlite3 connection handling + flask CLI commands
├── schema.sql          tables (28 item columns with range CHECKs)
├── seed.py             5 dummy patients and their assessment histories
├── requirements.txt    Flask only — no ORM, no build step
├── templates/          base, login, patients, patient, predict, result
└── static/
    ├── css/style.css   design system
    └── js/app.js       chart, sparklines, live WPI tally
```

---

## The database

Three tables: `users`, `patients`, `assessments`.

`assessments` stores the 28 items as **named columns** rather than key/value
rows, so the table is directly usable as a feature matrix:

```sql
SELECT fimfam_transfer_bed_adm, npds_mobility_adm, /* ... */ nis_tone_adm,
       walk_prob
FROM   assessments;
```

Each column carries a `CHECK` constraint for its instrument's valid range
(FIM 1–7, NPDS 0–5, NIS 0–4), so an out-of-range score is rejected by the
database, not just by the form.

Export training data with:

```bash
sqlite3 -header -csv rehadai.db "SELECT * FROM assessments;" > training.csv
```

---

## Two things about WPI

**1. The items point in opposite directions.** FIM/FAM items score 1–7 where
higher means *more independent*. NPDS and NIS items score upward for *more
dependency and impairment*. A straight sum mixes the two, so the raw total is
close to meaningless clinically. From the seeded data:

| Patient             | Raw WPI | Adjusted WPI | Walking |
| ------------------- | ------: | -----------: | ------: |
| Margaret Whitfield  |      87 |           95 |   91.8% |
| Daniel Osei         |      84 |           60 |   46.3% |
| Kenneth Ollerenshaw |      83 |           43 |   16.1% |

The raw scores are nearly identical for three patients with completely
different outcomes. The adjusted score separates them cleanly.

So the app computes and stores **both**:

* `wpi_raw` — the straight sum you asked for, 12–154
* `wpi_adj` — NPDS and NIS reverse-coded so higher always means better, 0–142

`wpi_adj` is what the progress chart plots by default. Both are on the record
and you can toggle between them.

**2. Feed the model the 28 items, not the sum.** WPI is a good summary for
clinicians to read and to plot, but collapsing 28 items into one number throws
away most of the signal. Train on the individual columns.

---

## Swapping in your real model

`model.py` `predict()` is a transparent stand-in: a weighted capability index
through a logistic. It exists so the UI works before the classifier is ready.

Replace it with your own — `predict_with_model()` in the same file shows the
pattern:

```python
import joblib
clf = joblib.load("walking_model.joblib")
X = [[int(values[k]) for k in ITEM_KEYS]]     # ITEM_KEYS fixes column order
walk = float(clf.predict_proba(X)[0][1]) * 100
```

Keep the return shape (`wpi_raw`, `wpi_adj`, `walk_prob`, `risk_score`,
`domains`) and nothing else in the app needs to change.

---

## Before this goes anywhere near real patients

* **Scale anchors are placeholders.** Replace `SCALES` in `model.py` with the
  official UK ROC data-dictionary ranges and wording, and update the `CHECK`
  constraints in `schema.sql` to match.
* **There is no password.** Login takes a username and email and trusts them.
  Add `werkzeug.security` password hashing and a `password_hash` column, or
  put the app behind your institution's SSO.
* **Set a real `SECRET_KEY`** via environment variable — the default is a
  development placeholder.
* **SQLite is single-writer.** Fine for a project, a demo or a single clinic
  machine; move to PostgreSQL for anything multi-user.
* **No audit trail beyond `clinician` and `created_at`.** Clinical systems
  normally need immutable logging and the ability to amend rather than
  overwrite.
* The interpretation text is rule-based template output, not a clinical
  guideline. It is there to make the numbers readable, not to recommend
  treatment.

---

Brand colour is Nottingham Trent University pink (`#EC0B62`). Headings are
Fraunces, UI text is Instrument Sans, both from Google Fonts.
