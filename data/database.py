"""
DeskBuddy — database.py
Run this FIRST to initialize the SQLite database.
"""

import sqlite3
import os

DB_PATH = "data/deskbuddy.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Table 1: study_sessions — environment & posture snapshot per session
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS study_sessions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
            temperature_c   REAL NOT NULL,
            humidity_pct    REAL NOT NULL,
            co2_ppm         INTEGER NOT NULL,
            aqi             INTEGER NOT NULL,
            posture_status  TEXT NOT NULL,   -- 'Good' | 'Warning' | 'Poor'
            posture_score   INTEGER NOT NULL, -- 0–100
            focus_score     INTEGER NOT NULL, -- 0–100 (calculated)
            session_label   TEXT NOT NULL    -- e.g. 'Morning Session 1'
        )
    """)

    # Table 2: focus_data — time-series chart history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS focus_data (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp     DATETIME DEFAULT CURRENT_TIMESTAMP,
            hour_label    TEXT NOT NULL,     -- e.g. '9 AM'
            focus_minutes INTEGER NOT NULL,
            break_minutes INTEGER NOT NULL,
            distractions  INTEGER NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    print(f"[DB] Initialized database at '{DB_PATH}' — tables ready.")


if __name__ == "__main__":
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"[DB] Removed existing '{DB_PATH}' for a fresh start.")
    init_db()