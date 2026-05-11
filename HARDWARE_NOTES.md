# DeskBuddy — Hardware Sensor Integration Notes

## Current Status

| Sensor | Connected | Pin | Status |
|--------|-----------|-----|--------|
| Ultrasonic (HC-SR04) | ✅ | Trig=9, Echo=10 | Working — posture detection |
| Photoresistor | ✅ | A0 | Working — light level |
| MQ135 (CO2/AQI) | ✅ | A1 | Working — CO2 ppm + AQI derived |
| TMP36 (Temperature) | ✅ | A2 | Working — °C conversion |
| LCD 16x2 (I2C) | ✅ | I2C | Working — feedback display |
| Button | ✅ | D2 | Working — calibration trigger |
| Buzzer | ✅ | D8 | Working — alerts |
| LEDs (Green/Yellow/Red) | 🔜 | D3/D4/D5 | To be wired |
| Humidity Sensor | 🔜 | TBD | To be plugged in |

---

## Sensors To Add Later

### 1. Humidity Sensor (DHT11 or DHT22)

**Current workaround:** `humidity_pct` is set to `0.0` in the bridge and stored in DB as a placeholder.

**When you plug it in:**

1. **Arduino side** — Add to `deskbuddy_arduino1.ino`:
   ```cpp
   #include <DHT.h>
   
   const byte dhtPin = 6;      // pick an unused digital pin
   DHT dht(dhtPin, DHT11);     // or DHT22
   
   // In setup():
   dht.begin();
   
   // In the serial output section, add humidity:
   float humidity = dht.readHumidity();
   Serial.print(",\"h\":");
   Serial.print(isnan(humidity) ? 0 : (int)humidity);
   ```

2. **Bridge side** — In `serial_bridge.py`, update the sensor read section:
   ```python
   humidity = data.get("h", 0)
   ```
   And update the session save:
   ```python
   "humidity_pct": humidity,  # was 0.0
   ```

### 2. LEDs (Green / Yellow / Red)

**When you wire them:**

1. Connect LEDs with appropriate resistors (220Ω) to pins 3, 4, 5
2. The bridge already sends `LED:3:1`, `LED:4:1`, `LED:5:1` commands
3. If you use different pins, update the constants in `serial_bridge.py`:
   ```python
   LED_GREEN = 3   # change to your pin
   LED_YELLOW = 4  # change to your pin
   LED_RED = 5     # change to your pin
   ```
4. Also update `ledPins[]` in the Arduino sketch to match

---

## MQ135 → CO2 + AQI Note

The **MQ135** sensor is used for both CO2 and AQI readings from the same analog pin (A1):

- **CO2 ppm**: Mapped linearly from raw 0–1023 to 400–2000 ppm
- **AQI**: Mapped from raw 0–1023 to 0–150 AQI scale

> **Important:** The MQ135 is NOT a precision sensor. The CO2/AQI values are rough estimates. For accurate readings, consider calibrating the conversion formulas in `serial_bridge.py` (`raw_to_co2()` and `raw_to_aqi()`) against a known reference.

> **Warm-up:** MQ135 needs ~24 hours of initial burn-in and ~2–5 minutes warm-up each time. Readings in the first few minutes may be unreliable.

---

## NTC Thermistor (Temperature)

The bridge uses a **10kΩ NTC thermistor** with the Beta parameter equation:

**Wiring:** 5V to Thermistor, then to A2, then to a 10kΩ Resistor to GND.

```
5V ──[NTC thermistor]──┬──[10kΩ resistor]── GND
                       │
                      A2 (analog read)
```

**Conversion formula** (in `serial_bridge.py` → `raw_to_temperature()`):
```
resistance = 10000 × (1023 / raw - 1)
steinhart  = ln(resistance / 10000) / 3950
steinhart += 1 / (25 + 273.15)
temp_C     = (1 / steinhart) - 273.15
```

**Calibration:** If readings seem off, adjust these values in `raw_to_temperature()`:
- `SERIES_RESISTOR` — your series resistor value (default 10kΩ)
- `THERMISTOR_NOMINAL` — thermistor resistance at 25°C (default 10kΩ)
- `B_COEFFICIENT` — Beta value from your thermistor's datasheet (default 3950)
