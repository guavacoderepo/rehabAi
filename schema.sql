-- RehadAI schema
-- Rebuild with:  flask init-db      (empty)
--                flask seed-db      (empty + 5 dummy patients)

DROP TABLE IF EXISTS assessments;
DROP TABLE IF EXISTS patients;
DROP TABLE IF EXISTS users;

-- ---------------------------------------------------------------------------
-- Clinicians. The prototype signs in with username + email only; add a
-- password_hash column and werkzeug.security before any real deployment.
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL UNIQUE,
    email       TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Patients
-- ---------------------------------------------------------------------------
CREATE TABLE patients (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,          -- e.g. ROC-4821, used in URLs
    name        TEXT NOT NULL,
    age         INTEGER NOT NULL,
    sex         TEXT NOT NULL CHECK(sex IN ('F','M','X')),
    diagnosis   TEXT NOT NULL,
    admitted_on TEXT NOT NULL,                 -- ISO date
    consultant  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Assessments: one row per prediction.
--
-- The 28 UK ROC items are stored as named columns rather than key/value pairs,
-- so that
--     SELECT fimfam_transfer_bed_adm, fimfam_transfer_toilet_adm, ... , walk_prob FROM assessments
-- is directly usable as a feature matrix for model training and export.
-- CHECK constraints enforce each instrument's valid range.
-- ---------------------------------------------------------------------------
CREATE TABLE assessments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id  INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    assessed_on TEXT NOT NULL,                 -- ISO date the scoring refers to
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    clinician   TEXT,                          -- username who ran it

    -- the 28 admission items -------------------------------------------------
    fimfam_transfer_bed_adm          INTEGER NOT NULL CHECK(fimfam_transfer_bed_adm BETWEEN 1 AND 7),
    fimfam_transfer_toilet_adm       INTEGER NOT NULL CHECK(fimfam_transfer_toilet_adm BETWEEN 1 AND 7),
    fimfam_transfer_bath_adm         INTEGER NOT NULL CHECK(fimfam_transfer_bath_adm BETWEEN 1 AND 7),
    fimfam_transfer_car_adm          INTEGER NOT NULL CHECK(fimfam_transfer_car_adm BETWEEN 1 AND 7),
    npds_mobility_adm                INTEGER NOT NULL CHECK(npds_mobility_adm BETWEEN 0 AND 5),
    fimfam_dress_upper_adm           INTEGER NOT NULL CHECK(fimfam_dress_upper_adm BETWEEN 1 AND 7),
    fimfam_dress_lower_adm           INTEGER NOT NULL CHECK(fimfam_dress_lower_adm BETWEEN 1 AND 7),
    fimfam_bathing_adm               INTEGER NOT NULL CHECK(fimfam_bathing_adm BETWEEN 1 AND 7),
    fimfam_bladder_adm               INTEGER NOT NULL CHECK(fimfam_bladder_adm BETWEEN 1 AND 7),
    fimfam_bowel_adm                 INTEGER NOT NULL CHECK(fimfam_bowel_adm BETWEEN 1 AND 7),
    fimfam_toileting_adm             INTEGER NOT NULL CHECK(fimfam_toileting_adm BETWEEN 1 AND 7),
    npds_bathing_adm                 INTEGER NOT NULL CHECK(npds_bathing_adm BETWEEN 0 AND 5),
    npds_skin_pressure_adm           INTEGER NOT NULL CHECK(npds_skin_pressure_adm BETWEEN 0 AND 5),
    npds_pressure_adm                INTEGER NOT NULL CHECK(npds_pressure_adm BETWEEN 0 AND 5),
    fimfam_speech_adm                INTEGER NOT NULL CHECK(fimfam_speech_adm BETWEEN 1 AND 7),
    fimfam_writing_adm               INTEGER NOT NULL CHECK(fimfam_writing_adm BETWEEN 1 AND 7),
    nis_cognitive_adm                INTEGER NOT NULL CHECK(nis_cognitive_adm BETWEEN 0 AND 4),
    nis_perceptual_adm               INTEGER NOT NULL CHECK(nis_perceptual_adm BETWEEN 0 AND 4),
    npds_safety_adm                  INTEGER NOT NULL CHECK(npds_safety_adm BETWEEN 0 AND 5),
    npds_specialing_adm              INTEGER NOT NULL CHECK(npds_specialing_adm BETWEEN 0 AND 5),
    nis_fatigue_adm                  INTEGER NOT NULL CHECK(nis_fatigue_adm BETWEEN 0 AND 4),
    nis_motor_upper_left_adm         INTEGER NOT NULL CHECK(nis_motor_upper_left_adm BETWEEN 0 AND 4),
    nis_motor_upper_right_adm        INTEGER NOT NULL CHECK(nis_motor_upper_right_adm BETWEEN 0 AND 4),
    nis_motor_lower_left_adm         INTEGER NOT NULL CHECK(nis_motor_lower_left_adm BETWEEN 0 AND 4),
    nis_motor_lower_right_adm        INTEGER NOT NULL CHECK(nis_motor_lower_right_adm BETWEEN 0 AND 4),
    nis_motor_trunk_adm              INTEGER NOT NULL CHECK(nis_motor_trunk_adm BETWEEN 0 AND 4),
    nis_sensation_adm                INTEGER NOT NULL CHECK(nis_sensation_adm BETWEEN 0 AND 4),
    nis_tone_adm                     INTEGER NOT NULL CHECK(nis_tone_adm BETWEEN 0 AND 4),

    -- computed outputs -------------------------------------------------------
    wpi_raw        INTEGER NOT NULL,           -- straight sum of all 28 items
    wpi_adj        INTEGER NOT NULL,           -- NPDS/NIS reverse-coded
    walk_prob      REAL NOT NULL,              -- % chance of walking
    risk_score     REAL NOT NULL,              -- % risk of poor outcome
    interpretation TEXT NOT NULL               -- JSON: lead, body, recs, domains
);

CREATE INDEX idx_assessments_patient ON assessments(patient_id, assessed_on);
