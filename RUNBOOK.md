# RUNBOOK — QueueStorm Investigator

A stranger can bring this service up with the steps below. No secrets required.

## Option A — Run locally (Python)

Requires Python 3.10 or newer.

```bash
# 1. From the repository root
pip install -r requirements.txt

# 2. Start the service (binds 0.0.0.0:8000)
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 3. Verify
curl http://localhost:8000/health
# -> {"status":"ok"}

curl -X POST http://localhost:8000/analyze-ticket \
  -H "Content-Type: application/json" \
  -d @sample_request.json
```

To use a different port:

```bash
PORT=9000 uvicorn app.main:app --host 0.0.0.0 --port 9000
```

## Option B — Docker

```bash
# Build
docker build -t queuestorm .

# Run (maps container port 8000 to host 8000)
docker run -p 8000:8000 queuestorm

# Verify
curl http://localhost:8000/health
```

The image binds to `0.0.0.0` and reads `$PORT` (default 8000). No `--env-file`
is needed because the service runs with zero secrets. If you map a different
host port, the service still listens on 8000 inside the container unless you
override `PORT`:

```bash
docker run -e PORT=8080 -p 8080:8080 queuestorm
```

## Option C — Any cloud host (Render / Railway / Fly / EC2 / Poridhi Lab)

1. Push this repo.
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   (Most platforms inject `$PORT`. If not, default 8000 is used.)
4. No environment variables are required.
5. After deploy, confirm `GET /health` returns `{"status":"ok"}` and
   `POST /analyze-ticket` returns a 200 with the structured body.

## Smoke test against the public samples

```bash
PYTHONPATH=. python3 tests/run_samples.py
# Expects: 10/10 cases pass hard-key + safety equivalence
# (Edit the sample JSON path at the top of the script if needed.)
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| 404 on endpoints | Confirm exact routes `/health` and `/analyze-ticket` and the base URL. |
| Connection refused from outside | Ensure host is `0.0.0.0`, the correct port is exposed/mapped. |
| 400 on a valid-looking request | Body must be a JSON object with `ticket_id` and `complaint`. |
| Slow first request | Cold start only; warm responses are ~1 ms. |
