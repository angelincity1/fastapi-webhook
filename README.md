# FastAPI Webhook

A simple FastAPI server with a webhook endpoint, ready for deployment on Render.

## Endpoints

- `GET /` — Health check.
- `POST /webhook` — Accepts webhook payload.

## Local Development

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Deployment (Render)

1. Push this repo to GitHub.
2. Create a new Render Web Service:
    - Set **Environment** to Python.
    - Set **Build Command**: `pip install -r requirements.txt`
    - Set **Start Command**: `uvicorn main:app --host 0.0.0.0 --port 10000`
    - Leave **Root Directory** blank (unless files are in a subfolder).
3. Add `render.yaml` to the repo for automatic config (optional but recommended).

## Webhook Usage

Send a POST request with JSON body to `/webhook`.

```
curl -X POST https://your-service.onrender.com/webhook -H "Content-Type: application/json" -d '{"key":"value"}'
```
