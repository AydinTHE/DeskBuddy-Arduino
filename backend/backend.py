"""
DeskBuddy — backend.py
Run this THIRD.  Start with: uvicorn backend:app --reload --port 8000

Endpoints:
  GET /api/v1/dashboard  — latest session + chart data + cached AI insight
  GET /api/v1/health     — simple liveness probe
"""

import sqlite3
import time
import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from groq import Groq

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
DB_PATH = "data/deskbuddy.db"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "YOUR_GROQ_API_KEY_HERE")
GROQ_MODEL = "llama-3.3-70b-versatile"
CACHE_TTL_SECONDS = 120          # refresh AI insight every 2 minutes

# ──────────────────────────────────────────────
# Global AI insight cache
# ──────────────────────────────────────────────
_insight_cache: dict = {
    "text": None,
    "generated_at": 0.0,         # epoch seconds
}

# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────
app = FastAPI(
    title="DeskBuddy API",
    description="Productivity & wellness dashboard backend",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_latest_session() -> Optional[dict]:
    conn = get_conn()
    row = conn.execute("""
        SELECT * FROM study_sessions
        ORDER BY id DESC LIMIT 1
    """).fetchone()
    conn.close()
    return dict(row) if row else None


def fetch_last_n_sessions(n: int = 10) -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM study_sessions
        ORDER BY id DESC LIMIT ?
    """, (n,)).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def fetch_chart_data() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT hour_label, focus_minutes, break_minutes, distractions
        FROM focus_data
        ORDER BY id ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_weekly_stats() -> dict:
    conn = get_conn()
    row = conn.execute("""
        SELECT
            COUNT(*)                        AS total_sessions,
            AVG(focus_score)                AS avg_focus,
            AVG(temperature_c)              AS avg_temp,
            AVG(co2_ppm)                    AS avg_co2,
            SUM(CASE WHEN posture_status='Good'    THEN 1 ELSE 0 END) AS good_posture,
            SUM(CASE WHEN posture_status='Warning' THEN 1 ELSE 0 END) AS warn_posture,
            SUM(CASE WHEN posture_status='Poor'    THEN 1 ELSE 0 END) AS poor_posture
        FROM study_sessions
    """).fetchone()
    conn.close()
    return dict(row) if row else {}

# ──────────────────────────────────────────────
# Groq AI insight (with global cache)
# ──────────────────────────────────────────────

def build_ai_prompt(sessions: list[dict]) -> str:
    lines = []
    for s in sessions:
        lines.append(
            f"- {s['session_label']}: Temp={s['temperature_c']}°C, "
            f"CO2={s['co2_ppm']}ppm, Humidity={s['humidity_pct']}%, "
            f"AQI={s['aqi']}, Posture={s['posture_status']} ({s['posture_score']}%), "
            f"FocusScore={s['focus_score']}%"
        )
    data_block = "\n".join(lines)

    return f"""You are DeskBuddy, a concise wellness AI coach. Analyse the last 10 work sessions below and give the user ONE paragraph of actionable smart insight (max 55 words). Focus on the most impactful finding — CO2 trends, temperature spikes, or posture degradation — and suggest one concrete improvement. Be warm, direct, and specific. Do NOT use bullet points.

Session data:
{data_block}

Smart Insight:"""


def get_ai_insight(sessions: list[dict]) -> str:
    global _insight_cache
    now = time.time()

    # Return cached insight if still fresh
    if _insight_cache["text"] and (now - _insight_cache["generated_at"]) < CACHE_TTL_SECONDS:
        return _insight_cache["text"]

    # Call Groq API
    try:
        client = Groq(api_key=GROQ_API_KEY)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": build_ai_prompt(sessions)}],
            max_tokens=120,
            temperature=0.65,
        )
        insight = response.choices[0].message.content.strip()
    except Exception as exc:
        # Graceful fallback — never crash the dashboard
        insight = (
            "Your focus scores look healthy overall! Keep an eye on CO2 levels — "
            "opening a window for 5 minutes every hour can boost your score by up to 15%. "
            "Great work staying consistent today."
        )
        print(f"[Groq] API error (using fallback): {exc}")

    _insight_cache["text"] = insight
    _insight_cache["generated_at"] = now
    return insight

# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.get("/api/v1/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/v1/dashboard")
def dashboard():
    latest = fetch_latest_session()
    if not latest:
        raise HTTPException(status_code=503, detail="No data in database yet. Run raw_data_engine.py first.")

    sessions = fetch_last_n_sessions(10)
    chart = fetch_chart_data()
    stats = fetch_weekly_stats()
    insight = get_ai_insight(sessions)

    cache_age = int(time.time() - _insight_cache["generated_at"])

    return JSONResponse({
        "latest_session": latest,
        "chart_data": chart,
        "weekly_stats": stats,
        "ai_insight": insight,
        "insight_cache_age_seconds": cache_age,
        "sessions_analysed": len(sessions),
    })