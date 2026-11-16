# Free hosting guide (no credit card, no Docker)

Chosen host: **Render – free Web Service** (native Python).
Why: no card needed, 750 free hours/month (enough for one always-available service), builds straight from GitHub,
HTTPS URL included. This API uses ~175 MB RAM; the free instance has 512 MB.

Free-tier facts to know:
* It **sleeps after ~15 minutes without requests**; the next request takes ~30-60 s to wake it.
* Render may restart free services at any time. The model is inside the code, so nothing is lost.
* Free tiers change. Check render.com/pricing before you rely on it.

## Step 1 – Train the model on Kaggle (free, no card)
1. Make a free account at kaggle.com.
2. Zip this whole `ml_service` folder (or use `ml_service.zip` as it is).
3. Kaggle -> **Datasets -> New Dataset** -> upload the zip -> name it `ml-service` -> Create. (Kaggle unzips it for you.)
4. Kaggle -> **Code -> New Notebook** -> **File -> Import Notebook** -> choose `kaggle_train.ipynb`.
   (Or create an empty notebook and paste the cells.)
5. In the notebook: **+ Add Input** (top right) -> *Your Datasets* -> add `ml-service`.
6. Run the cells one by one. Cell 4 prints the accuracy report.
7. When it finishes, open the **Output** tab -> download `model_files.zip`.
8. Unzip it and copy the 4 files (`mean.txt`, `lo.txt`, `hi.txt`, `meta.json`) into your project's `models/` folder, replacing the old ones.
   Commit and push them to GitHub (Step 2). Render redeploys by itself.

Notes
* Internet and GPU are NOT needed. Leave them off (Kaggle may ask for phone verification to turn Internet on; you can skip that).
* The models are saved in LightGBM's text format, so it does not matter that Kaggle's library versions differ from Render's.
* Kaggle files are deleted when the session ends. Always download `model_files.zip` before closing.
* To train on real data later: export it with `export_real_data.sql`, upload the CSV as a second dataset, and use cell 3B instead of 3A.

### (Optional) Test on your own computer instead
```
pip install -r requirements-train.txt
python generate_synthetic.py && python train.py && python test_api.py
```

## Step 2 – Put the project on GitHub
1. Create a free account at github.com and click New repository (name: `appointment-predictor`, Private is fine).
2. Install Git, then in this folder:
```
git init
git add .
git commit -m "first version"
git branch -M main
git remote add origin https://github.com/YOUR_NAME/appointment-predictor.git
git push -u origin main
```
3. Open the repo on github.com and check these exist: `app.py`, `features.py`, `requirements.txt`,
   `models/mean.txt, lo.txt, hi.txt, meta.json`, `data/symptoms_1000.csv`.

## Step 3 – Create the service on Render
1. Go to render.com -> Sign up -> **Continue with GitHub**. No card is asked for the free plan.
2. Dashboard -> **New +** -> **Web Service** -> connect your repo.
3. Fill in:
   * Language/Runtime: **Python 3**
   * Branch: `main`
   * Build Command: `pip install -r requirements.txt`
   * Start Command: `uvicorn app:app --host 0.0.0.0 --port $PORT`
   * Instance Type: **Free**
4. Open **Advanced -> Environment Variables** and add:
   * `PYTHON_VERSION` = `3.12.3`
   * `API_KEY` = a long random secret (for example 40 random letters and numbers). Save it somewhere safe.
5. Click **Create Web Service**. The first build takes a few minutes (LightGBM and pandas are big downloads).
6. When the log says the service is live, you get a URL like `https://appointment-predictor-xxxx.onrender.com`.

(Shortcut: New + -> Blueprint reads `render.yaml` and fills this in for you.)

## Step 4 – Test the live API
```
curl https://YOUR-URL.onrender.com/health
curl -X POST https://YOUR-URL.onrender.com/predict -H "X-API-Key: YOUR_SECRET" -H "Content-Type: application/json" -d "{\"symptoms\":[\"Fever\"],\"age\":30}"
```
You can also open `https://YOUR-URL.onrender.com/docs` in the browser.
(If it hangs for a minute the first time, that is the free service waking up.)

## Step 5 – Keep it awake during clinic hours
Use your free Supabase database to ping the API (pg_cron + pg_net). In Supabase SQL editor:
```sql
create extension if not exists pg_cron;
create extension if not exists pg_net;

-- every 10 minutes, 08:00-22:59 Bangladesh time (= 02:00-16:59 UTC)
select cron.schedule('keep-predictor-awake', '*/10 2-16 * * *',
  $$ select net.http_get('https://YOUR-URL.onrender.com/health'); $$);
```
Stop it with `select cron.unschedule('keep-predictor-awake');`.
This uses about 450 hours a month, inside the 750 free hours. Do not also run a 24/7 pinger.

## Step 6 – Connect it to the app
Supabase Edge Function (keeps the secret away from the phone):
* In Supabase: Edge Functions -> Secrets -> add `ML_URL` and `ML_API_KEY`.
* The function receives the appointment, calls `POST {ML_URL}/predict` with header `X-API-Key`, and updates
  `appointments.predicted_duration_minutes`.
* IMPORTANT: use a timeout of ~60 s and fall back to the average duration of that symptom if the API is asleep or down.
  The app must never fail to book because the predictor is slow.

## Step 7 – Update the model later
Retrain on your computer -> `git add models/mean.txt, lo.txt, hi.txt, meta.json` -> `git commit` -> `git push`.
Render redeploys automatically.

## Other free options (checked, with limits)
| Option | Card? | Verdict |
|---|---|---|
| Render free web service | No | Recommended |
| Google Cloud Run | Yes | Needs a card |
| Fly.io | Yes | Needs a card |
| Koyeb | - | No free plan for new users since Feb 2026 |
| Railway | No | Only a 30-day $5 trial, then ~$1/month credit |
| PythonAnywhere free | No | No FastAPI (no ASGI), very small CPU limit; would need a Flask rewrite |
| SnapDeploy | No | Docker container host, 100 h/month, sleeps; backup option |
