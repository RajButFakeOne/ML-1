"""
Prediction API.
  POST /predict          -> how long will ONE consultation take?
  POST /queue/estimate   -> when will each patient in today's queue start?  (your "come at 9:00" idea)
  GET  /health
Run locally:  uvicorn app:app --reload
"""
import json, math, os, warnings
from datetime import datetime, timedelta
from typing import List, Optional

import lightgbm as lgb
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from features import SymptomCatalog, build_row, to_frame

warnings.filterwarnings("ignore")
API_KEY = os.getenv("API_KEY", "")          # set this in Cloud Run / Render. Empty = no check (local only)
GAP_MIN = float(os.getenv("GAP_MIN", "1.0")) # minutes lost between two patients (walking, writing, etc.)
Z80 = 1.2816                                 # a 10%-90% range is +/-1.28 standard deviations

meta = json.load(open("models/meta.json"))
art = {"mean": lgb.Booster(model_file="models/mean.txt"),
       "lo": lgb.Booster(model_file="models/lo.txt"),
       "hi": lgb.Booster(model_file="models/hi.txt"),
       "categories": meta["categories"], "trained_on": meta["trained_on"], "mae_test": meta["mae_test"]}
catalog = SymptomCatalog("data/symptoms_1000.csv")
app = FastAPI(title="Appointment time predictor")


def check_key(x_api_key: str = Header(default="")):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(401, "bad api key")


class PatientIn(BaseModel):
    symptoms: List[str] = Field(..., min_length=1, description="Symptom names chosen by the patient")
    doctor_id: Optional[str] = None
    specialty: Optional[str] = None
    age: Optional[float] = None
    gender: Optional[str] = None
    queue_position: Optional[int] = None
    hour: Optional[int] = None
    weekday: Optional[int] = None
    doctor_avg_today: Optional[float] = None


def run_model(patients: List[PatientIn], default_hour=None, default_weekday=None):
    rows = [build_row(p.symptoms, catalog, p.specialty, p.doctor_id, p.age, p.gender,
                      p.hour if p.hour is not None else default_hour,
                      p.weekday if p.weekday is not None else default_weekday,
                      p.queue_position, p.doctor_avg_today) for p in patients]
    X = to_frame(rows, art["categories"])
    mean = art["mean"].predict(X); lo = art["lo"].predict(X); hi = art["hi"].predict(X)
    out = []
    for m, l, h in zip(mean, lo, hi):
        m = max(float(m), 2.0); l = min(max(float(l), 1.0), m); h = max(float(h), m)
        out.append((m, l, h, max((h - l) / (2 * Z80), 0.5)))   # mean, low, high, std-dev
    return out


@app.get("/health")
def health():
    return {"ok": True, "trained_on": art["trained_on"], "mae_test_min": round(art["mae_test"], 2)}


@app.post("/predict", dependencies=[Depends(check_key)])
def predict(p: PatientIn):
    m, l, h, _ = run_model([p], datetime.now().hour, datetime.now().weekday())[0]
    return {"predicted_duration_minutes": round(m, 1), "low": round(l, 1), "high": round(h, 1)}


class QueueItem(PatientIn):
    appointment_id: str
    queue_serial: int
    status: str                                   # Scheduled / Confirmed / In_Progress / Completed / Skipped / Cancelled
    minutes_elapsed: Optional[float] = None       # only for In_Progress: minutes since the doctor pressed Start
    predicted_duration_minutes: Optional[float] = None   # if you already stored it, we reuse it


class QueueIn(BaseModel):
    now: datetime
    session_start: Optional[datetime] = None      # used only if nobody has been started yet
    items: List[QueueItem]


@app.post("/queue/estimate", dependencies=[Depends(check_key)])
def queue_estimate(q: QueueIn):
    items = sorted(q.items, key=lambda i: i.queue_serial)
    live = [i for i in items if i.status in ("Scheduled", "Confirmed", "In_Progress")]
    preds = run_model(live, q.now.hour, q.now.weekday())
    cursor = max(q.now, q.session_start) if q.session_start else q.now   # nothing before "now" can still happen
    mean_sum, var_sum, out = 0.0, 0.0, []
    for it, (m, l, h, sd) in zip(live, preds):
        if it.predicted_duration_minutes:                      # keep a stored value stable if present
            m = it.predicted_duration_minutes
        remaining = m
        if it.status == "In_Progress":                          # already inside: only the rest of the time counts
            remaining = max(m - (it.minutes_elapsed or 0), 0.3 * m, 1.0)
            start_mean = 0.0
        else:
            start_mean = mean_sum
        std_ahead = math.sqrt(var_sum)
        est = cursor + timedelta(minutes=start_mean)
        out.append({
            "appointment_id": it.appointment_id, "queue_serial": it.queue_serial,
            "status": it.status,
            "predicted_duration_minutes": round(m, 1),
            "estimated_start": est.isoformat(),
            "earliest_start": (est - timedelta(minutes=Z80 * std_ahead)).isoformat() if it.status != "In_Progress" else est.isoformat(),
            "latest_start": (est + timedelta(minutes=Z80 * std_ahead)).isoformat() if it.status != "In_Progress" else est.isoformat(),
            "wait_minutes": round(start_mean, 1),
        })
        mean_sum += remaining + GAP_MIN
        var_sum += sd ** 2 if it.status != "In_Progress" else (sd * 0.6) ** 2
    return {"generated_at": q.now.isoformat(), "patients": out}
