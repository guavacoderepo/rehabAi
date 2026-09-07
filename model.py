"""
RehabAI — Scoring instruments, WPI calculation, and outcome prediction.
"""

from asyncio.log import logger
import os
import json
import joblib
import numpy as np
import pandas as pd
from pandas import DataFrame


def load_rehabai_artifacts(model_dir="rehabai_models/"):
    """Load all RehabAI artifacts from disk."""
    calibrator_model = joblib.load(os.path.join(model_dir, "calibrator_model.joblib"))
    
    with open(os.path.join(model_dir, "feature_bin_specs.json"), "r") as f:
        feature_bin_specs = json.load(f)
    
    with open(os.path.join(model_dir, "bin_imputation_values.json"), "r") as f:
        bin_imputation_values = json.load(f)
    
    with open(os.path.join(model_dir, "quantile_bands.json"), "r") as f:
        quantile_bands = json.load(f)
    
    with open(os.path.join(model_dir, "wpi_features.json"), "r") as f:
        wpi_features = json.load(f)
    
    with open(os.path.join(model_dir, "numeric_features.json"), "r") as f:
        numeric_features = json.load(f)
    
    with open(os.path.join(model_dir, "categorical_features.json"), "r") as f:
        categorical_features = json.load(f)
    
    with open(os.path.join(model_dir, "bin_point_mapping.json"), "r") as f:
        bin_point_mapping = json.load(f)
    
    return {
        "feature_bin_specs": feature_bin_specs,
        "bin_imputation_values": bin_imputation_values,
        "quantile_bands": quantile_bands,
        "calibrator_model": calibrator_model,
        "wpi_features": wpi_features,
        "numeric_features": numeric_features,
        "categorical_features": categorical_features,
        "bin_point_mapping": bin_point_mapping,
    }


# Load all saved artifacts
artifacts = load_rehabai_artifacts("rehabai_models/")

FEATURE_BIN_SPECS = artifacts["feature_bin_specs"]
BIN_IMPUTATION_VALUES = artifacts["bin_imputation_values"]
QUANTILE_BANDS = artifacts["quantile_bands"]
calibrator = artifacts["calibrator_model"]
FINAL_WPI_FEATURES = artifacts["wpi_features"]
numeric_features = artifacts["numeric_features"]
categorical_features = artifacts["categorical_features"]
BIN_POINT_MAPPING = artifacts["bin_point_mapping"]


# UK ROC scales
SCALES = {
    "fim": {
        "min": 1, "max": 7, "dir": 1, "tag": "FIM",
        "anchors": {
            1: "Total assistance",
            2: "Maximal assistance",
            3: "Moderate assistance",
            4: "Minimal assistance",
            5: "Supervision or set-up",
            6: "Modified independence",
            7: "Complete independence",
        },
    },
    "npds": {
        "min": 0, "max": 5, "dir": -1, "tag": "NPDS",
        "anchors": {
            0: "No help needed",
            1: "Minimal help (occasional)",
            2: "Low dependency (regular help)",
            3: "Moderate dependency (frequent help)",
            4: "High dependency (constant help)",
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
    "npds_binary": {  # Binary NPDS items (0 or 5 only)
        "min": 0, "max": 5, "dir": -1, "tag": "NPDS",
        "values": [0, 5],
        "anchors": {
            0: "No need",
            5: "Requires assistance",
        },
    },
    "nis_special": {  # NIS trunk (0-2 only)
        "min": 0, "max": 2, "dir": -1, "tag": "NIS",
        "anchors": {
            0: "No impairment",
            1: "Moderate impairment",
            2: "Severe impairment",
        },
    },
}


# 28 UK ROC admission items grouped into 4 clinical domains
DOMAINS = [
    {
        "id": "mob",
        "name": "Mobility",
        "short": "Mobility",
        "question": "How much help does {name} need with mobility and transfers?",
        "items": [
            ("fimfam_transfer_bed_adm", "Transfer: bed/chair", "fim"),
            ("fimfam_transfer_toilet_adm", "Transfer: toilet", "fim"),
            ("fimfam_transfer_bath_adm", "Transfer: bath/shower", "fim"),
            ("fimfam_transfer_car_adm", "Transfer: car", "fim"),
            ("npds_mobility_adm", "Mobility dependency", "npds"),
        ],
    },
    {
        "id": "adl",
        "name": "ADL",
        "short": "ADL",
        "question": "How is {name} managing daily activities and self-care?",
        "items": [
            ("fimfam_dress_upper_adm", "Dressing: upper body", "fim"),
            ("fimfam_dress_lower_adm", "Dressing: lower body", "fim"),
            ("fimfam_bathing_adm", "Bathing/washing", "fim"),
            ("fimfam_bladder_adm", "Bladder management", "fim"),
            ("fimfam_bowel_adm", "Bowel management", "fim"),
            ("fimfam_toileting_adm", "Toileting", "fim"),
            ("npds_bathing_adm", "Bathing support", "npds"),
            ("npds_skin_pressure_adm", "Skin care/pressure", "npds"),
            ("npds_pressure_adm", "Pressure relief", "npds_binary"),  # 0 or 5 only
        ],
    },
    {
        "id": "cog",
        "name": "Cognitive / Communicative",
        "short": "Cognition",
        "question": "How is {name} communicating and processing information?",
        "items": [
            ("fimfam_speech_adm", "Speech/expression", "fim"),
            ("fimfam_writing_adm", "Writing", "fim"),
            ("nis_cognitive_adm", "Cognitive impairment", "nis"),
            ("nis_perceptual_adm", "Perceptual impairment", "nis"),
            ("npds_safety_adm", "Safety supervision", "npds"),
            ("npds_specialing_adm", "1:1 nursing (specialing)", "npds_binary"),  # 0 or 5 only
        ],
    },
    {
        "id": "phys",
        "name": "Physical Impairment",
        "short": "Physical",
        "question": "What are the physical and neurological findings for {name}?",
        "items": [
            ("nis_fatigue_adm", "Fatigue", "nis"),
            ("nis_motor_lower_left_adm", "Motor: left leg", "nis"),
            ("nis_motor_lower_right_adm", "Motor: right leg", "nis"),
            ("nis_motor_trunk_adm", "Trunk control", "nis_special"),  # 0-2 only
            ("nis_motor_upper_left_adm", "Motor: left arm", "nis"),
            ("nis_motor_upper_right_adm", "Motor: right arm", "nis"),
            ("nis_sensation_adm", "Sensation", "nis"),
            ("nis_tone_adm", "Tone/spasticity", "nis"),
        ],
    },
]

# Flatten items for easy iteration
ITEMS = [
    {"key": k, "label": lbl, "scale": sc, "domain": d["id"]}
    for d in DOMAINS
    for (k, lbl, sc) in d["items"]
]

ITEM_KEYS = [i["key"] for i in ITEMS]
assert len(ITEM_KEYS) == 28, f"Expected 28 items, found {len(ITEM_KEYS)}"

# Domain view with scale objects for templates
DOMAIN_VIEW = [
    {
        "id": d["id"],
        "name": d["name"],
        "short": d["short"],
        "question": d["question"],
        "items": [
            {
                "key": k,
                "label": lbl,
                "scale": sc,
                "tag": SCALES[sc]["tag"],
                "values": SCALES[sc].get("values", list(range(SCALES[sc]["min"], SCALES[sc]["max"] + 1))),
                "anchors": SCALES[sc]["anchors"],
            }
            for (k, lbl, sc) in d["items"]
        ],
    }
    for d in DOMAINS
]


def apply_dev_feature_types(X, numeric_cols, categorical_cols):
    """Apply feature typing learned from development data."""
    X_clean = X.copy()
    
    for col in numeric_cols:
        if col not in X_clean.columns:
            raise KeyError(f"Numeric feature missing: {col}")
        X_clean[col] = pd.to_numeric(X_clean[col], errors="coerce")
        X_clean[col] = X_clean[col].replace([np.inf, -np.inf], np.nan).astype("float64")
    
    for col in categorical_cols:
        if col not in X_clean.columns:
            raise KeyError(f"Categorical feature missing: {col}")
        X_clean[col] = X_clean[col].map(
            lambda v: str(v).strip() if pd.notna(v) else np.nan
        ).astype("object")
    
    return X_clean.replace({pd.NA: np.nan})


def apply_feature_bins(X, specs, imputation_values):
    """Apply locked development-derived bins."""
    Xb = pd.DataFrame(index=X.index)
    
    for feature, spec in specs.items():
        if feature not in X.columns:
            raise KeyError(f"Missing feature: {feature}")
        
        s = pd.to_numeric(X[feature], errors="coerce").astype(float)
        s = s.fillna(float(imputation_values[feature]))
        
        Xb[feature] = pd.cut(
            s,
            bins=spec["edges"],
            labels=spec["labels"],
            include_lowest=True,
            right=True,
            ordered=True,
        ).astype("object")
    
    return Xb


def score_binned_dataframe(X_binned):
    """Score binned data using the point mapping."""
    component_points = pd.DataFrame(index=X_binned.index)
    
    for feature in FINAL_WPI_FEATURES:
        mapping = BIN_POINT_MAPPING[feature]
        values = X_binned[feature].astype(str).str.replace('.0', '').fillna("Missing")
        
        unknown = set(values.unique()) - set(mapping.keys())
        for val in unknown:
            mapping[val] = 0
        
        component_points[feature] = values.map(mapping).astype(float)
    
    total_wpi = component_points.sum(axis=1)
    return component_points, total_wpi


def score_new_patient(patient_df: DataFrame):
    """Score a new patient using the WPI system."""
    missing = [f for f in FINAL_WPI_FEATURES if f not in patient_df.columns]
    if missing:
        raise KeyError(f"Missing WPI admission input fields: {missing}")
    
    Xp = patient_df.reindex(columns=FINAL_WPI_FEATURES).copy()
    Xp_clean = apply_dev_feature_types(Xp, numeric_features, categorical_features)
    patient_bins = apply_feature_bins(Xp_clean, FEATURE_BIN_SPECS, BIN_IMPUTATION_VALUES)
    
    component_points, total_wpi = score_binned_dataframe(patient_bins)
    
    probability = calibrator.predict_proba(
        np.asarray(total_wpi, dtype=float).reshape(-1, 1)
    )[:, 1]
    
    output = pd.DataFrame({
        "WPI": total_wpi.values,
        "EstimatedWalkingProbability": probability,
        "EstimatedWalkingProbability_percent": probability * 100,
    }, index=Xp.index)
    
    return output, component_points, patient_bins


def domain_score(values, domain_id):
    """Calculate domain-specific functional attainment (0.0-1.0)."""
    got = mx = 0
    for i in ITEMS:
        if i["domain"] != domain_id:
            continue
        s = SCALES[i["scale"]]
        x = int(values.get(i["key"], s["min"]))
        if s["dir"] > 0:
            got += (x - s["min"])
        else:
            got += (s["max"] - x)
        mx += s["max"] - s["min"]
    return got / mx if mx > 0 else 0.0


def predict(values):
    """Predict walking probability for a single patient."""
    df = pd.DataFrame([values])
    output, _, _ = score_new_patient(df)
    wpi = output["WPI"].iloc[0]
    walk_prob = output["EstimatedWalkingProbability_percent"].iloc[0]

    risk_score = wpi / QUANTILE_BANDS["q95"] * 10
    risk_score = np.clip(risk_score, 0, 10)

    # Calculate domain scores
    domains = {
        d["id"]: round(domain_score(values, d["id"]) * 100)
        for d in DOMAINS
    }

    return {
        "wpi": wpi,
        "walk_prob": round(walk_prob, 1),
        "risk_score": round(risk_score, 1),
        "domains": domains,
    }


def wpi_barrier_band(wpi):
    """Classify WPI score into barrier burden bands using quantiles."""
    if wpi <= QUANTILE_BANDS.get("q25", 0):
        return "Lower barrier burden"
    if wpi <= QUANTILE_BANDS.get("q50", 0):
        return "Lower-intermediate barrier burden"
    if wpi <= QUANTILE_BANDS.get("q75", 0):
        return "Higher-intermediate barrier burden"
    return "Higher barrier burden"


def risk_class(risk):
    """CSS class for UI styling based on risk score."""
    if risk <= QUANTILE_BANDS.get("q25", 0):
        return "p-good"
    elif risk <= QUANTILE_BANDS.get("q50", 0):
        return "p-warn"
    elif risk <= QUANTILE_BANDS.get("q75", 0):
        return "p-bad"
    else:
        return "p-bad"  # Highest risk


def risk_var(risk):
    """CSS variable for UI styling based on risk score."""
    if risk <= QUANTILE_BANDS.get("q25", 0):
        return "good"
    elif risk <= QUANTILE_BANDS.get("q50", 0):
        return "warn"
    elif risk <= QUANTILE_BANDS.get("q75", 0):
        return "bad"
    else:
        return "bad"  # Highest risk


def interpret(pred, previous=None, patient_name="Patient"):
    """Generate plain-English clinical interpretation."""
    first = patient_name.split()[0] if patient_name else "Patient"
    wpi = pred.get("wpi", 0)
    risk = pred.get("risk_score", 0)
    band = wpi_barrier_band(wpi)
    
    lead = {
        "Lower barrier burden": f"{first} is on track to walk independently by discharge.",
        "Lower-intermediate barrier burden": f"{first} can realistically achieve walking with targeted work.",
        "Higher-intermediate barrier burden": f"{first} needs intensive rehabilitation to achieve walking.",
        "Higher barrier burden": f"Independent walking is a significant challenge for {first} at this point.",
    }[band]
    
    body = (
        f"There is a {pred.get('walk_prob', 0):.1f}% probability of walking independently "
        f"or with supervision by discharge. The WPI score of {wpi:.0f} points places {first} in the "
        f"'{band.lower()}' category, with a corresponding risk score of {risk:.1f}/10."
    )
    
    recs = []
    
    if band in ["Higher-intermediate barrier burden", "Higher barrier burden"]:
        recs.append("Intensive multidisciplinary rehabilitation is recommended.")
        recs.append("Consider additional therapies and regular review of the care plan.")
    
    if band == "Higher barrier burden":
        recs.append("Discuss realistic goals with the patient and family.")
        recs.append("Focus on functional gains rather than independent walking.")
    
    if band == "Lower-intermediate barrier burden":
        recs.append("Continue current rehabilitation plan with regular monitoring.")
        recs.append("Focus on building confidence and endurance.")
    
    if band == "Lower barrier burden":
        recs.append("Maintain current programme with a focus on discharge planning.")
        recs.append("Consider community-based rehabilitation options.")
    
    if previous is None:
        recs.append("This is the baseline assessment. Re-score every 2 weeks to track progress.")
    else:
        delta = pred.get("wpi", 0) - previous.get("wpi", 0)
        if delta > 3:
            recs.append(f"WPI improved by {delta:.0f} points — current plan is effective.")
        elif delta < -3:
            recs.append(f"WPI decreased by {abs(delta):.0f} points — check for infection, pain, or deconditioning.")
        else:
            recs.append("WPI stable. Consider reviewing the rehabilitation plan.")
    
    return {"lead": lead, "body": body, "recs": recs}