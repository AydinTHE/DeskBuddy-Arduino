// ═══════════════════════════════════════════════════════════════
// DeskBuddy — Arduino Raw Sensor Transmitter
// ═══════════════════════════════════════════════════════════════
// Reads all sensors and transmits raw data as JSON over Serial
// (USB) to the PC bridge. All calculation, posture detection,
// Pomodoro logic, and alerting is handled by the PC backend.
//
// Hardware: LCD 16x2 (I2C), Button, Ultrasonic (HC-SR04),
//           Photoresistor, CO2 sensor, Temp sensor, LEDs
//
// Serial output (JSON line every 500ms):
//   {"d":42,"l":512,"co2":730,"t":680,"btn":0}
//
//   d   = distance in cm (ultrasonic, -1 if no echo)
//   l   = light level (analog 0-1023)
//   co2 = CO2 raw analog (0-1023)
//   t   = temperature raw analog (0-1023)
//   btn = button state (1 = pressed, 0 = not pressed)
//
// Serial input commands from PC (for feedback):
//   BUZZ:freq:duration   — play buzzer tone
//   LCD:line:message     — write to LCD line (0 or 1)
//   LED:pin:state        — set an LED (pin number, 1=on 0=off)
//   NOBUZZ               — silence buzzer
//   CALIBRATE            — respond with ACK
// ═══════════════════════════════════════════════════════════════

#include <Adafruit_LiquidCrystal.h>

// ──────────────────────────────────────────────
// Pin Assignments
// ──────────────────────────────────────────────
const byte trigPin    = 9;
const byte echoPin    = 10;
const byte buzzerPin  = 8;
const byte buttonPin  = 2;
const byte lightPin   = A0;
const byte co2Pin     = A1;
const byte tempPin    = A2;

// LED pins — add your LED pin numbers here as you wire them
const byte ledPins[]  = {3, 4, 5};       // example: green, yellow, red
const byte ledCount   = sizeof(ledPins) / sizeof(ledPins[0]);

// ──────────────────────────────────────────────
// Hardware
// ──────────────────────────────────────────────
Adafruit_LiquidCrystal lcd(0);

// ──────────────────────────────────────────────
// Timing
// ──────────────────────────────────────────────
const unsigned long SAMPLE_INTERVAL_MS = 500;
unsigned long lastSampleTime = 0;

// ──────────────────────────────────────────────
// Serial input buffer
// ──────────────────────────────────────────────
String serialBuffer = "";

// ═══════════════════════════════════════════════
// SETUP
// ═══════════════════════════════════════════════
void setup() {
  Serial.begin(115200);

  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  pinMode(buzzerPin, OUTPUT);
  pinMode(buttonPin, INPUT_PULLUP);

  // Initialize LED pins
  for (byte i = 0; i < ledCount; i++) {
    pinMode(ledPins[i], OUTPUT);
    digitalWrite(ledPins[i], LOW);
  }

  lcd.begin(16, 2);

  // Boot message
  lcd.setCursor(0, 0);
  lcd.print("DeskBuddy v2    ");
  lcd.setCursor(0, 1);
  lcd.print("Waiting for PC..");

  // Signal ready to PC
  Serial.println("{\"status\":\"ready\"}");
}

// ═══════════════════════════════════════════════
// SENSOR READING
// ═══════════════════════════════════════════════

int measureDistance() {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  long duration = pulseIn(echoPin, HIGH, 30000);
  if (duration == 0) return -1;  // no echo / out of range

  return (duration * 34) / 2000;  // cm
}

// ═══════════════════════════════════════════════
// SERIAL COMMAND HANDLER
// ═══════════════════════════════════════════════
// Receives commands from the PC bridge to control
// the Arduino's output devices (buzzer, LEDs, LCD).

void handleCommand(String cmd) {
  cmd.trim();

  if (cmd.startsWith("BUZZ:")) {
    // Format: BUZZ:freq:duration
    int c1 = cmd.indexOf(':', 5);
    if (c1 > 0) {
      int freq = cmd.substring(5, c1).toInt();
      int dur  = cmd.substring(c1 + 1).toInt();
      tone(buzzerPin, freq, dur);
    }
  }
  else if (cmd == "NOBUZZ") {
    noTone(buzzerPin);
  }
  else if (cmd.startsWith("LED:")) {
    // Format: LED:pin:state  (e.g. LED:3:1 turns pin 3 on)
    int c1 = cmd.indexOf(':', 4);
    if (c1 > 0) {
      int pin   = cmd.substring(4, c1).toInt();
      int state = cmd.substring(c1 + 1).toInt();
      digitalWrite(pin, state ? HIGH : LOW);
    }
  }
  else if (cmd.startsWith("LCD:")) {
    // Format: LCD:line:message
    int c1 = cmd.indexOf(':', 4);
    if (c1 > 0) {
      int line = cmd.substring(4, c1).toInt();
      String msg = cmd.substring(c1 + 1);
      while (msg.length() < 16) msg += ' ';
      lcd.setCursor(0, line);
      lcd.print(msg.substring(0, 16));
    }
  }
  else if (cmd == "CALIBRATE") {
    Serial.println("{\"ack\":\"calibrate\"}");
  }
}

// ═══════════════════════════════════════════════
// MAIN LOOP
// ═══════════════════════════════════════════════

void loop() {
  // ─── Check for incoming commands from PC ───
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      handleCommand(serialBuffer);
      serialBuffer = "";
    } else {
      serialBuffer += c;
    }
  }

  // ─── Send sensor data at fixed interval ───
  unsigned long now = millis();
  if (now - lastSampleTime >= SAMPLE_INTERVAL_MS) {
    lastSampleTime = now;

    int distance = measureDistance();
    int lightVal = analogRead(lightPin);
    int co2Raw   = analogRead(co2Pin);
    int tempRaw  = analogRead(tempPin);
    int btnState = (digitalRead(buttonPin) == LOW) ? 1 : 0;

    // Send compact JSON line
    Serial.print("{\"d\":");
    Serial.print(distance);
    Serial.print(",\"l\":");
    Serial.print(lightVal);
    Serial.print(",\"co2\":");
    Serial.print(co2Raw);
    Serial.print(",\"t\":");
    Serial.print(tempRaw);
    Serial.print(",\"btn\":");
    Serial.print(btnState);
    Serial.println("}");
  }
}
