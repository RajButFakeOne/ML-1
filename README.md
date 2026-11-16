# Appointment time predictor

Predicts how long each consultation will take (from symptom, doctor, age, queue position...)
and adds the times up to tell each patient when to come.

| File | What it does |
|---|---|
| `generate_synthetic.py` | makes FAKE history so you can test everything today |
| `export_real_data.sql` | pulls REAL history from Supabase (use this once you have data) |
| `train.py` | trains the model, compares it with a simple-average baseline, saves `models/mean.txt, lo.txt, hi.txt, meta.json` |
| `features.py` | turns a patient into numbers (shared by training and the API) |
| `app.py` | the web API (FastAPI): `/predict`, `/queue/estimate`, `/health` |
| `Dockerfile` | packs the API for Cloud Run / Render |

## 1. Train: on Kaggle (see HOSTING.md, Step 1) or on your computer
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-train.txt
python generate_synthetic.py      # fake data  (skip when you have real data)
python train.py                   # prints the accuracy report
python test_api.py                # quick check
uvicorn app:app --reload          # open http://127.0.0.1:8000/docs  to try it in the browser
```

## 2. Train on REAL data (when ready)
1. Run `export_real_data.sql` in Supabase, download the CSV to `data/real_data.csv`.
2. `python train.py --data data/real_data.csv`
3. Look at the report. Use the model only if "MAE LightGBM" is clearly lower than "MAE baseline".
   Rule of thumb: below ~2,000 completed visits the simple averages are about as good; keep logging data.

## 3. Host for FREE (no card, no Docker): Render
Full step-by-step guide is in HOSTING.md. Short version:
1. Put this folder on GitHub (free account).
2. render.com -> sign in with GitHub -> New -> Web Service -> pick the repo.
3. Runtime Python 3, Build `pip install -r requirements.txt`, Start `uvicorn app:app --host 0.0.0.0 --port $PORT`, Plan Free.
4. Add env var API_KEY (a long random secret). Deploy.
(`Dockerfile` is optional and only needed if you ever move to a Docker host.)

## 4. Connect to the app (summary)
Flutter -> Supabase (Edge Function holds the URL + API_KEY secret) -> this API -> result saved in
`appointments.predicted_duration_minutes` -> Flutter listens with Supabase Realtime.
Never put the API_KEY inside the Flutter app.

## 5. Keep it healthy
* Retrain monthly (or weekly at first): export -> `train.py` -> redeploy.
* Compare `predicted_duration_minutes` with `actual_duration_minutes` and watch the average error.
* Filter bad rows (done in `train.py`: under 2 or over 90 minutes dropped).
