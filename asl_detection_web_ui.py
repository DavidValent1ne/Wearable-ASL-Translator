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

SERIAL_PORT = '/dev/serial0'
BAUD_RATE   = 115200

# ── FLEX THRESHOLDS ──
# below threshold = bent, above = straight
FLEX_THRESH = {
    'thumb':  1350,
    'index':   970,
    'middle': 1350,
    'ring':   1100,
    'pinky':  1030,
}

# partial bend thresholds for C detection
# C fingers sit between straight and fully bent
FLEX_C_THRESH = {
    'thumb':  1300,  # below straight, above full bent
    'index':   820,
    'middle': 1180,
    'ring':    900,
    'pinky':   840,
}

# ── HALL THRESHOLDS ──
# above threshold = thumb touching that finger
HALL_THRESH = {
    'index':  2370,
    'middle': 2350,
    'ring':   2000,  # lowered — E only needs slight touch
    'pinky':  2435,
}

# ── shared state ──
state = {
    'flex':   {'thumb': 0, 'index': 0, 'middle': 0, 'ring': 0, 'pinky': 0},
    'hall':   {'index': 0, 'middle': 0, 'ring': 0, 'pinky': 0},
    'tilt':   {'wrist': False, 'hand': False},
    'accel':  {'x': 0.0, 'y': 0.0, 'z': 0.0},
    'gyro':   {'x': 0.0, 'y': 0.0, 'z': 0.0},
    'letter': '—',
    'bent':   {'thumb': False, 'index': False, 'middle': False, 'ring': False, 'pinky': False},
    'touch':  {'index': False, 'middle': False, 'ring': False, 'pinky': False},
}

def is_bent(finger):
    return state['flex'][finger] < FLEX_THRESH[finger]

def is_straight(finger):
    return not is_bent(finger)

def is_touching(finger):
    return state['hall'][finger] > HALL_THRESH[finger]

def is_partial(finger):
    """finger is in C range — partially bent, not fully bent or straight"""
    val = state['flex'][finger]
    return FLEX_C_THRESH[finger] < val < FLEX_THRESH[finger] + 100

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

    state['bent']  = {'thumb': t, 'index': i, 'middle': m, 'ring': r, 'pinky': p}
    state['touch'] = {'index': ti, 'middle': tm, 'ring': tr, 'pinky': tp}

    fx = state['flex']

    # ── LETTER RULES (ordered by specificity) ──

    # E — all fingers bent, thumb touches ring
    if t and i and m and r and p and tr:
        return 'E'

    # F — thumb bent, index bent, middle/ring/pinky straight, thumb touches index
    if t and i and not m and not r and not p and ti:
        return 'F'

    # D — index straight, thumb touches middle, rest bent
    if not i and m and r and p and tm:
        return 'D'

    # X — all fingers bent, index partially bent (hooked), no touches
    if t and m and r and p and 700 < fx['index'] < 1100 and not ti and not tm and not tr and not tp:
        return 'X'

    # I — all fingers bent except pinky straight, no touches
    if t and i and m and r and not p and not ti and not tm and not tr and not tp:
        return 'I'

    # A — all fingers bent, thumb alongside (above S threshold), no touches
    if fx['thumb'] > 1350 and i and m and r and p and not ti and not tm and not tr and not tp:
        return 'A'

    # S — all fingers bent, thumb over fingers (below A threshold), no touches
    if fx['thumb'] <= 1350 and t and i and m and r and p and not ti and not tm and not tr and not tp:
        return 'S'

    # B — thumb bent, all fingers straight
    if t and not i and not m and not r and not p:
        return 'B'

    # C — all fingers partially curved, no touches
    if (fx['index']  > 800 and
        fx['middle'] > 1100 and
        fx['ring']   > 850 and
        fx['pinky']  > 800 and
        fx['index']  < FLEX_THRESH['index']  + 100 and
        fx['middle'] < FLEX_THRESH['middle'] + 100 and
        fx['ring']   < FLEX_THRESH['ring']   + 100 and
        fx['pinky']  < FLEX_THRESH['pinky']  + 100 and
        not ti and not tm and not tr and not tp):
        return 'C'

    # G — thumb and index straight, rest bent, hall index triggered
    if not t and not i and m and r and p and ti:
        return 'G'

    # L — thumb and index straight, rest bent, no hall touches
    if not t and not i and m and r and p and not ti:
        return 'L'

    # W — index/middle/ring straight, thumb and pinky bent
    if t and not i and not m and not r and p:
        return 'W'

    # Y — thumb and pinky straight, rest bent
    if not t and i and m and r and not p:
        return 'Y'

    return '—'

# ── UART PARSER ──
section = ['none']

def parse_line(line):
    line = line.strip()
    if not line:
        state['letter'] = detect_letter()
        return

    if '--- FLEX' in line:
        section[0] = 'flex'
        return
    elif '--- HALL' in line:
        section[0] = 'hall'
        return
    elif '--- TILT' in line:
        section[0] = 'tilt'
        return
    elif '--- IMU' in line:
        section[0] = 'imu'
        return

    if ':' not in line:
        return

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
                state['tilt']['wrist'] = 'tilted' in val.lower()
            elif key == 'hand':
                state['tilt']['hand'] = 'tilted' in val.lower()

        elif section[0] == 'imu':
            # format: "Accel (g)  X: 0.426  Y: -0.351  Z: 0.845"
            parts = val.split()
            i = 0
            while i < len(parts):
                if parts[i].startswith('X:'):
                    xval = parts[i][2:] if len(parts[i]) > 2 else parts[i+1]
                    if key.startswith('accel'):
                        state['accel']['x'] = float(xval)
                    else:
                        state['gyro']['x'] = float(xval)
                elif parts[i].startswith('Y:'):
                    yval = parts[i][2:] if len(parts[i]) > 2 else parts[i+1]
                    if key.startswith('accel'):
                        state['accel']['y'] = float(yval)
                    else:
                        state['gyro']['y'] = float(yval)
                elif parts[i].startswith('Z:'):
                    zval = parts[i][2:] if len(parts[i]) > 2 else parts[i+1]
                    if key.startswith('accel'):
                        state['accel']['z'] = float(zval)
                    else:
                        state['gyro']['z'] = float(zval)
                i += 1

    except Exception:
        pass

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

# ── HTML DASHBOARD ──
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
  .letter { font-size: 180px; font-weight: 700; color: #333; line-height: 1; transition: all 0.15s; }
  .letter.active { color: #1D9E75; }
  .letter-label { font-size: 13px; color: #666; margin-top: 8px; letter-spacing: 1px; }

  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; max-width: 960px; margin: 0 auto; }
  .card { background: #1a1a1a; border-radius: 10px; padding: 20px; }
  .card h2 { font-size: 11px; color: #555; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 16px; }

  .bar-row { margin-bottom: 10px; }
  .bar-label { font-size: 12px; color: #888; margin-bottom: 4px; display: flex; justify-content: space-between; }
  .bar-track { background: #252525; border-radius: 4px; height: 10px; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 4px; transition: width 0.1s; background: #1D9E75; }
  .bar-fill.bent { background: #EF9F27; }
  .bar-fill.touch { background: #e05a30; }

  .finger-vis { display: flex; gap: 10px; justify-content: center; margin-top: 4px; }
  .finger { width: 40px; text-align: center; }
  .finger-seg { height: 26px; border-radius: 4px; margin-bottom: 3px; background: #252525; transition: background 0.15s; }
  .finger-seg.bent { background: #EF9F27; }
  .finger-seg.touch { background: #e05a30; }
  .finger-name { font-size: 10px; color: #555; margin-top: 4px; }

  .imu-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-bottom: 16px; }
  .imu-val { background: #222; border-radius: 6px; padding: 8px; text-align: center; }
  .imu-axis { font-size: 10px; color: #555; margin-bottom: 2px; }
  .imu-num { font-size: 15px; font-weight: 600; color: #999; }

  .tilt-row { display: flex; gap: 10px; }
  .tilt-pill { flex: 1; text-align: center; padding: 10px; border-radius: 6px; background: #222; font-size: 12px; color: #666; transition: all 0.15s; }
  .tilt-pill.active { background: #534ab7; color: #eeedfe; }

  .history { max-width: 960px; margin: 20px auto 0; background: #1a1a1a; border-radius: 10px; padding: 20px; }
  .history h2 { font-size: 11px; color: #555; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 12px; }
  .history-text { font-size: 32px; font-weight: 700; color: #fff; letter-spacing: 6px; min-height: 48px; word-break: break-all; }
  .history-controls { margin-top: 12px; display: flex; gap: 10px; }
  .btn { padding: 8px 16px; border-radius: 6px; border: none; cursor: pointer; font-size: 12px; font-weight: 600; }
  .btn-clear { background: #333; color: #aaa; }
  .btn-space { background: #333; color: #aaa; }
  .btn-clear:hover { background: #444; }
  .btn-space:hover { background: #444; }
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
    <h2 style="margin-bottom:10px">Tilt</h2>
    <div class="tilt-row" id="tilt-row"></div>
  </div>
</div>

<div class="history">
  <h2>Signed Letters</h2>
  <div class="history-text" id="history-text"></div>
  <div class="history-controls">
    <button class="btn btn-space" onclick="addSpace()">Add Space</button>
    <button class="btn btn-clear" onclick="clearHistory()">Clear</button>
  </div>
</div>

<script>
const FLEX_MAX  = { thumb:1589, index:1403, middle:1863, ring:1651, pinky:1579 };
const FLEX_MIN  = { thumb:1109, index:541,  middle:839,  ring:551,  pinky:478  };
const HALL_REST = { index:1856, middle:1840, ring:1860, pinky:1936 };
const HALL_MAX  = { index:2884, middle:2861, ring:2859, pinky:2931 };

let history = '';
let lastLetter = '—';
let holdStart = null;
const HOLD_MS = 800;

function flexPct(f, v) {
  return Math.max(0, Math.min(100, ((FLEX_MAX[f]-v)/(FLEX_MAX[f]-FLEX_MIN[f]))*100));
}
function hallPct(f, v) {
  return Math.max(0, Math.min(100, ((v-HALL_REST[f])/(HALL_MAX[f]-HALL_REST[f]))*100));
}
function addSpace() { history += ' '; document.getElementById('history-text').textContent = history; }
function clearHistory() { history = ''; document.getElementById('history-text').textContent = ''; }

async function update() {
  try {
    const r = await fetch('/data');
    const d = await r.json();
    const letter = d.letter;

    // letter display
    const el = document.getElementById('letter');
    el.textContent = letter;
    el.className = 'letter' + (letter !== '—' ? ' active' : '');

    // hold to add to history
    if (letter !== '—' && letter === lastLetter) {
      if (!holdStart) holdStart = Date.now();
      else if (Date.now() - holdStart > HOLD_MS) {
        history += letter;
        document.getElementById('history-text').textContent = history;
        holdStart = null;
        await new Promise(res => setTimeout(res, 1000));
      }
    } else {
      holdStart = null;
    }
    lastLetter = letter;

    // flex bars
    const fingers = ['thumb','index','middle','ring','pinky'];
    document.getElementById('flex-bars').innerHTML = fingers.map(f =>
      `<div class="bar-row">
        <div class="bar-label"><span>${f}</span><span>${d.flex[f]}</span></div>
        <div class="bar-track"><div class="bar-fill ${d.bent[f]?'bent':''}" style="width:${flexPct(f,d.flex[f])}%"></div></div>
      </div>`).join('');

    // hall bars
    const hf = ['index','middle','ring','pinky'];
    document.getElementById('hall-bars').innerHTML = hf.map(f =>
      `<div class="bar-row">
        <div class="bar-label"><span>thumb → ${f}</span><span>${d.hall[f]}</span></div>
        <div class="bar-track"><div class="bar-fill bar-hall ${d.touch[f]?'touch':''}" style="width:${hallPct(f,d.hall[f])}%"></div></div>
      </div>`).join('');

    // finger vis
    document.getElementById('finger-vis').innerHTML = fingers.map(f => {
      const touch = f !== 'thumb' && d.touch[f];
      const cls = (d.bent[f]?'bent':'') + (touch?' touch':'');
      return `<div class="finger">
        <div class="finger-seg ${cls}"></div>
        <div class="finger-seg ${cls}"></div>
        <div class="finger-seg ${cls}"></div>
        <div class="finger-name">${f[0].toUpperCase()}</div>
      </div>`;
    }).join('');

    // IMU
    const axes = ['x','y','z'];
    document.getElementById('imu-grid').innerHTML =
      axes.map(a => `<div class="imu-val"><div class="imu-axis">Accel ${a.toUpperCase()}</div><div class="imu-num">${d.accel[a].toFixed(2)}</div></div>`).join('') +
      axes.map(a => `<div class="imu-val"><div class="imu-axis">Gyro ${a.toUpperCase()}</div><div class="imu-num">${d.gyro[a].toFixed(2)}</div></div>`).join('');

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
        pass

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
