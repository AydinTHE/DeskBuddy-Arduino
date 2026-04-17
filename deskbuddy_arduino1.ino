#include <Adafruit_LiquidCrystal.h>
#include <Adafruit_NeoPixel.h>

Adafruit_LiquidCrystal lcd(0);

// OPTIMIZATION: Using 'byte' saves 50% memory per variable
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

int baselineDistance = 0; 
int currentDistance = 0;

const int darkThreshold = 300; 
const int co2Threshold = 1200; 
const byte hotThreshold = 28; 

unsigned long previousMillis = 0;
byte timeLeft = 25; 
bool isBreakTime = false;
unsigned long postureTimerStart = 0;
bool postureTimerActive = false;
const unsigned long gracePeriod = 7000; 

void setup() {
  pinMode(trigPin, OUTPUT);
  pinMode(echoPin, INPUT);
  pinMode(buzzerPin, OUTPUT);
  pinMode(buttonPin, INPUT_PULLUP); 
  
  // Serial.begin removed to save huge amounts of RAM!
  
  lcd.begin(16, 2);
  strip.begin();
  strip.show(); 
  strip.setBrightness(50); 
  
  lcd.setCursor(0, 0); 
  lcd.print("Sys Ready!      "); 
  lcd.setCursor(0, 1); 
  lcd.print("Press Button... ");
}

int measureDistance() {
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  
  long duration = pulseIn(echoPin, HIGH, 30000); 
  if (duration == 0) return 0;
  // OPTIMIZATION: Integer math instead of decimals (duration * 0.034 / 2)
  return (duration * 34) / 2000; 
}

void setGlow(byte r, byte g, byte b) {
  for(byte i = 0; i < strip.numPixels(); i++) {
    strip.setPixelColor(i, strip.Color(r, g, b));
  }
  strip.show();
}

void loop() {
  unsigned long currentMillis = millis();
  if (currentMillis - previousMillis >= 1000) { 
    previousMillis = currentMillis;
    if (baselineDistance > 0) { 
      if (timeLeft > 0) {
        timeLeft--; 
      } else {
        isBreakTime = !isBreakTime; 
        if (isBreakTime) {
          timeLeft = 5; 
          tone(buzzerPin, 1200, 500); 
        } else {
          timeLeft = 25; 
          tone(buzzerPin, 800, 500); 
        }
      }
    }
  }

  if (digitalRead(buttonPin) == LOW) {
    noTone(buzzerPin); 
    setGlow(100, 100, 100); 
    
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Calibrating...");
    
    tone(buzzerPin, 500, 200); 
    delay(5000); 
    baselineDistance = measureDistance();
    
    timeLeft = 25; 
    isBreakTime = false;
    postureTimerActive = false; 
    
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Target Locked!");
    tone(buzzerPin, 1000, 100);
    delay(200);
    tone(buzzerPin, 1000, 100);
    delay(1000); 
    lcd.clear();
  }

  if (baselineDistance > 0) {
    if (isBreakTime) {
      setGlow(0, 0, 255); 
      lcd.setCursor(0, 0);
      lcd.print(" TAKE A BREAK!  ");
      lcd.setCursor(0, 1);
      lcd.print(" Back in: ");
      lcd.print(timeLeft);
      lcd.print("s   ");
      delay(100);
      return; 
    }

    currentDistance = measureDistance();
    bool alarmTriggered = false; 
    
    lcd.setCursor(0, 0); 
    
    if (currentDistance == 0 || currentDistance > 150) {
      lcd.print("User Away...    ");
      setGlow(0, 0, 0); 
      postureTimerActive = false; 
    }
    else if (currentDistance < (baselineDistance - 10) || currentDistance > (baselineDistance + 15)) {
      if (!postureTimerActive) {
        postureTimerActive = true;
        postureTimerStart = millis();
      }

      if (millis() - postureTimerStart >= gracePeriod) {
        lcd.print("Posture: BAD X( "); 
        setGlow(255, 0, 0); 
        tone(buzzerPin, 1000); 
        alarmTriggered = true;
      } else {
        lcd.print("Careful...      ");
        setGlow(255, 100, 0); 
      }
    } 
    else {
      postureTimerActive = false; 
      lcd.print("Posture: OK  :) "); 
      setGlow(0, 150, 0); 
    }
    
    lcd.setCursor(0, 1);
    
    // OPTIMIZATION: Read sensors directly without storing them in variables
    if (analogRead(lightPin) < darkThreshold) {
      lcd.print("Warning: DARK!  ");
      if (!alarmTriggered) { tone(buzzerPin, 300); alarmTriggered = true; } 
    } 
    else if (map(analogRead(co2Pin), 0, 1023, 400, 2000) > co2Threshold) {
      lcd.print("CO2 HIGH! VENT! "); 
      setGlow(255, 0, 0); 
      if (!alarmTriggered) { tone(buzzerPin, 600); alarmTriggered = true; } 
    } 
    // OPTIMIZATION: Integer math mapping for temp, no decimals!
    else if (map(analogRead(tempPin), 0, 1023, -50, 450) > hotThreshold) {
      lcd.print("Temp: HOT!      ");
      setGlow(255, 100, 0); 
      if (!alarmTriggered) { tone(buzzerPin, 400); alarmTriggered = true; } 
    }
    else {
      lcd.print("C:");
      lcd.print(map(analogRead(co2Pin), 0, 1023, 400, 2000));
      lcd.print(" ");
      lcd.print(map(analogRead(tempPin), 0, 1023, -50, 450));
      lcd.print("C T:");
      lcd.print(timeLeft);
      lcd.print("  "); 
    }
    
    if (!alarmTriggered) {
      noTone(buzzerPin);     
    }
    
    delay(100); 
  }
}