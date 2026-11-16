"""Shared feature code. Used by training AND by the API, so both always agree."""
import re
import numpy as np
import pandas as pd

CAT_COLS = ["doctor_id", "specialty", "category", "symptom_id"]
NUM_COLS = [
    "is_followup", "is_review", "is_advice", "is_child", "is_infant", "is_elderly_kw",
    "is_pregnancy", "is_severe", "has_duration", "n_symptoms",
    "age", "is_female", "hour", "weekday", "queue_position", "doc_avg_today",
]
FEATURES = CAT_COLS + NUM_COLS


def symptom_flags(text: str) -> dict:
    """Turn symptom words into simple 0/1 flags (works even for symptoms never seen before)."""
    t = (text or "").lower()
    return {
        "is_followup": int(bool(re.search(r"follow-up|follow up|post-|recovery", t))),
        "is_review": int(bool(re.search(r"review|report", t))),
        "is_advice": int(bool(re.search(r"advice|check-up|check up|certificate|screening|test$", t))),
        "is_child": int(bool(re.search(r"\bchild\b|\bteen\b|school", t))),
        "is_infant": int(bool(re.search(r"baby|newborn|infant|teething", t))),
        "is_elderly_kw": int(bool(re.search(r"elderly|old age|bed-ridden", t))),
        "is_pregnancy": int(bool(re.search(r"pregnan|labor|postnatal|postpartum|trimester", t))),
        "is_severe": int(bool(re.search(r"severe|sudden|blood|heavy|seizure|fits|stroke|fracture|faint", t))),
        "has_duration": int(bool(re.search(r"since|for \d+|for a (week|month)", t))),
    }


class SymptomCatalog:
    """Looks up a symptom name -> (id, category, specialty)."""

    def __init__(self, csv_path: str):
        df = pd.read_csv(csv_path)
        self.df = df
        self.by_name = {r.symptom.lower(): (int(r.id), r.category, r.specialty) for r in df.itertuples()}

    def lookup(self, name: str):
        return self.by_name.get(name.strip().lower(), (-1, "Unknown", "Unknown"))


def build_row(symptoms, catalog, specialty, doctor_id, age, gender, hour, weekday,
              queue_position, doc_avg_today):
    """One patient -> one feature row (dict). `symptoms` is a list of names (1 or more)."""
    symptoms = [s for s in symptoms if s and s.strip()] or ["Unknown"]
    primary = symptoms[0]
    sid, cat, spec_from_symptom = catalog.lookup(primary)
    flags = {k: 0 for k in symptom_flags("").keys()}
    for s in symptoms:  # a flag is on if ANY chosen symptom has it
        for k, v in symptom_flags(s).items():
            flags[k] = max(flags[k], v)
    row = {
        "doctor_id": str(doctor_id) if doctor_id else None,
        "specialty": specialty or spec_from_symptom,
        "category": cat,
        "symptom_id": str(sid),
        **flags,
        "n_symptoms": len(symptoms),
        "age": np.nan if age is None else float(age),
        "is_female": np.nan if not gender else float(str(gender).lower().startswith("f")),
        "hour": np.nan if hour is None else float(hour),
        "weekday": np.nan if weekday is None else float(weekday),
        "queue_position": np.nan if queue_position is None else float(queue_position),
        "doc_avg_today": np.nan if doc_avg_today is None else float(doc_avg_today),
    }
    return row


def to_frame(rows, categories):
    """Rows -> DataFrame with fixed categorical levels (unknown values become NaN = 'unknown')."""
    df = pd.DataFrame(rows)
    for c in CAT_COLS:
        df[c] = pd.Categorical(df[c].astype("object"), categories=categories[c])
    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[FEATURES]
