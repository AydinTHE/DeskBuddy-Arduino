// ═══════════════════════════════════════════════════════════════
// DeskBuddy — Arduino Raw Sensor Transmitter (Minimalist)
// ═══════════════════════════════════════════════════════════════
// Reads sensors and transmits raw data as JSON over Serial.
// Hardware: LCD 16x2 (I2C), Ultrasonic (HC-SR04), 
//           Photoresistor, CO2 sensor, Temp sensor.
// ═══════════════════════════════════════════════════════════════
#include <Adafruit_LiquidCrystal.h>

const byte trigPin    = 9;
const byte echoPin    = 10;
const byte lightPin   = A0;
const byte co2Pin     = A1;
const byte tempPin    = A2;

Adafruit_LiquidCrystal lcd(0);

const unsigned long SAMPLE_INTERVAL_MS = 500;
unsigned long lastSampleTime = 0;
String serialBuffer = "";

void setup() {
  // 115200 is fast. Ensure Serial Monitor matches this EXACTLY.
  Serial.begin(9600); 
  
  // Give the Serial hardware a moment to stabilize
  delay(500); 

  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);

  lcd.begin(16, 2);
  lcd.setCursor(0, 0);
  lcd.print("DeskBuddy v2.1");
  
  // DEBUG HEARTBEAT: If you see this clearly, your baud rate is correct.
  Serial.println("\n--- SYSTEM ONLINE ---");
  Serial.println("{\"status\":\"ready\"}");
}

int measureDistance() {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);

  // Added a 20ms timeout to prevent long hangs if sensor is unplugged
  long duration = pulseIn(echoPin, HIGH, 20000); 
  if (duration == 0) return -1; 

  return (duration * 34) / 2000; 
}

void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.startsWith("LCD:")) {
    int c1 = cmd.indexOf(':', 4);
    if (c1 > 0) {
      int line = cmd.substring(4, c1).toInt();
      String msg = cmd.substring(c1 + 1);
      while (msg.length() < 16) msg += ' ';
      lcd.setCursor(0, line);
      lcd.print(msg.substring(0, 16));
    }
  }
}

void loop() {
  // Listen for PC commands
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      handleCommand(serialBuffer);
      serialBuffer = "";
    } else if (serialBuffer.length() < 32) { // BUG FIX: Prevent memory overflow
      serialBuffer += c;
    }
  }

  unsigned long now = millis();
  if (now - lastSampleTime >= SAMPLE_INTERVAL_MS) {
    lastSampleTime = now;

    int distance = measureDistance();
    int lightVal = analogRead(lightPin);
    int co2Raw   = analogRead(co2Pin);
    int tempRaw  = analogRead(tempPin);

    // Clean JSON output
    Serial.print("{\"d\":");
    Serial.print(distance);
    Serial.print(",\"l\":");
    Serial.print(lightVal);
    Serial.print(",\"co2\":");
    Serial.print(co2Raw);
    Serial.print(",\"t\":");
    Serial.print(tempRaw);
    Serial.println("}");
  }
}