#include <Adafruit_LiquidCrystal.h>
#include <Adafruit_NeoPixel.h>

Adafruit_LiquidCrystal lcd(0); // I2C address 0 for Adafruit backpack

// ══════════════════════════════════════════════
// PIN DEFINITIONS
// ══════════════════════════════════════════════

// ══════════════════════════════════════════════
// KODDA LED STRIPS VAR ONU LED LE EVEZLEMEK LAZIMDIR
// ══════════════════════════════════════════════
const byte trigPin = 9;
const byte echoPin = 10;
const byte buzzerPin = 8;
const byte buttonPin = 2; 
const byte lightPin = A0; 
const byte co2Pin = A1; 
const byte tempPin = A2; 
const byte ledPin = 3; 

const byte ledCount = 8; 
Adafruit_NeoPixel strip(ledCount, ledPin, NEO_GRB + NEO_KHZ800);

// ══════════════════════════════════════════════
// GLOBAL STATE
// ══════════════════════════════════════════════
int baselineDistance = 50; 
unsigned long previousMillis = 0;
const long interval = 1000; // Send data every 1 second

// Custom LCD characters
byte smiley[8] = {
  0b00000, 0b01010, 0b01010, 0b00000, 0b10001, 0b01110, 0b00000, 0b00000
};
byte frown[8] = {
  0b00000, 0b01010, 0b01010, 0b00000, 0b00000, 0b01110, 0b10001, 0b00000
};

String currentStatus = "Good!";
bool isGoodPosture = true;

// ══════════════════════════════════════════════
// SETUP
// ══════════════════════════════════════════════
void setup() {
  Serial.begin(9600);
  
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  pinMode(buzzerPin, OUTPUT);
  pinMode(buttonPin, INPUT_PULLUP); 

  // Initialize LCD
  lcd.begin(16, 2);
  lcd.createChar(0, smiley);
  lcd.createChar(1, frown);
  
  // Initialize LEDs
  strip.begin();
  strip.setBrightness(50); 
  setGlow(0, 50, 0); // Start green
  
  // Boot screen
  lcd.setCursor(0, 0); 
  lcd.print("DeskBuddy V2.0  "); 
  lcd.setCursor(0, 1); 
  lcd.print("Ready to connect");
  delay(1500);
  lcd.clear();
}

// ══════════════════════════════════════════════
// SENSOR FUNCTIONS
// ══════════════════════════════════════════════
int measureDistance() {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  
  long duration = pulseIn(echoPin, HIGH, 30000); 
  if (duration == 0) return 0;
  return (duration * 34) / 2000; 
}

float measureTemperature() {
  int rawVal = analogRead(tempPin);
  if (rawVal == 0) return 22.0; // Fail-safe
  float R1 = 10000.0;
  float c1 = 1.009249522e-03, c2 = 2.378405444e-04, c3 = 2.019202697e-07;
  
  float R2 = R1 * (1023.0 / (float)rawVal - 1.0);
  float logR2 = log(R2);
  float T = (1.0 / (c1 + c2*logR2 + c3*logR2*logR2*logR2));
  return T - 273.15; // Celcius
}

void setGlow(byte r, byte g, byte b) {
  for(byte i = 0; i < strip.numPixels(); i++) {
    strip.setPixelColor(i, strip.Color(r, g, b));
  }
  strip.show();
}

// ══════════════════════════════════════════════
// COMMAND PARSER
// ══════════════════════════════════════════════
void processIncomingCommand(String cmd) {
  cmd.trim();
  if (cmd == "CMD:WORK") {
    setGlow(0, 50, 0); // Green
    currentStatus = "Focus Mode";
    isGoodPosture = true;
  } else if (cmd == "CMD:BREAK") {
    setGlow(0, 0, 50); // Blue
    currentStatus = "Break Time";
    isGoodPosture = true;
    tone(buzzerPin, 1000, 300);
  } else if (cmd == "CMD:BAD_POSTURE") {
    setGlow(50, 0, 0); // Red
    currentStatus = "Slouching!";
    isGoodPosture = false;
    tone(buzzerPin, 800, 200);
  } else if (cmd == "CMD:OK_POSTURE") {
    setGlow(0, 50, 0); // Back to green
    currentStatus = "Good!";
    isGoodPosture = true;
  }
}

// ══════════════════════════════════════════════
// LCD RENDER
// ══════════════════════════════════════════════
void updateLCD(float temp, int co2) {
  // Row 1: T:24.5C  C:450p
  lcd.setCursor(0, 0);
  lcd.print("T:");
  lcd.print(temp, 1);
  lcd.print("C  C:");
  lcd.print(co2);
  lcd.print("p     "); // padding to clear line
  
  // Row 2: [Emoji] Status
  lcd.setCursor(0, 1);
  if (isGoodPosture) {
    lcd.write(byte(0)); // Smiley
  } else {
    lcd.write(byte(1)); // Frown
  }
  lcd.print(" ");
  lcd.print(currentStatus);
  lcd.print("            "); // Padding
}

// ══════════════════════════════════════════════
// MAIN LOOP
// ══════════════════════════════════════════════
void loop() {
  // 1. Read Button for Calibration
  if (digitalRead(buttonPin) == LOW) {
    int dist = measureDistance();
    if (dist > 0 && dist < 150) {
      baselineDistance = dist;
      tone(buzzerPin, 1500, 100);
      lcd.clear();
      lcd.setCursor(0,0);
      lcd.print("Calibration OK!");
      lcd.setCursor(0,1);
      lcd.print("Dist: "); lcd.print(dist); lcd.print("cm");
      delay(2000);
      lcd.clear();
    }
  }

  // 2. Read Serial Commands from PC
  if (Serial.available() > 0) {
    String incoming = Serial.readStringUntil('\n');
    processIncomingCommand(incoming);
  }

  // 3. Periodic Sensor Read & Transmit (Every 1s)
  unsigned long currentMillis = millis();
  if (currentMillis - previousMillis >= interval) {
    previousMillis = currentMillis;

    int dist = measureDistance();
    float temp = measureTemperature();
    int co2 = analogRead(co2Pin);
    int light = analogRead(lightPin);

    // Send JSON format to Serial port for Python to read
    Serial.print("{\"temp\":"); Serial.print(temp, 2);
    Serial.print(",\"co2\":"); Serial.print(co2);
    Serial.print(",\"light\":"); Serial.print(light);
    Serial.print(",\"dist\":"); Serial.print(dist);
    Serial.print(",\"base\":"); Serial.print(baselineDistance);
    Serial.println("}");

    updateLCD(temp, co2);
  }
}
