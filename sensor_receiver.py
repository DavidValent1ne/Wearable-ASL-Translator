# ═══════════════════════════════════════════════════
#  ESP32 ASL Glove — Pi Zero UART Receiver
#  Receives sensor data from ESP32 over Serial0
#  Run on Pi Zero 2W via SSH
#  Sacramento State Senior Design
# ═══════════════════════════════════════════════════

import serial
import time

# open UART connection to ESP32
ser = serial.Serial(
    port='/dev/serial0',
    baudrate=115200,
    timeout=1
)

print("Listening for ESP32 data on /dev/serial0...")
print("Press Ctrl+C to stop\n")

try:
    while True:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line:
                print(line)
except KeyboardInterrupt:
    print("\nStopped.")
    ser.close()
