# DeskBuddy Operation Guide

Follow these steps to start and stop the DeskBuddy ecosystem.

## 🚀 How to START the System

To get everything running, you need to start three components in this order:

### 1. Arduino Hardware
- Connect your Arduino to your PC via USB.
- Ensure the code in `deskbuddy_arduino1.ino` is uploaded.
- **Note**: Close the Arduino Serial Monitor before proceeding to Step 2, or the bridge will fail to connect.

### 2. Serial Bridge (The Brain)
Open a terminal in the project root and run:
```bash
python bridge/serial_bridge.py
```
- This connects to your Arduino, starts the Pomodoro timer, and handles posture detection.
- **New Feature**: It will automatically restore your last baseline calibration from the database!

### 3. Backend API
Open a second terminal and run:
```bash
python -m uvicorn backend.backend:app --host 127.0.0.1 --port 8000
```
- This serves the data to the dashboard and allows you to control settings from the web.

### 4. Frontend Dashboard
- Open `frontend/index.html` in your browser.
- **Tip**: Use a "Live Server" extension for the best experience.

---

## 🛑 How to STOP the System

### 1. Close the Dashboard
- Simply close the browser tab.

### 2. Stop the Terminals
- Go to each terminal (Bridge and Backend) and press **`Ctrl + C`**.
- This safely closes the COM port and shuts down the server.

### 3. Emergency Stop (Kill All)
If a process gets stuck or the COM port is "Access Denied," run this in PowerShell:
```powershell
taskkill /F /IM python.exe
```

---

## 🛠️ Calibration & Tips
- **Instant Calibration**: Click "Set New Baseline" in the Posture Monitor tab. The LCD and Dashboard will update instantly.
- **Persistent Timer**: You can refresh the browser anytime; the timer will pick up exactly where it left off because it is synced with the Bridge.
- **LCD UI**:
    - **Top Row**: Shows blinking eyes and the live focus timer.
    - **Bottom Row**: Shows your custom scrolling motivational message.
