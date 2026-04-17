# DeskBuddy: Smart Study Gadget      
    
An all-in-one, Arduino-powered desktop companion designed to keep you focused, healthy, and productive. DeskBuddy monitors your posture, enforces healthy study breaks using the Pomodoro technique, and keeps an eye on your room's environmental conditions.

## Features
* **Posture Monitoring:** Uses an HC-SR04 ultrasonic sensor to lock onto your baseline sitting position. If you slouch or lean too close to your screen for more than 7 seconds, a buzzer and visual alarm will remind you to sit up straight.
* **Pomodoro Timer:** Automatically tracks your study sessions (25 minutes of work, 5 minutes of break) with distinct audio cues and LCD updates.
* **Environmental Warnings:** * **Light:** Warns you if the room is too dark to safely read (preventing eye strain).
* **Temperature:** Alerts you if the room gets uncomfortably hot.
* **CO2/Air Quality:** Reminds you to open a window and ventilate the room if the air gets stuffy.
* **Visual & Audio UI:** Uses an I2C 16x2 LCD screen for real-time data, an 8-LED NeoPixel strip for ambient status lighting, and a piezo buzzer for alerts.

## Hardware Required
* 1x Arduino Uno R3 (or Mega 2560)
* 1x 16x2 LCD Display 
* 1x HC-SR04 Ultrasonic Sensor
* 1x 8-LED WS2812 NeoPixel Strip
* 1x LDR (Photoresistor)
* 1x TMP36 Temperature Sensor
* 1x Analog CO2/Gas Sensor
* 1x Piezo Buzzer
* 1x Push Button

## 🔌 Pin Mapping
| Component | Arduino Pin |
| :--- | :--- |
| Push Button | `D2` |
| NeoPixel Strip | `D3` |
| Piezo Buzzer | `D8` |
| Ultrasonic TRIG | `D9` |
| Ultrasonic ECHO | `D10` |
| Light Sensor (LDR)| `A0` |
| CO2 Sensor | `A1` |
| Temp Sensor | `A2` |

##  How to Use
1. **Power On:** The system will boot and display "Sys Ready! Press Button..."
2. **Calibrate:** Sit in your perfect, healthy posture and press the button. The NeoPixels will turn white, and the ultrasonic sensor will take 5 seconds to lock onto your distance.
3. **Work:** The Pomodoro timer will start. The LCD will display your real-time room data, and the NeoPixels will glow green as long as your posture is good.
4. **Break:** When 25 minutes are up, the system will glow blue and tell you to take a 5-minute break
