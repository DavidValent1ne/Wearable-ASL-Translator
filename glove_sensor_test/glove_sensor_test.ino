// ═══════════════════════════════════════════════════
//  ESP32 ASL Glove — Full Sensor Test
//  Flex + Hall Effect + IMU + Tilt + FSR
//  Sends data over Serial2 (GPIO16/17) to Pi Zero
//  Also prints to Serial Monitor at 115200 baud
//  Library: 7Semi_BMI270
//  Sacramento State Senior Design
// ═══════════════════════════════════════════════════

#include <Wire.h>
#include <7Semi_BMI270.h>

BMI270_7Semi imu;

// ── FLEX SENSOR PINS (ADC1) ──
#define FLEX_THUMB   36
#define FLEX_INDEX   39
#define FLEX_MIDDLE  34
#define FLEX_RING    35
#define FLEX_PINKY   32

// ── HALL EFFECT SENSOR PINS ──
#define HALL_INDEX   33   // ADC1 — safe with BLE/WiFi
#define HALL_MIDDLE  25   // ADC2
#define HALL_RING    26   // ADC2
#define HALL_PINKY   27   // ADC2

// ── FSR PIN ──
#define FSR_UV       13   // ADC2 — index/middle touch for U vs V

// ── TILT SENSOR PINS ──
#define TILT_WRIST   4
#define TILT_HAND    14

#define SAMPLE_DELAY_MS 20  // 50 Hz

bool readTilt(int pin) {
  if (digitalRead(pin) == LOW) {
    delay(10);
    return digitalRead(pin) == LOW;
  }
  return false;
}

void setup() {
  Serial.begin(115200);
  Serial2.begin(115200, SERIAL_8N1, 16, 17);
  delay(1000);

  analogReadResolution(12);

  pinMode(TILT_WRIST, INPUT_PULLUP);
  pinMode(TILT_HAND,  INPUT_PULLUP);

  Wire.begin(21, 22);
  Wire.setClock(100000);

  BMI270_7Semi::Config cfg;
  cfg.bus   = BMI270_7Semi::Bus::I2C;
  cfg.addr  = 0x68;
  cfg.sda   = 21;
  cfg.scl   = 22;
  cfg.i2cHz = 100000;

  bool imu_ok = false;
  if (imu.begin(cfg)) {
    imu_ok = true;
  } else {
    cfg.addr = 0x69;
    if (imu.begin(cfg)) imu_ok = true;
  }

  if (imu_ok) {
    imu.setAccelConfig(BMI2_ACC_ODR_100HZ, BMI2_ACC_RANGE_2G,
                       BMI2_ACC_NORMAL_AVG4, BMI2_PERF_OPT_MODE);
    imu.setGyroConfig(BMI2_GYR_ODR_200HZ, BMI2_GYR_RANGE_2000,
                      BMI2_GYR_NORMAL_MODE, BMI2_PERF_OPT_MODE);
    Serial.println("BMI270 initialized!");
  } else {
    Serial.println("WARNING: BMI270 not found");
  }

  delay(500);
  Serial.println("ASL Glove sensor stream starting...");
}

void loop() {
  // ── flex ──
  int flex_thumb  = analogRead(FLEX_THUMB);
  int flex_index  = analogRead(FLEX_INDEX);
  int flex_middle = analogRead(FLEX_MIDDLE);
  int flex_ring   = analogRead(FLEX_RING);
  int flex_pinky  = analogRead(FLEX_PINKY);

  // ── hall ──
  int hall_index  = analogRead(HALL_INDEX);
  int hall_middle = analogRead(HALL_MIDDLE);
  int hall_ring   = analogRead(HALL_RING);
  int hall_pinky  = analogRead(HALL_PINKY);

  // ── FSR ──
  int fsr_uv = analogRead(FSR_UV);

  // ── tilt ──
  bool tilt_wrist = readTilt(TILT_WRIST);
  bool tilt_hand  = readTilt(TILT_HAND);

  // ── IMU ──
  float ax = 0, ay = 0, az = 0;
  float gx = 0, gy = 0, gz = 0;
  imu.readAccel(ax, ay, az);
  imu.readGyro(gx, gy, gz);

  // ── build output ──
  String out = "";
  out += "--- FLEX (raw ADC 0-4095) ---\n";
  out += "Thumb:  " + String(flex_thumb)  + "\n";
  out += "Index:  " + String(flex_index)  + "\n";
  out += "Middle: " + String(flex_middle) + "\n";
  out += "Ring:   " + String(flex_ring)   + "\n";
  out += "Pinky:  " + String(flex_pinky)  + "\n";
  out += "--- HALL EFFECT ---\n";
  out += "Index:  " + String(hall_index)  + "\n";
  out += "Middle: " + String(hall_middle) + "\n";
  out += "Ring:   " + String(hall_ring)   + "\n";
  out += "Pinky:  " + String(hall_pinky)  + "\n";
  out += "--- FSR ---\n";
  out += "UV:     " + String(fsr_uv)      + "\n";
  out += "--- TILT ---\n";
  out += "Wrist: " + String(tilt_wrist ? "TILTED" : "upright") + "\n";
  out += "Hand:  " + String(tilt_hand  ? "TILTED" : "upright") + "\n";
  out += "--- IMU ---\n";
  out += "Accel (g)  X: " + String(ax, 3) + "  Y: " + String(ay, 3) + "  Z: " + String(az, 3) + "\n";
  out += "Gyro (d/s) X: " + String(gx, 3) + "  Y: " + String(gy, 3) + "  Z: " + String(gz, 3) + "\n";
  out += "\n";

  Serial.print(out);
  Serial2.print(out);

  delay(SAMPLE_DELAY_MS);
}
