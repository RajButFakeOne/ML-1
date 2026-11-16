FROM python:3.12-slim

# LightGBM needs this small system library
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY features.py app.py ./
COPY data/symptoms_1000.csv data/symptoms_1000.csv
COPY models/ models/

# Cloud Run gives the port in $PORT
CMD exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080}
