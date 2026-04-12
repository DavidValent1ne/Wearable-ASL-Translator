# ═══════════════════════════════════════════════════
#  ESP32 ASL Glove — Rule-Based Letter Detection
#  Live web dashboard served on port 5000
#  Run on Pi Zero 2W
#  Sacramento State Senior Design
# ═══════════════════════════════════════════════════

import serial
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

# ── UART ──
SERIAL_PORT = '/dev/serial0'
BAUD_RATE   = 115200

# ── FLEX THRESHOLDS (below = bent, above = straight) ──
FLEX_THRESH = {
    'thumb':  1350,
    'index':   970,
    'middle': 1350,
    'ring':   1100,
    'pinky':  1030,
}

# ── HALL THRESHOLDS (above = thumb touching finger) ──
HALL_THRESH = {
    'index':  2370,
    'middle': 2350,
    'ring':   2360,
    'pinky':  2435,
}

# ── shared state ──
state = {
    'flex':   {'thumb': 0, 'index': 0, 'middle': 0, 'ring': 0, 'pinky': 0},
    'hall':   {'index': 0, 'middle': 0, 'ring': 0, 'pinky': 0},
    'tilt':   {'wrist': False, 'hand': False},
    'accel':  {'x': 0, 'y': 0, 'z': 0},
    'gyro':   {'x': 0, 'y': 0, 'z': 0},
    'letter': '—',
    'bent':   {'thumb': False, 'index': False, 'middle': False, 'ring': False, 'pinky': False},
    'touch':  {'index': False, 'middle': False, 'ring': False, 'pinky': False},
}

def is_bent(finger):
    return state['flex'][finger] < FLEX_THRESH[finger]

def is_touching(finger):
    return state['hall'][finger] > HALL_THRESH[finger]

def detect_letter():
    t  = is_bent('thumb')
    i  = is_bent('index')
    m  = is_bent('middle')
    r  = is_bent('ring')
    p  = is_bent('pinky')
    ti = is_touching('index')
    tm = is_touching('middle')
    tr = is_touching('ring')
    tp = is_touching('pinky')

    # update bent/touch state for UI
    state['bent']  = {'thumb': t, 'index': i, 'middle': m, 'ring': r, 'pinky': p}
    state['touch'] = {'index': ti, 'middle': tm, 'ring': tr, 'pinky': tp}

    # ── RULE-BASED LETTER DETECTION ──

    # A — fist, thumb resting on side (all bent, no touches)
    if t and i and m and r and p and not ti and not tm and not tr and not tp:
        return 'A'

    # B — all fingers straight up, thumb bent across palm
    if t and not i and not m and not r and not p:
        return 'B'

    # C — all fingers curved (partially bent), no touches
    # approximated as all fingers partially bent
    if not t and not i and not m and not r and not p:
        return 'C'

    # D — index up, thumb touches middle, rest bent
    if not i and m and r and p and tm:
        return 'D'

    # F — index and middle form circle with thumb
    # thumb touches index, middle slightly bent
    if ti and not m and r and p:
        return 'F'

    # G — index and thumb point sideways
    # index straight, thumb straight, rest bent
    if not t and not i and m and r and p:
        return 'G'

    # L — index straight up, thumb out, rest bent
    if not t and not i and m and r and p and not ti:
        return 'L'

    # S — fist with thumb over fingers
    if t and i and m and r and p and not ti and not tm and not tr and not tp:
        return 'S'  # similar to A — refine with IMU later

    # W — three fingers up (index, middle, ring), pinky and thumb bent
    if t and not i and not m and not r and p:
        return 'W'

    # Y — pinky and thumb out, rest bent
    if not t and i and m and r and not p:
        return 'Y'

    return '—'

def parse_uart(line):
    line = line.strip()
    try:
        if line.startswith('Thumb:'):
            state['flex']['thumb'] = int(line.split(':')[1].strip())
        elif line.startswith('Index:') and 'HALL' not in line:
            # disambiguate flex vs hall index
            pass
        elif line.startswith('Middle:') and 'HALL' not in line:
            pass
        elif line.startswith('Ring:') and 'HALL' not in line:
            pass
        elif line.startswith('Pinky:') and 'HALL' not in line:
            pass
    except:
        pass

# better parser — tracks section context
section = ['none']

def parse_line(line):
    line = line.strip()
    if '--- FLEX' in line:
        section[0] = 'flex'
    elif '--- HALL' in line:
        section[0] = 'hall'
    elif '--- TILT' in line:
        section[0] = 'tilt'
    elif '--- IMU' in line:
        section[0] = 'imu'
    elif ':' in line:
        try:
            key, val = line.split(':', 1)
            key = key.strip().lower()
            val = val.strip()

            if section[0] == 'flex':
                if key in state['flex']:
                    state['flex'][key] = int(val)

            elif section[0] == 'hall':
                if key in state['hall']:
                    state['hall'][key] = int(val)

            elif section[0] == 'tilt':
                if key == 'wrist':
                    state['tilt']['wrist'] = val.upper() == 'TILTED'
                elif key == 'hand':
                    state['tilt']['hand'] = val.upper() == 'TILTED'

            elif section[0] == 'imu':
                if key.startswith('accel'):
                    parts = val.split()
                    for p in parts:
                        if p.startswith('X:'):
                            state['accel']['x'] = float(p[2:])
                        elif p.startswith('Y:'):
                            state['accel']['y'] = float(p[2:])
                        elif p.startswith('Z:'):
                            state['accel']['z'] = float(p[2:])
                elif key.startswith('gyro'):
                    parts = val.split()
                    for p in parts:
                        if p.startswith('X:'):
                            state['gyro']['x'] = float(p[2:])
                        elif p.startswith('Y:'):
                            state['gyro']['y'] = float(p[2:])
                        elif p.startswith('Z:'):
                            state['gyro']['z'] = float(p[2:])
        except:
            pass

    # update letter after each full block
    if line == '' or '---' in line:
        state['letter'] = detect_letter()

def uart_thread():
    while True:
        try:
            ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
            print("Connected to ESP32 on", SERIAL_PORT)
            while True:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore')
                    parse_line(line)
        except Exception as e:
            print("UART error:", e)
            time.sleep(2)

# ── WEB SERVER ──
HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ASL Glove — Live Detection</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: Arial, sans-serif; background: #0f0f0f; color: #e0e0e0; padding: 24px; }
  h1 { text-align: center; font-size: 18px; color: #aaa; margin-bottom: 24px; letter-spacing: 2px; text-transform: uppercase; }

  .letter-box { text-align: center; margin-bottom: 32px; }
  .letter { font-size: 180px; font-weight: 700; color: #fff; line-height: 1; transition: all 0.15s; }
  .letter.active { color: #1D9E75; }
  .letter-label { font-size: 13px; color: #666; margin-top: 8px; letter-spacing: 1px; }

  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; max-width: 900px; margin: 0 auto; }
  .card { background: #1a1a1a; border-radius: 10px; padding: 20px; }
  .card h2 { font-size: 12px; color: #666; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 16px; }

  .bar-row { margin-bottom: 12px; }
  .bar-label { font-size: 12px; color: #aaa; margin-bottom: 4px; display: flex; justify-content: space-between; }
  .bar-track { background: #2a2a2a; border-radius: 4px; height: 12px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 4px; transition: width 0.1s; }
  .bar-flex { background: #1D9E75; }
  .bar-flex.bent { background: #EF9F27; }
  .bar-hall { background: #534ab7; }
  .bar-hall.touch { background: #e05a30; }

  .finger-vis { display: flex; gap: 8px; justify-content: center; margin-top: 8px; }
  .finger { width: 36px; text-align: center; }
  .finger-seg { height: 28px; border-radius: 4px; margin-bottom: 3px; background: #2a2a2a; transition: background 0.15s; }
  .finger-seg.bent { background: #EF9F27; }
  .finger-seg.touch { background: #e05a30; }
  .finger-name { font-size: 10px; color: #666; }

  .imu-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; }
  .imu-val { background: #222; border-radius: 6px; padding: 8px; text-align: center; }
  .imu-axis { font-size: 10px; color: #666; }
  .imu-num { font-size: 16px; font-weight: 600; color: #aaa; }

  .tilt-row { display: flex; gap: 12px; }
  .tilt-pill { flex: 1; text-align: center; padding: 10px; border-radius: 6px; background: #222; font-size: 13px; transition: background 0.15s; }
  .tilt-pill.active { background: #534ab7; color: #fff; }
</style>
</head>
<body>
<h1>ASL Glove — Live Detection</h1>

<div class="letter-box">
  <div class="letter" id="letter">—</div>
  <div class="letter-label">Detected Letter</div>
</div>

<div class="grid">
  <div class="card">
    <h2>Flex Sensors</h2>
    <div id="flex-bars"></div>
  </div>
  <div class="card">
    <h2>Hall Effect Sensors</h2>
    <div id="hall-bars"></div>
  </div>
  <div class="card">
    <h2>Finger State</h2>
    <div class="finger-vis" id="finger-vis"></div>
  </div>
  <div class="card">
    <h2>IMU</h2>
    <div class="imu-grid" id="imu-grid"></div>
    <br>
    <h2 style="margin-bottom:10px">Tilt</h2>
    <div class="tilt-row" id="tilt-row"></div>
  </div>
</div>

<script>
const FLEX_MAX  = { thumb: 1589, index: 1403, middle: 1863, ring: 1651, pinky: 1579 };
const FLEX_MIN  = { thumb: 1109, index: 541,  middle: 839,  ring: 551,  pinky: 478  };
const HALL_REST = { index: 1856, middle: 1840, ring: 1860, pinky: 1936 };
const HALL_MAX  = { index: 2884, middle: 2861, ring: 2859, pinky: 2931 };

function flexPct(finger, val) {
  const range = FLEX_MAX[finger] - FLEX_MIN[finger];
  return Math.max(0, Math.min(100, ((FLEX_MAX[finger] - val) / range) * 100));
}
function hallPct(finger, val) {
  const range = HALL_MAX[finger] - HALL_REST[finger];
  return Math.max(0, Math.min(100, ((val - HALL_REST[finger]) / range) * 100));
}

async function update() {
  try {
    const r = await fetch('/data');
    const d = await r.json();

    const letter = d.letter;
    const el = document.getElementById('letter');
    el.textContent = letter;
    el.className = 'letter' + (letter !== '—' ? ' active' : '');

    // flex bars
    const fingers = ['thumb','index','middle','ring','pinky'];
    let fb = '';
    fingers.forEach(f => {
      const pct = flexPct(f, d.flex[f]);
      const bent = d.bent[f];
      fb += `<div class="bar-row">
        <div class="bar-label"><span>${f}</span><span>${d.flex[f]}</span></div>
        <div class="bar-track"><div class="bar-fill bar-flex ${bent?'bent':''}" style="width:${pct}%"></div></div>
      </div>`;
    });
    document.getElementById('flex-bars').innerHTML = fb;

    // hall bars
    const hfingers = ['index','middle','ring','pinky'];
    let hb = '';
    hfingers.forEach(f => {
      const pct = hallPct(f, d.hall[f]);
      const touch = d.touch[f];
      hb += `<div class="bar-row">
        <div class="bar-label"><span>thumb → ${f}</span><span>${d.hall[f]}</span></div>
        <div class="bar-track"><div class="bar-fill bar-hall ${touch?'touch':''}" style="width:${pct}%"></div></div>
      </div>`;
    });
    document.getElementById('hall-bars').innerHTML = hb;

    // finger vis
    let fv = '';
    fingers.forEach(f => {
      const touch = f !== 'thumb' && d.touch[f];
      fv += `<div class="finger">
        <div class="finger-seg ${d.bent[f]?'bent':''} ${touch?'touch':''}"></div>
        <div class="finger-seg ${d.bent[f]?'bent':''} ${touch?'touch':''}"></div>
        <div class="finger-seg ${d.bent[f]?'bent':''} ${touch?'touch':''}"></div>
        <div class="finger-name">${f[0].toUpperCase()}</div>
      </div>`;
    });
    document.getElementById('finger-vis').innerHTML = fv;

    // IMU
    const axes = ['x','y','z'];
    let ig = '';
    axes.forEach(a => {
      ig += `<div class="imu-val"><div class="imu-axis">Accel ${a.toUpperCase()}</div><div class="imu-num">${d.accel[a].toFixed(2)}</div></div>`;
    });
    axes.forEach(a => {
      ig += `<div class="imu-val"><div class="imu-axis">Gyro ${a.toUpperCase()}</div><div class="imu-num">${d.gyro[a].toFixed(2)}</div></div>`;
    });
    document.getElementById('imu-grid').innerHTML = ig;

    // tilt
    document.getElementById('tilt-row').innerHTML =
      `<div class="tilt-pill ${d.tilt.wrist?'active':''}">Wrist ${d.tilt.wrist?'TILTED':'upright'}</div>
       <div class="tilt-pill ${d.tilt.hand?'active':''}">Hand ${d.tilt.hand?'TILTED':'upright'}</div>`;

  } catch(e) {}
  setTimeout(update, 100);
}
update();
</script>
</body>
</html>"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress request logs

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(HTML.encode())
        elif self.path == '/data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(state).encode())

if __name__ == '__main__':
    t = threading.Thread(target=uart_thread, daemon=True)
    t.start()

    port = 5000
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f"ASL Dashboard running at http://piglove.local:{port}")
    print("Press Ctrl+C to stop")
    server.serve_forever()
