import os
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google.cloud import aiplatform

app = FastAPI(title="Oura Health Report")

PROJECT_ID = os.environ["PROJECT_ID"]
LOCATION = os.environ.get("LOCATION", "us-central1")
ENDPOINT_ID = os.environ["ENDPOINT_ID"]
OURA_API_TOKEN = os.environ["OURA_API_TOKEN"]
HTTP_TIMEOUT_SECONDS = int(os.environ.get("HTTP_TIMEOUT_SECONDS", "20"))
BASELINE_DAYS = int(os.environ.get("BASELINE_DAYS", "45"))

aiplatform.init(project=PROJECT_ID, location=LOCATION)
endpoint = aiplatform.Endpoint(
    f"projects/{PROJECT_ID}/locations/{LOCATION}/endpoints/{ENDPOINT_ID}"
)


class AnalyzeRequest(BaseModel):
    as_of_date: Optional[str] = None


def oura_get(path: str, start_date: str) -> Dict[str, Any]:
    headers = {"Authorization": f"Bearer {OURA_API_TOKEN}"}
    url = f"https://api.ouraring.com/v2/usercollection/{path}?start_date={start_date}"
    r = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS)
    r.raise_for_status()
    return r.json()


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    try:
        now = datetime.utcnow().date()
        as_of = datetime.strptime(req.as_of_date, "%Y-%m-%d").date() if req.as_of_date else now
        start_date = (as_of - timedelta(days=BASELINE_DAYS)).strftime("%Y-%m-%d")

        readiness = oura_get("daily_readiness", start_date).get("data", [])
        daily_sleep = oura_get("daily_sleep", start_date).get("data", [])
        sleep = oura_get("sleep", start_date).get("data", [])

        if not readiness or not daily_sleep:
            raise HTTPException(status_code=400, detail="No Oura data found")

        latest_readiness = readiness[-1]
        latest_daily_sleep = daily_sleep[-1]

        avg_hr = None
        avg_hrv = None
        if sleep:
            latest_sleep = sleep[-1]
            avg_hr = latest_sleep.get("average_heart_rate")
            avg_hrv = latest_sleep.get("average_hrv")

        risk = "green"
        signals: List[str] = []

        temp_dev = latest_readiness.get("temperature_deviation")
        readiness_score = latest_readiness.get("score")
        sleep_score = latest_daily_sleep.get("score")

        if isinstance(temp_dev, (int, float)) and temp_dev >= 0.5:
            risk = "orange"
            signals.append("Temperature deviation elevated")
        if isinstance(readiness_score, int) and readiness_score < 70:
            risk = "yellow" if risk == "green" else risk
            signals.append("Readiness score below preferred range")
        if isinstance(sleep_score, int) and sleep_score < 70:
            risk = "yellow" if risk == "green" else risk
            signals.append("Sleep score below preferred range")

        prompt = {
            "task": "Explain today's Oura results in plain English.",
            "risk_level": risk,
            "signals": signals,
            "metrics": {
                "readiness_score": readiness_score,
                "sleep_score": sleep_score,
                "temperature_deviation": temp_dev,
                "average_heart_rate": avg_hr,
                "average_hrv": avg_hrv,
            },
            "output_format": {
                "summary": "string",
                "recommended_actions": ["string"],
                "escalation_advice": "string",
                "disclaimer": "string",
            },
        }

        response = endpoint.predict(
            instances=[{"prompt": json.dumps(prompt)}],
            parameters={"max_output_tokens": 500, "temperature": 0.2},
        )

        return {
            "status": "success",
            "risk_level": risk,
            "signals": signals,
            "oura": {
                "readiness_score": readiness_score,
                "sleep_score": sleep_score,
                "temperature_deviation": temp_dev,
                "average_heart_rate": avg_hr,
                "average_hrv": avg_hrv,
            },
            "model_output": response.predictions[0],
        }
    except requests.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Oura API error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
