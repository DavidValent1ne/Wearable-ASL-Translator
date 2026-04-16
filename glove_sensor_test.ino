// ═══════════════════════════════════════════════════
//  ESP32 ASL Glove — Flex + IMU Sensor Test
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

#define SAMPLE_DELAY_MS 500

void setup() {
  Serial.begin(115200);
  Serial2.begin(115200, SERIAL_8N1, 16, 17);  // UART to Pi
  delay(1000);

  analogReadResolution(12);

  // ── IMU init ──
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
    imu.setGyroConfig(BMI2_GYR_ODR_100HZ, BMI2_GYR_RANGE_2000,
                      BMI2_GYR_NORMAL_MODE, BMI2_PERF_OPT_MODE);
    Serial.println("BMI270 initialized!");
  } else {
    Serial.println("WARNING: BMI270 not found — IMU data will be 0");
  }

  delay(500);

  Serial.println("═══════════════════════════════════════");
  Serial.println("  ESP32 ASL Glove — Sensor Test");
  Serial.println("═══════════════════════════════════════\n");
}

void loop() {
  // ── read flex sensors ──
  int flex_thumb  = analogRead(FLEX_THUMB);
  int flex_index  = analogRead(FLEX_INDEX);
  int flex_middle = analogRead(FLEX_MIDDLE);
  int flex_ring   = analogRead(FLEX_RING);
  int flex_pinky  = analogRead(FLEX_PINKY);

  // ── read IMU ──
  float ax = 0, ay = 0, az = 0;
  float gx = 0, gy = 0, gz = 0;
  imu.readAccel(ax, ay, az);
  imu.readGyro(gx, gy, gz);

  // ── build output string ──
  String out = "";
  out += "--- FLEX SENSORS ---\n";
  out += "  Thumb:  " + String(flex_thumb)  + "\n";
  out += "  Index:  " + String(flex_index)  + "\n";
  out += "  Middle: " + String(flex_middle) + "\n";
  out += "  Ring:   " + String(flex_ring)   + "\n";
  out += "  Pinky:  " + String(flex_pinky)  + "\n";
  out += "--- IMU ---\n";
  out += "  Accel (g)  X: " + String(ax, 3) + "  Y: " + String(ay, 3) + "  Z: " + String(az, 3) + "\n";
  out += "  Gyro (d/s) X: " + String(gx, 3) + "  Y: " + String(gy, 3) + "  Z: " + String(gz, 3) + "\n";
  out += "\n";

  Serial.print(out);
  Serial2.print(out);

  delay(SAMPLE_DELAY_MS);
}
