// ═══════════════════════════════════════════════════
//  ESP32 ASL Glove — OLED Name Tag Display
//  Receives detected letter from Pi over UDP WiFi
//  OLED: SSD1306 128x64 I2C
//  SDA = GPIO21, SCL = GPIO22
//  Sacramento State Senior Design
// ═══════════════════════════════════════════════════

#include <Wire.h>
#include <WiFi.h>
#include <WiFiUdp.h>
#include <ESPmDNS.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ── WiFi credentials ──
const char* SSID     = "valentines";
const char* PASSWORD = "whynot12";

// ── UDP ──
#define UDP_PORT 4210
WiFiUDP udp;

// ── OLED ──
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

String currentLetter = "";
String letterHistory = "";

void drawDisplay(String letter) {
  display.clearDisplay();

  // header
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("ASL Translator");
  display.drawLine(0, 10, 127, 10, SSD1306_WHITE);

  if (letter == "" || letter == "—") {
    display.setTextSize(1);
    display.setCursor(20, 28);
    display.println("Waiting for sign...");
  } else {
    display.setTextSize(4);
    int x = (SCREEN_WIDTH - 24) / 2;
    display.setCursor(x, 16);
    display.println(letter);
  }

  // history bar at bottom
  display.drawLine(0, 53, 127, 53, SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 56);
  String hist = letterHistory;
  if (hist.length() > 16) hist = hist.substring(hist.length() - 16);
  display.println(hist);

  display.display();
}

void setup() {
  Serial.begin(115200);
  delay(500);

  // ── OLED init ──
  Wire.begin(21, 22);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("ERROR: SSD1306 not found!");
    while (true) delay(1000);
  }

  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("Connecting to WiFi...");
  display.display();

  // ── WiFi connect ──
  WiFi.begin(SSID, PASSWORD);
  Serial.print("Connecting to WiFi");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() != WL_CONNECTED) {
    display.clearDisplay();
    display.setCursor(0, 0);
    display.println("WiFi failed!");
    display.println("Check credentials");
    display.display();
    Serial.println("\nWiFi connection failed!");
    while (true) delay(1000);
  }

  Serial.printf("\nConnected! IP: %s\n", WiFi.localIP().toString().c_str());

  // start mDNS
  if (MDNS.begin("oled-esp32")) {
    Serial.println("mDNS started — oled-esp32.local");
  }

  display.clearDisplay();
  display.setCursor(0, 0);
  display.println("Connected!");
  display.println(WiFi.localIP().toString());
  display.println("\nWaiting for data...");
  display.display();

  // ── start UDP ──
  udp.begin(UDP_PORT);
  Serial.printf("Listening on UDP port %d\n", UDP_PORT);

  delay(1500);
  drawDisplay("");
}

void loop() {
  // ── reconnect if WiFi drops ──
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi lost, reconnecting...");
    WiFi.reconnect();
    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
      delay(500);
      attempts++;
    }
    if (WiFi.status() == WL_CONNECTED) {
      udp.begin(UDP_PORT);
      Serial.println("Reconnected!");
    }
    return;
  }

  int packetSize = udp.parsePacket();
  if (packetSize) {
    char buf[32];
    int len = udp.read(buf, sizeof(buf) - 1);
    buf[len] = '\0';
    String received = String(buf);
    received.trim();

    Serial.printf("Received: %s\n", received.c_str());

    if (received == "PING") {
      // keepalive — ignore
    } else if (received == "SPACE") {
      letterHistory += " ";
      drawDisplay(currentLetter);
    } else if (received == "CLEAR") {
      letterHistory = "";
      currentLetter = "";
      drawDisplay("");
    } else if (received.length() == 1 || received == "—") {
      currentLetter = received;
      if (received != "—") {
        letterHistory += received;
        if (letterHistory.length() > 64) {
          letterHistory = letterHistory.substring(letterHistory.length() - 64);
        }
      }
      drawDisplay(currentLetter);
    }
  }
}