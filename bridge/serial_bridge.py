"""
DeskBuddy — serial_bridge.py
The bridge between Arduino (USB Serial) and the DeskBuddy backend.

Reads raw sensor JSON from Arduino over COM port, converts to real
units, runs posture detection + Pomodoro logic, writes to SQLite,
and sends feedback commands back to the Arduino.

Usage:
  python serial_bridge.py
  python serial_bridge.py --port COM7 --baud 115200
"""

import serial
import serial.tools.list_ports
import json
import sqlite3
import time
import argparse
import sys
import os
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────
# Config & Defaults
# ──────────────────────────────────────────────
DEFAULT_PORT = "COM7"
DEFAULT_BAUD = 115200
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "deskbuddy.db")

# Session save interval (seconds) — how often we write a session row to DB
SESSION_SAVE_INTERVAL = 60  # 1 minute

# Pomodoro defaults (can be overridden via settings file)
DEFAULT_FOCUS_MIN = 25
DEFAULT_BREAK_MIN = 5

# Settings file — the frontend/backend can write user prefs here
SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "bridge_settings.json")

# ──────────────────────────────────────────────
# Sensor Conversion Functions
# ──────────────────────────────────────────────
#BURA IŞLEMEYE BİLER TEST ETTİR
def raw_to_temperature(raw: int) -> float:
    """Convert NTC thermistor analog reading (0-1023) to °C.
    Assumes a 10kΩ NTC thermistor with a 10kΩ series resistor
    in a voltage divider (5V -- Thermistor -- A2 -- Resistor -- GND).
    Uses the Beta parameter equation.
    """
    import math

    if raw <= 0:
        return -40.0
    if raw >= 1023:
        return 125.0

    # Thermistor parameters (10kΩ NTC)
    SERIES_RESISTOR = 10000.0   # 10kΩ series resistor
    THERMISTOR_NOMINAL = 10000.0  # 10kΩ at 25°C
    TEMP_NOMINAL = 25.0          # 25°C reference
    B_COEFFICIENT = 3950.0       # Beta coefficient

    # Calculate thermistor resistance
    resistance = SERIES_RESISTOR * (1023.0 / raw - 1.0)

    # Beta equation (simplified Steinhart-Hart)
    steinhart = math.log(resistance / THERMISTOR_NOMINAL) / B_COEFFICIENT
    steinhart += 1.0 / (TEMP_NOMINAL + 273.15)
    temp_c = (1.0 / steinhart) - 273.15

    return round(max(-40.0, min(125.0, temp_c)), 1)
#BURA IŞLEMEYE BİLER TEST ETTİR (TEMP CALCULATOR)

def raw_to_co2(raw: int) -> int:
    """Convert MQ135 analog reading (0-1023) to estimated CO2 ppm.
    MQ135 is not precision — this is a rough mapping.
    Typical range: 400 ppm (fresh air) to ~2000 ppm (stuffy room).
    """
    ppm = int((raw / 1023.0) * 1600 + 400)
    return max(400, min(2000, ppm))


def raw_to_aqi(raw: int) -> int:
    """Convert MQ135 analog reading to a simple AQI estimate.
    Uses the same sensor as CO2 — maps to a 0–150 AQI scale.
    """
    aqi = int((raw / 1023.0) * 150)
    return max(0, min(150, aqi))


def raw_to_light(raw: int) -> int:
    """Return light level as-is (0-1023). Higher = brighter."""
    return raw


# ──────────────────────────────────────────────
# Posture Detection
# ──────────────────────────────────────────────

class PostureTracker:
    """Tracks posture using ultrasonic distance readings."""

    def __init__(self):
        self.baseline = None         # calibrated "good posture" distance
        self.grace_start = None      # when bad posture was first detected
        self.grace_period = 7.0      # seconds before triggering alarm
        self.tolerance_near = 10     # cm closer than baseline = bad
        self.tolerance_far = 15      # cm farther than baseline = bad
        self.current_status = "Good"
        self.posture_score = 100
        self.user_away = False

        # Rolling stats for score calculation
        self._good_count = 0
        self._total_count = 0

    def calibrate(self, distance: int):
        """Set baseline distance (should be called when user is sitting properly)."""
        self.baseline = distance
        self.grace_start = None
        self.current_status = "Good"
        self.posture_score = 100
        self._good_count = 0
        self._total_count = 0
        print(f"  [Posture] Calibrated baseline: {distance} cm")

    def update(self, distance: int) -> dict:
        """Process a new distance reading. Returns posture status dict."""
        if self.baseline is None:
            return {"status": "Uncalibrated", "score": 0, "away": True}

        self._total_count += 1

        # User away detection
        if distance < 0 or distance > 150:
            self.user_away = True
            self.grace_start = None
            return {"status": "Away", "score": self.posture_score, "away": True}

        self.user_away = False

        # Check if distance is within acceptable range
        if (distance < (self.baseline - self.tolerance_near) or
                distance > (self.baseline + self.tolerance_far)):
            # Bad posture detected
            if self.grace_start is None:
                self.grace_start = time.time()
                self.current_status = "Warning"
            elif time.time() - self.grace_start >= self.grace_period:
                self.current_status = "Poor"
            else:
                self.current_status = "Warning"
        else:
            # Good posture
            self.grace_start = None
            self.current_status = "Good"
            self._good_count += 1

        # Calculate rolling posture score (0-100)
        if self._total_count > 0:
            self.posture_score = int((self._good_count / self._total_count) * 100)
            self.posture_score = max(0, min(100, self.posture_score))

        return {
            "status": self.current_status,
            "score": self.posture_score,
            "away": False,
            "distance": distance,
        }


# ──────────────────────────────────────────────
# Pomodoro Timer
# ──────────────────────────────────────────────

class PomodoroTimer:
    """Pomodoro timer that tracks work/break cycles."""

    def __init__(self, work_min=25, break_min=5):
        self.work_secs = work_min * 60
        self.break_secs = break_min * 60
        self.remaining = self.work_secs
        self.is_work = True
        self.running = False
        self.session = 1
        self.last_tick = None
        self._just_switched = False  # flag for transition events

    def update_intervals(self, work_min: int, break_min: int):
        """Update work/break durations from user settings."""
        self.work_secs = work_min * 60
        self.break_secs = break_min * 60
        # If not running and in work mode, update remaining
        if not self.running and self.is_work:
            self.remaining = self.work_secs

    def start(self):
        self.running = True
        self.last_tick = time.time()

    def pause(self):
        self.running = False

    def reset(self):
        self.running = False
        self.is_work = True
        self.remaining = self.work_secs
        self.session = 1

    def tick(self) -> dict:
        """Call this frequently. Returns current state + whether a transition just happened."""
        self._just_switched = False

        if self.running and self.last_tick:
            elapsed = time.time() - self.last_tick
            self.last_tick = time.time()
            self.remaining -= elapsed

            if self.remaining <= 0:
                # Time's up — switch mode
                self._just_switched = True
                if self.is_work:
                    self.is_work = False
                    self.remaining = self.break_secs
                else:
                    self.is_work = True
                    self.remaining = self.work_secs
                    self.session = self.session + 1 if self.session < 4 else 1

        mins = int(max(0, self.remaining) // 60)
        secs = int(max(0, self.remaining) % 60)

        return {
            "mode": "FOCUS" if self.is_work else "BREAK",
            "remaining": f"{mins:02d}:{secs:02d}",
            "session": self.session,
            "running": self.running,
            "just_switched": self._just_switched,
        }


# ──────────────────────────────────────────────
# Focus Score Calculator
# ──────────────────────────────────────────────

def calculate_focus_score(temp_c: float, co2_ppm: int, posture_status: str, light: int) -> int:
    """Calculate focus score (0-100) based on environmental + posture data."""
    score = 85

    # CO2 penalties
    if co2_ppm > 900:
        score -= int((co2_ppm - 900) / 50) * 3
    if co2_ppm > 1200:
        score -= 10

    # Temperature penalties
    if temp_c > 27.0:
        score -= int((temp_c - 27.0) * 4)
    if temp_c < 19.0:
        score -= int((19.0 - temp_c) * 3)

    # Posture penalty
    if posture_status == "Warning":
        score -= 5
    elif posture_status == "Poor":
        score -= 15

    # Low light penalty
    if light < 300:
        score -= 8

    return max(10, min(100, score))


# ──────────────────────────────────────────────
# Settings Loader
# ──────────────────────────────────────────────

def load_settings() -> dict:
    """Load user settings from bridge_settings.json (written by backend API)."""
    defaults = {
        "focus_min": DEFAULT_FOCUS_MIN,
        "break_min": DEFAULT_BREAK_MIN,
        "posture_strictness": "medium",
        "co2_max": 1000,
        "target_temp": 23,
    }
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r") as f:
                saved = json.load(f)
                defaults.update(saved)
        except Exception:
            pass
    return defaults


# ──────────────────────────────────────────────
# Database Writer
# ──────────────────────────────────────────────

def save_session(db_path: str, data: dict):
    """Insert a study session + focus data row into deskbuddy.db."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    hour_label = datetime.now().strftime("%-I %p") if sys.platform != "win32" else datetime.now().strftime("%#I %p")

    # Study session
    cursor.execute("""
        INSERT INTO study_sessions
            (timestamp, temperature_c, humidity_pct, co2_ppm, aqi,
             posture_status, posture_score, focus_score, session_label)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ts,
        data["temperature_c"],
        data.get("humidity_pct", 0.0),    # placeholder until humidity sensor is plugged in
        data["co2_ppm"],
        data["aqi"],
        data["posture_status"],
        data["posture_score"],
        data["focus_score"],
        data["session_label"],
    ))

    # Focus data for charts
    cursor.execute("""
        INSERT INTO focus_data
            (timestamp, hour_label, focus_minutes, break_minutes, distractions)
        VALUES (?, ?, ?, ?, ?)
    """, (
        ts,
        hour_label,
        data.get("focus_minutes", 0),
        data.get("break_minutes", 0),
        data.get("distractions", 0),
    ))

    conn.commit()
    conn.close()


# ──────────────────────────────────────────────
# Arduino Feedback Commands
# ──────────────────────────────────────────────

def send_command(ser: serial.Serial, cmd: str):
    """Send a command string to the Arduino over serial."""
    ser.write((cmd + "\n").encode("utf-8"))


def send_lcd(ser: serial.Serial, line: int, text: str):
    """Update a line on the Arduino's LCD."""
    send_command(ser, f"LCD:{line}:{text[:16]}")


def send_buzz(ser: serial.Serial, freq: int, duration_ms: int):
    """Play a buzzer tone on the Arduino."""
    send_command(ser, f"BUZZ:{freq}:{duration_ms}")


def send_led(ser: serial.Serial, pin: int, state: int):
    """Turn an LED on/off on the Arduino."""
    send_command(ser, f"LED:{pin}:{state}")


def send_nobuzz(ser: serial.Serial):
    """Silence the Arduino buzzer."""
    send_command(ser, "NOBUZZ")


# ──────────────────────────────────────────────
# LED feedback based on posture
# ──────────────────────────────────────────────
# Assumes: pin 3 = green, pin 4 = yellow, pin 5 = red
LED_GREEN = 3
LED_YELLOW = 4
LED_RED = 5


def update_leds_for_posture(ser: serial.Serial, status: str):
    """Set LED indicators based on posture status."""
    if status == "Good":
        send_led(ser, LED_GREEN, 1)
        send_led(ser, LED_YELLOW, 0)
        send_led(ser, LED_RED, 0)
    elif status == "Warning":
        send_led(ser, LED_GREEN, 0)
        send_led(ser, LED_YELLOW, 1)
        send_led(ser, LED_RED, 0)
    elif status == "Poor":
        send_led(ser, LED_GREEN, 0)
        send_led(ser, LED_YELLOW, 0)
        send_led(ser, LED_RED, 1)
    else:
        # Away or uncalibrated — all off
        send_led(ser, LED_GREEN, 0)
        send_led(ser, LED_YELLOW, 0)
        send_led(ser, LED_RED, 0)


# ──────────────────────────────────────────────
# Session Label Generator
# ──────────────────────────────────────────────

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


def get_session_label(session_num: int) -> str:
    return SESSION_LABELS[session_num % len(SESSION_LABELS)]


# ══════════════════════════════════════════════
# MAIN BRIDGE LOOP
# ══════════════════════════════════════════════

def find_arduino_port() -> str:
    """Auto-detect Arduino COM port if possible."""
    ports = serial.tools.list_ports.comports()
    for p in ports:
        desc = (p.description or "").lower()
        if "arduino" in desc or "ch340" in desc or "usb serial" in desc:
            return p.device
    return DEFAULT_PORT


def main():
    parser = argparse.ArgumentParser(description="DeskBuddy Serial Bridge")
    parser.add_argument("--port", default=None, help=f"COM port (default: auto-detect or {DEFAULT_PORT})")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help=f"Baud rate (default: {DEFAULT_BAUD})")
    args = parser.parse_args()

    port = args.port or find_arduino_port()
    baud = args.baud

    # Resolve DB path
    db_path = os.path.abspath(DB_PATH)
    if not os.path.exists(db_path):
        print(f"[Bridge] ERROR: Database not found at {db_path}")
        print("         Run data/database.py first to create it.")
        sys.exit(1)

    print("=" * 55)
    print("  DeskBuddy Serial Bridge")
    print("=" * 55)
    print(f"  Port:     {port}")
    print(f"  Baud:     {baud}")
    print(f"  Database: {db_path}")
    print(f"  Settings: {os.path.abspath(SETTINGS_PATH)}")
    print("=" * 55)

    # Load user settings
    settings = load_settings()
    print(f"  Focus:    {settings['focus_min']} min")
    print(f"  Break:    {settings['break_min']} min")
    print("=" * 55)

    # Initialize components
    posture = PostureTracker()
    pomodoro = PomodoroTimer(settings["focus_min"], settings["break_min"])

    # Connect to Arduino
    try:
        ser = serial.Serial(port, baud, timeout=1)
        time.sleep(2)  # wait for Arduino to reset after serial connection
        print(f"\n[Bridge] Connected to {port}")
    except serial.SerialException as e:
        print(f"[Bridge] ERROR: Could not open {port}: {e}")
        print("         Check the port and make sure no other program is using it.")
        sys.exit(1)

    # State tracking
    session_count = 0
    last_save_time = time.time()
    last_posture_status = None
    last_pom_mode = None
    calibrated = False
    focus_seconds_accumulated = 0
    break_seconds_accumulated = 0
    distraction_count = 0
    last_tick_time = time.time()

    # Running averages for session saves
    temp_sum = 0.0
    co2_sum = 0
    aqi_sum = 0
    light_sum = 0
    reading_count = 0

    print("[Bridge] Waiting for Arduino data...\n")

    try:
        while True:
            # ─── Read serial line ───
            try:
                line = ser.readline().decode("utf-8", errors="replace").strip()
            except serial.SerialException:
                print("[Bridge] Serial connection lost! Attempting reconnect...")
                time.sleep(2)
                try:
                    ser.close()
                    ser = serial.Serial(port, baud, timeout=1)
                    time.sleep(2)
                    print("[Bridge] Reconnected!")
                except Exception:
                    print("[Bridge] Reconnect failed. Exiting.")
                    break
                continue

            if not line:
                continue

            # Parse JSON from Arduino
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                # Might be a status message like {"status":"ready"}
                if "ready" in line:
                    print("[Bridge] Arduino is ready!")
                    send_lcd(ser, 0, "DeskBuddy LIVE  ")
                    send_lcd(ser, 1, "Press btn to cal")
                continue

            # Skip non-sensor messages (like ack messages)
            if "d" not in data:
                continue

            # ─── Convert raw values ───
            distance = data["d"]
            light = raw_to_light(data["l"])
            co2_ppm = raw_to_co2(data["co2"])
            temp_c = raw_to_temperature(data["t"])
            aqi = raw_to_aqi(data["co2"])  # same sensor
            btn = data.get("btn", 0)

            # ─── Button press = calibrate ───
            if btn == 1 and not calibrated:
                if distance > 0:
                    posture.calibrate(distance)
                    calibrated = True
                    pomodoro.start()
                    send_buzz(ser, 1000, 200)
                    time.sleep(0.2)
                    send_buzz(ser, 1200, 200)
                    send_lcd(ser, 0, "Calibrated!     ")
                    send_lcd(ser, 1, f"Baseline: {distance}cm  ")
                    time.sleep(1)
                continue
            elif btn == 1 and calibrated:
                # Re-calibrate
                if distance > 0:
                    posture.calibrate(distance)
                    send_buzz(ser, 1000, 200)
                    send_lcd(ser, 0, "Re-calibrated!  ")
                    send_lcd(ser, 1, f"Baseline: {distance}cm  ")
                    time.sleep(1)
                continue

            # ─── Posture update ───
            posture_info = posture.update(distance)

            # ─── Pomodoro tick ───
            pom_state = pomodoro.tick()

            # Track focus/break time
            now = time.time()
            dt = now - last_tick_time
            last_tick_time = now
            if pomodoro.running:
                if pom_state["mode"] == "FOCUS":
                    focus_seconds_accumulated += dt
                else:
                    break_seconds_accumulated += dt

            # ─── Accumulate for session averages ───
            temp_sum += temp_c
            co2_sum += co2_ppm
            aqi_sum += aqi
            light_sum += light
            reading_count += 1

            # ─── Calculate focus score ───
            focus_score = calculate_focus_score(temp_c, co2_ppm, posture_info["status"], light)

            # ─── Posture feedback to Arduino ───
            if posture_info["status"] != last_posture_status:
                last_posture_status = posture_info["status"]
                update_leds_for_posture(ser, posture_info["status"])

                if posture_info["status"] == "Poor":
                    send_buzz(ser, 1000, 0)  # continuous buzz
                elif posture_info["status"] == "Warning":
                    send_buzz(ser, 600, 300)
                else:
                    send_nobuzz(ser)

            # ─── Pomodoro feedback to Arduino ───
            if pom_state["just_switched"]:
                if pom_state["mode"] == "BREAK":
                    send_buzz(ser, 1200, 500)
                    send_lcd(ser, 0, " TAKE A BREAK!  ")
                    send_lcd(ser, 1, f" Back in {settings['break_min']}min   ")
                else:
                    send_buzz(ser, 800, 500)
                    send_lcd(ser, 0, "  FOCUS TIME!   ")
                    send_lcd(ser, 1, f" Session {pom_state['session']}/4    ")

            # ─── Update LCD with current state ───
            if calibrated and not pom_state["just_switched"]:
                if posture_info.get("away"):
                    send_lcd(ser, 0, "User Away...    ")
                else:
                    status_str = posture_info["status"]
                    send_lcd(ser, 0, f"P:{status_str:<8}{pom_state['remaining']}")

                # Bottom line: environment summary
                send_lcd(ser, 1, f"{temp_c:.0f}C CO2:{co2_ppm:>4}  ")

            # ─── Posture: stop buzzer when corrected ───
            if posture_info["status"] == "Good" and last_posture_status != "Good":
                send_nobuzz(ser)

            # ─── Periodic session save to DB ───
            if now - last_save_time >= SESSION_SAVE_INTERVAL and reading_count > 0:
                avg_temp = round(temp_sum / reading_count, 1)
                avg_co2 = int(co2_sum / reading_count)
                avg_aqi = int(aqi_sum / reading_count)

                session_data = {
                    "temperature_c": avg_temp,
                    "humidity_pct": 0.0,  # TODO: plug in humidity sensor
                    "co2_ppm": avg_co2,
                    "aqi": avg_aqi,
                    "posture_status": posture_info["status"],
                    "posture_score": posture_info["score"],
                    "focus_score": focus_score,
                    "session_label": get_session_label(session_count),
                    "focus_minutes": int(focus_seconds_accumulated / 60),
                    "break_minutes": int(break_seconds_accumulated / 60),
                    "distractions": distraction_count,
                }

                try:
                    save_session(db_path, session_data)
                    session_count += 1
                    print(f"  [DB] Session {session_count} saved — "
                          f"Temp={avg_temp}°C  CO2={avg_co2}ppm  "
                          f"Posture={posture_info['status']}  Focus={focus_score}%")
                except Exception as e:
                    print(f"  [DB] Save error: {e}")

                # Reset accumulators
                last_save_time = now
                temp_sum = 0.0
                co2_sum = 0
                aqi_sum = 0
                light_sum = 0
                reading_count = 0
                focus_seconds_accumulated = 0
                break_seconds_accumulated = 0
                distraction_count = 0

            # ─── Reload settings periodically ───
            if int(now) % 30 == 0:  # every ~30 seconds
                new_settings = load_settings()
                if (new_settings["focus_min"] != settings["focus_min"] or
                        new_settings["break_min"] != settings["break_min"]):
                    settings = new_settings
                    pomodoro.update_intervals(settings["focus_min"], settings["break_min"])
                    print(f"  [Settings] Updated: Focus={settings['focus_min']}min  Break={settings['break_min']}min")

            # ─── Console output (compact) ───
            if reading_count % 4 == 1:  # print every ~2 seconds
                status_char = {"Good": "✓", "Warning": "⚠", "Poor": "✗", "Away": "—"}.get(
                    posture_info["status"], "?"
                )
                print(
                    f"  {temp_c:5.1f}°C  CO2:{co2_ppm:>5}  "
                    f"Light:{light:>4}  Dist:{distance:>4}cm  "
                    f"Posture:{status_char}  {pom_state['mode']} {pom_state['remaining']}  "
                    f"Focus:{focus_score}%"
                )

    except KeyboardInterrupt:
        print("\n[Bridge] Shutting down...")
        send_lcd(ser, 0, "Bridge stopped  ")
        send_lcd(ser, 1, "                ")
        send_nobuzz(ser)
        # Turn off all LEDs
        send_led(ser, LED_GREEN, 0)
        send_led(ser, LED_YELLOW, 0)
        send_led(ser, LED_RED, 0)
        ser.close()
        print("[Bridge] Goodbye!")


if __name__ == "__main__":
    main()
