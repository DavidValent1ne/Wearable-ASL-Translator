// ═══════════════════════════════════════════════════
//  ESP32 ASL Glove — Full Sensor Test + UART to Pi
//  Tests: 5x flex, 4x hall effect, 2x tilt
//  Sends data over Serial2 (GPIO16/17) to Pi Zero
//  Also prints to Serial Monitor at 115200 baud
//  Sacramento State Senior Design
// ═══════════════════════════════════════════════════

// ── FLEX SENSOR PINS (ADC1 — always safe) ──
#define FLEX_THUMB   36
#define FLEX_INDEX   39
#define FLEX_MIDDLE  34
#define FLEX_RING    35
#define FLEX_PINKY   32

// ── HALL EFFECT SENSOR PINS ──
#define HALL_INDEX   33   // ADC1 — safe with BLE/WiFi
#define HALL_MIDDLE  25   // ADC2 — radio must be off
#define HALL_RING    26   // ADC2 — radio must be off
#define HALL_PINKY   27   // ADC2 — radio must be off

// ── TILT SENSOR PINS ──
#define TILT_WRIST   4
#define TILT_HAND    14

// ── SAMPLING ──
#define SAMPLE_DELAY_MS 1000  // 1 reading per second for testing

void setup() {
  Serial.begin(115200);   // USB serial monitor
  Serial2.begin(115200, SERIAL_8N1, 16, 17);  // UART to Pi — RX=16, TX=17
  delay(1000);

  // tilt sensors — input with internal pull-up
  pinMode(TILT_WRIST, INPUT_PULLUP);
  pinMode(TILT_HAND,  INPUT_PULLUP);

  // ADC resolution — 12 bit (0-4095)
  analogReadResolution(12);

  Serial.println("═══════════════════════════════════════");
  Serial.println("  ESP32 ASL Glove — Sensor Test");
  Serial.println("═══════════════════════════════════════");
  Serial.println("Flex sensors:  0-4095 (higher = more bent)");
  Serial.println("Hall sensors:  ~2048 at rest, swings with magnet");
  Serial.println("Tilt sensors:  0 = tilted, 1 = upright");
  Serial.println("═══════════════════════════════════════\n");
}

// ── debounce helper for tilt ──
bool readTilt(int pin) {
  if (digitalRead(pin) == LOW) {
    delay(20);
    return digitalRead(pin) == LOW;
  }
  return false;
}

void loop() {
  // ── read flex sensors ──
  int flex_thumb  = analogRead(FLEX_THUMB);
  int flex_index  = analogRead(FLEX_INDEX);
  int flex_middle = analogRead(FLEX_MIDDLE);
  int flex_ring   = analogRead(FLEX_RING);
  int flex_pinky  = analogRead(FLEX_PINKY);

  // ── read hall effect sensors ──
  int hall_index  = analogRead(HALL_INDEX);
  int hall_middle = analogRead(HALL_MIDDLE);
  int hall_ring   = analogRead(HALL_RING);
  int hall_pinky  = analogRead(HALL_PINKY);

  // ── read tilt sensors ──
  bool tilt_wrist = readTilt(TILT_WRIST);
  bool tilt_hand  = readTilt(TILT_HAND);

  // ── print results to Serial Monitor AND Serial2 (Pi) ──
  String out = "";
  out += "--- FLEX SENSORS ---\n";
  out += "  Thumb:  " + String(flex_thumb)  + "  |  Index:  " + String(flex_index)  + "  |  Middle: " + String(flex_middle) + "\n";
  out += "  Ring:   " + String(flex_ring)   + "  |  Pinky:  " + String(flex_pinky)  + "\n";
  out += "--- HALL EFFECT SENSORS ---\n";
  out += "  Index:  " + String(hall_index)  + "  |  Middle: " + String(hall_middle) + "\n";
  out += "  Ring:   " + String(hall_ring)   + "  |  Pinky:  " + String(hall_pinky)  + "\n";
  out += "--- TILT SENSORS ---\n";
  out += "  Wrist: " + String(tilt_wrist ? "TILTED" : "upright") + "  |  Hand: " + String(tilt_hand ? "TILTED" : "upright") + "\n";

  Serial.print(out);    // USB serial monitor
  Serial2.print(out);   // UART to Pi

  delay(SAMPLE_DELAY_MS);
}
