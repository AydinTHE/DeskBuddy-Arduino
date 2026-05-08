"""
DeskBuddy — raw_data_engine.py
Run this SECOND (after database.py) to seed the DB with simulated sensor data.

Sensor → Calculation Logic:
  - Focus Score  = base 80, penalised by CO2 > 900, Temp > 27°C, high distractions
  - Posture Score = 100 − (CO2_excess_ratio * 20) − (temp_excess * 5) − random fatigue
  - Posture Status = 'Good' (≥75), 'Warning' (50–74), 'Poor' (<50)
"""

import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "data/deskbuddy.db"

SESSION_LABELS = [
    "Early Bird Warm-Up",
    "Morning Deep Work",
    "Pre-Break Focus",
    "Post-Breakfast Grind",
    "Mid-Morning Sprint",
    "Late Morning Push",
    "Pre-Lunch Wrap-Up",
    "Afternoon Kickstart",
    "Golden Hour Focus",
    "End-of-Day Review",
]

HOUR_LABELS = [
    "7 AM", "8 AM", "9 AM", "10 AM", "11 AM",
    "12 PM", "1 PM", "2 PM", "3 PM", "4 PM",
]


def calculate_focus_score(temp: float, co2: int, distractions: int) -> int:
    score = 85
    if co2 > 900:
        score -= int((co2 - 900) / 50) * 3   # -3 pts per 50ppm above threshold
    if co2 > 1200:
        score -= 10                            # severe penalty above 1200ppm
    if temp > 27.0:
        score -= int((temp - 27.0) * 4)       # -4 pts per degree above comfort
    if temp < 19.0:
        score -= int((19.0 - temp) * 3)       # too cold also hurts
    score -= distractions * 2                 # each distraction costs 2pts
    score += random.randint(-5, 5)            # sensor noise
    return max(10, min(100, score))


def calculate_posture(temp: float, co2: int) -> tuple[int, str]:
    co2_ratio = max(0, (co2 - 800) / 600)    # 0 at 800ppm, 1 at 1400ppm
    temp_excess = max(0, temp - 26.5)
    fatigue = random.uniform(0, 12)

    posture_score = int(100 - (co2_ratio * 25) - (temp_excess * 6) - fatigue)
    posture_score = max(5, min(100, posture_score))

    if posture_score >= 75:
        status = "Good"
    elif posture_score >= 50:
        status = "Warning"
    else:
        status = "Poor"

    return posture_score, status


def simulate_sensor_reading(session_num: int) -> dict:
    """Simulate raw IoT sensor data with realistic variance over a workday."""
    # Temperature drifts up through the day
    temp = round(random.gauss(22.5 + session_num * 0.3, 1.2), 1)
    temp = max(18.0, min(31.0, temp))

    # CO2 accumulates in poorly ventilated rooms; dips after breaks
    base_co2 = 650 + session_num * 55
    if session_num in (3, 7):           # post-break windows
        base_co2 -= 120
    co2 = int(random.gauss(base_co2, 60))
    co2 = max(400, min(1800, co2))

    humidity = round(random.gauss(52, 6), 1)
    humidity = max(30.0, min(80.0, humidity))

    aqi = int(random.gauss(28 + session_num * 1.5, 5))
    aqi = max(5, min(150, aqi))

    distractions = max(0, int(random.gauss(4 - (session_num % 3), 2)))

    focus_score = calculate_focus_score(temp, co2, distractions)
    posture_score, posture_status = calculate_posture(temp, co2)

    # Chart data (slightly different from session aggregate)
    focus_minutes = int(focus_score * 0.45 + random.randint(0, 10))
    break_minutes = random.randint(5, 20)

    return {
        "temperature_c": temp,
        "humidity_pct": humidity,
        "co2_ppm": co2,
        "aqi": aqi,
        "posture_status": posture_status,
        "posture_score": posture_score,
        "focus_score": focus_score,
        "distractions": distractions,
        "focus_minutes": focus_minutes,
        "break_minutes": break_minutes,
    }


def seed_database(num_sessions: int = 10):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    base_time = datetime.now() - timedelta(hours=num_sessions)

    print(f"\n[Engine] Seeding {num_sessions} simulated sessions...\n")
    print(f"  {'Label':<28} {'Temp':>6} {'CO2':>6} {'Posture':<9} {'Focus':>6}")
    print("  " + "-" * 60)

    for i in range(num_sessions):
        data = simulate_sensor_reading(i)
        ts = (base_time + timedelta(hours=i)).strftime("%Y-%m-%d %H:%M:%S")
        label = SESSION_LABELS[i % len(SESSION_LABELS)]
        hour = HOUR_LABELS[i % len(HOUR_LABELS)]

        cursor.execute("""
            INSERT INTO study_sessions
                (timestamp, temperature_c, humidity_pct, co2_ppm, aqi,
                 posture_status, posture_score, focus_score, session_label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ts,
            data["temperature_c"],
            data["humidity_pct"],
            data["co2_ppm"],
            data["aqi"],
            data["posture_status"],
            data["posture_score"],
            data["focus_score"],
            label,
        ))

        cursor.execute("""
            INSERT INTO focus_data
                (timestamp, hour_label, focus_minutes, break_minutes, distractions)
            VALUES (?, ?, ?, ?, ?)
        """, (
            ts,
            hour,
            data["focus_minutes"],
            data["break_minutes"],
            data["distractions"],
        ))

        print(f"  {label:<28} {data['temperature_c']:>5.1f}°  {data['co2_ppm']:>5}ppm  "
              f"{data['posture_status']:<9} {data['focus_score']:>4}%")

    conn.commit()
    conn.close()
    print(f"\n[Engine] Done. {num_sessions} sessions written to '{DB_PATH}'.")


if __name__ == "__main__":
    seed_database(10)