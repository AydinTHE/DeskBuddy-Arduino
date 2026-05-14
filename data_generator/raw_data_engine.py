import sqlite3
import random
import time
from datetime import datetime, timedelta

# Configuration
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
    """Calculates a focus percentage based on environmental factors."""
    score = 85
    if co2 > 900:
        score -= int((co2 - 900) / 50) * 3
    if co2 > 1200:
        score -= 10
    if temp > 27.0:
        score -= int((temp - 27.0) * 4)
    if temp < 19.0:
        score -= int((19.0 - temp) * 3)
    score -= distractions * 2
    score += random.randint(-5, 5)
    return max(10, min(100, score))

def calculate_posture(temp: float, co2: int) -> tuple[int, str]:
    """Calculates posture score and status string."""
    co2_ratio = max(0, (co2 - 800) / 600)
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
    """Generates a single set of realistic sensor and time data."""
    # Environment Logic
    temp = round(random.gauss(22.5 + (session_num % 10) * 0.2, 1.2), 1)
    temp = max(18.0, min(31.0, temp))

    base_co2 = 650 + (session_num % 10) * 40
    co2 = int(random.gauss(base_co2, 60))
    co2 = max(400, min(1800, co2))

    humidity = round(random.gauss(52, 6), 1)
    distractions = max(0, int(random.gauss(2, 1.5)))

    # Scoring Logic
    focus_score = calculate_focus_score(temp, co2, distractions)
    posture_score, posture_status = calculate_posture(temp, co2)

    # TIME VARIANCE LOGIC (The "Real Human" Feel)
    # Focus minutes vary between 15 and 50 minutes
    focus_minutes = random.randint(15, 50)
    # Break minutes vary between 3 and 15 minutes
    break_minutes = random.randint(3, 15)

    return {
        "temperature_c": temp,
        "humidity_pct": humidity,
        "co2_ppm": co2,
        "posture_status": posture_status,
        "posture_score": posture_score,
        "focus_score": focus_score,
        "distractions": distractions,
        "focus_minutes": focus_minutes,
        "break_minutes": break_minutes,
    }

def seed_database(num_sessions: int = 10, delay_seconds: int = 5):
    """
    Inserts data into the DB one by one with a delay to mimic 
    a real-time IoT device feeding a dashboard.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
    except sqlite3.OperationalError:
        print(f"❌ Error: Could not find database at {DB_PATH}. Run database.py first!")
        return

    print(f"\n🚀 [DeskBuddy Engine] Starting Natural Simulation...")
    print(f"📊 Mode: Live Feed | Delay: {delay_seconds}s | Sessions: {num_sessions}")
    print(f"\n  {'Timestamp':<20} {'Label':<22} {'Focus':<8} {'Break':<8} {'Status'}")
    print("  " + "-" * 75)

    for i in range(num_sessions):
        data = simulate_sensor_reading(i)
        
        # Use real current time for the live dashboard feel
        now = datetime.now()
        ts = now.strftime("%Y-%m-%d %H:%M:%S")
        
        label = SESSION_LABELS[i % len(SESSION_LABELS)]
        hour = now.strftime("%I %p").lstrip('0')

        try:
            # 1. Insert into study_sessions (Environment & Quality)
            cursor.execute("""
                INSERT INTO study_sessions
                    (timestamp, temperature_c, humidity_pct, co2_ppm, 
                     posture_status, posture_score, focus_score, session_label)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ts, data["temperature_c"], data["humidity_pct"], data["co2_ppm"],
                data["posture_status"], data["posture_score"], data["focus_score"], label
            ))

            # 2. Insert into focus_data (Time Tracking)
            cursor.execute("""
                INSERT INTO focus_data
                    (timestamp, hour_label, focus_minutes, break_minutes, distractions)
                VALUES (?, ?, ?, ?, ?)
            """, (
                ts, hour, data["focus_minutes"], data["break_minutes"], data["distractions"]
            ))

            conn.commit()
            
            print(f"  {ts:<20} {label:<22} {data['focus_minutes']:>2} min   {data['break_minutes']:>2} min   {data['posture_status']}")

        except sqlite3.Error as e:
            print(f"❌ Database Error: {e}")
            break

        # Natural delay before next "reading"
        if i < num_sessions - 1:
            time.sleep(delay_seconds)

    conn.close()
    print(f"\n🏁 [Done] {num_sessions} sessions pushed. Dashboard is now up to date.")

if __name__ == "__main__":
    # Change num_sessions to how many points you want on your chart.
    # Change delay_seconds to control how fast the "live" updates happen.
    seed_database(num_sessions=10, delay_seconds=10)