# ═══════════════════════════════════════════════════
#  ESP32 ASL Glove — Detection Server v2
#  Rule-based letter detection + web dashboard
#  UDP to OLED ESP32
#  Run on Pi Zero 2W
#  Sacramento State Senior Design
# ═══════════════════════════════════════════════════

import serial
import threading
import time
import socket
import json
import re
from http.server import HTTPServer, BaseHTTPRequestHandler

SERIAL_PORT  = '/dev/serial0'
BAUD_RATE    = 115200

# ── UDP to OLED ESP32 ──
OLED_UDP_PORT  = 4210
BROADCAST_IP   = '10.0.0.255'
udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

def send_to_oled(letter):
    try:
        udp_sock.sendto(letter.encode(), (BROADCAST_IP, OLED_UDP_PORT))
    except Exception as e:
        print("UDP error:", e)

# ── FLEX THRESHOLDS (below = bent) ──
FLEX_THRESH = {
    'thumb':  1350,
    'index':   970,
    'middle': 1350,
    'ring':   1100,
    'pinky':  1030,
}

# ── HALL THRESHOLDS (above = touching) ──
HALL_THRESH = {
    'index':  1900,
    'middle': 1900,
    'ring':   1900,
    'pinky':  2435,
}

# ── shared state ──
state = {
    'flex':         {'thumb': 0, 'index': 0, 'middle': 0, 'ring': 0, 'pinky': 0},
    'hall':         {'index': 0, 'middle': 0, 'ring': 0, 'pinky': 0},
    'fsr':          {'uv': 0},
    'tilt':         {'wrist': False, 'hand': False},
    'tilt_display': {'wrist': False, 'hand': False},
    'accel':        {'x': 0.0, 'y': 0.0, 'z': 0.0},
    'gyro':         {'x': 0.0, 'y': 0.0, 'z': 0.0},
    'letter':       '—',
    'display_letter': '—',
    'bent':         {'thumb': False, 'index': False, 'middle': False, 'ring': False, 'pinky': False},
    'touch':        {'index': False, 'middle': False, 'ring': False, 'pinky': False},
}

# ── helper functions ──
def is_bent(finger):
    return state['flex'][finger] < FLEX_THRESH[finger]

def is_touching(finger):
    return state['hall'][finger] > HALL_THRESH[finger]

def wrist_tilted():
    return not state['tilt']['wrist']  # inverted

def hand_tilted():
    return state['tilt']['hand']

# ── J motion detector ──
j_gyro_window = []
J_WINDOW_SIZE    = 15
J_PEAK_THRESH    = 250.0
J_SETTLE_THRESH  = 30.0
j_confirmed      = False
j_confirmed_time = 0.0
J_DISPLAY_SECONDS = 1.5

def update_j_detector(t, i, m, r, p, ti, tm, tr, tp):
    global j_confirmed, j_confirmed_time
    gyro_mag = (state['gyro']['x']**2 + state['gyro']['y']**2 + state['gyro']['z']**2) ** 0.5
    in_i_pos = t and i and m and r and not p and not ti and not tm and not tr and not tp
    if in_i_pos:
        j_gyro_window.append(gyro_mag)
        if len(j_gyro_window) > J_WINDOW_SIZE:
            j_gyro_window.pop(0)
        if (len(j_gyro_window) >= 5 and
                max(j_gyro_window) > J_PEAK_THRESH and
                gyro_mag < J_SETTLE_THRESH):
            j_confirmed = True
            j_confirmed_time = time.time()
            j_gyro_window.clear()
    else:
        j_gyro_window.clear()

def is_j_active():
    return j_confirmed and (time.time() - j_confirmed_time) < J_DISPLAY_SECONDS

# ── Z motion detector ──
z_gyro_window = []
Z_WINDOW_SIZE    = 20
Z_PEAK_THRESH    = 100.0
Z_SETTLE_THRESH  = 20.0
z_confirmed      = False
z_confirmed_time = 0.0
Z_DISPLAY_SECONDS = 1.5

def update_z_detector(t, i, m, r, p, ti, tm, tr, tp):
    global z_confirmed, z_confirmed_time
    gyro_mag = (state['gyro']['x']**2 + state['gyro']['y']**2 + state['gyro']['z']**2) ** 0.5
    in_z_pos = t and not i and m and r and p and not ti and not tm and not tr and not tp
    if in_z_pos:
        z_gyro_window.append(gyro_mag)
        if len(z_gyro_window) > Z_WINDOW_SIZE:
            z_gyro_window.pop(0)
        if (len(z_gyro_window) >= 5 and
                max(z_gyro_window) > Z_PEAK_THRESH and
                gyro_mag < Z_SETTLE_THRESH):
            z_confirmed = True
            z_confirmed_time = time.time()
            z_gyro_window.clear()
    else:
        z_gyro_window.clear()

def is_z_active():
    return z_confirmed and (time.time() - z_confirmed_time) < Z_DISPLAY_SECONDS

# ── letter persistence ──
last_detected      = '—'
last_detected_time = 0.0
PERSIST_SECONDS    = 1.0

def get_display_letter():
    now = time.time()
    if last_detected != '—' and (now - last_detected_time) < PERSIST_SECONDS:
        return last_detected
    return state['letter']

# ── UART send throttle ──
last_sent_letter   = '—'
letter_hold_start  = None
HOLD_SECONDS       = 0.8

def maybe_send_letter(letter):
    global last_sent_letter, letter_hold_start, last_detected, last_detected_time
    now = time.time()
    if letter != '—':
        last_detected = letter
        last_detected_time = now
    if letter != '—' and letter == last_sent_letter:
        if letter_hold_start is None:
            letter_hold_start = now
        elif now - letter_hold_start >= HOLD_SECONDS:
            send_to_oled(letter)
            letter_hold_start = None
            time.sleep(0.8)
    else:
        letter_hold_start = None
    last_sent_letter = letter

# ── letter detection ──
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
    wt = wrist_tilted()
    ht = hand_tilted()
    fx = state['flex']

    state['bent']         = {'thumb': t, 'index': i, 'middle': m, 'ring': r, 'pinky': p}
    state['touch']        = {'index': ti, 'middle': tm, 'ring': tr, 'pinky': tp}
    state['tilt_display'] = {'wrist': wt, 'hand': ht}

    update_j_detector(t, i, m, r, p, ti, tm, tr, tp)
    update_z_detector(t, i, m, r, p, ti, tm, tr, tp)

    if is_j_active(): return 'J'
    if is_z_active(): return 'Z'

    # O — all bent, thumb touches middle
    if t and i and m and r and p and tm and not tr and not ti:
        return 'O'
    # E — all bent, thumb touches ring
    if t and i and m and r and p and tr:
        return 'E'
    # F — thumb+index bent and touching, rest straight
    if t and i and not m and not r and not p and ti:
        return 'F'
    # D — index straight, thumb touches middle, rest bent
    if not i and m and r and p and tm:
        return 'D'
    # X — all bent, index hooked (950-1100), no touches
    if t and m and r and p and 950 < fx['index'] < 1100 and not ti and not tm and not tr and not tp:
        return 'X'
    # T — all bent, thumb slightly bent (1250-1500), hand tilted
    if 1250 < fx['thumb'] <= 1500 and i and m and r and p and ht and not ti and not tm and not tr and not tp:
        return 'T'
    # N — all bent, ring significantly less bent than S (ring > 800), no touches
    if t and i and m and r and p and fx['ring'] > 800 and (fx['middle'] - fx['index']) < 420 and not ti and not tm and not tr and not tp:
        return 'N'
    # M — all bent, middle significantly less bent than BOTH index and ring
    #     data-backed thresholds: middle-index > 420, middle-ring > 380
    if t and i and m and r and p and (fx['middle'] - fx['index']) > 420 and (fx['middle'] - fx['ring']) > 380 and not ti and not tm and not tr and not tp:
        return 'M'
    # I — all bent except pinky, no touches
    if t and i and m and r and not p and not ti and not tm and not tr and not tp:
        return 'I'
    # A — all bent, thumb fully straight (> 1500), no touches
    if fx['thumb'] > 1500 and i and m and r and p and not ti and not tm and not tr and not tp:
        return 'A'
    # S — all fingers fully bent with tight thresholds, no touches
    if fx['thumb'] <= 1140 and fx['index'] <= 590 and fx['middle'] <= 900 and fx['ring'] <= 640 and fx['pinky'] <= 520 and not ti and not tm and not tr and not tp:
        return 'S'
    # B — thumb bent, all fingers straight
    if t and not i and not m and not r and not p:
        return 'B'
    # C — all fingers partially curved
    if (fx['index']  > 800 and fx['middle'] > 1100 and
            fx['ring'] > 850 and fx['pinky'] > 800 and
            fx['index']  < FLEX_THRESH['index']  + 100 and
            fx['middle'] < FLEX_THRESH['middle'] + 100 and
            fx['ring']   < FLEX_THRESH['ring']   + 100 and
            fx['pinky']  < FLEX_THRESH['pinky']  + 100 and
            not ti and not tm and not tr and not tp):
        return 'C'
    # Q — thumb+index straight, rest bent, hall index, wrist tilted
    if not t and not i and m and r and p and ti and wt:
        return 'Q'
    # G — thumb+index straight, rest bent, hall index, wrist upright
    if not t and not i and m and r and p and ti and not wt:
        return 'G'
    # P — thumb/index/middle straight, ring/pinky bent, hand tilted
    if not t and not i and not m and r and p and ht:
        return 'P'
    # K — thumb/index/middle straight, ring/pinky bent, hand upright
    if not t and not i and not m and r and p and not ht:
        return 'K'
    # H — index+middle straight, rest bent, hand tilted
    if t and not i and not m and r and p and ht:
        return 'H'
    # U — index+middle straight, fingers touching (FSR > 1000), no tilt
    if t and not i and fx['middle'] > 1750 and r and p and state['fsr']['uv'] > 1000 and not ht and not wt:
        return 'U'
    # V — index+middle straight, fingers apart (FSR <= 1000), no tilt
    if t and not i and fx['middle'] > 1750 and r and p and state['fsr']['uv'] <= 1000 and not ht and not wt:
        return 'V'
    # R — index straight, middle slightly bent, rest bent, no tilt
    if t and not i and fx['middle'] > 1350 and fx['middle'] < 1750 and r and p and not ht and not wt:
        return 'R'
    # L — thumb+index straight, rest bent, no touches
    if not t and not i and m and r and p and not ti:
        return 'L'
    # W — index/middle/ring straight, thumb+pinky bent
    if t and not i and not m and not r and p:
        return 'W'
    # Y — thumb+pinky straight, rest bent
    if not t and i and m and r and not p:
        return 'Y'

    return '—'

# ── UART parser ──
section = ['none']

def parse_line(line):
    line = line.strip()
    if not line:
        state['letter'] = detect_letter()
        maybe_send_letter(state['letter'])
        return

    if '--- FLEX' in line:   section[0] = 'flex';   return
    if '--- HALL' in line:   section[0] = 'hall';   return
    if '--- FSR'  in line:   section[0] = 'fsr';    return
    if '--- TILT' in line:   section[0] = 'tilt';   return
    if '--- IMU'  in line:   section[0] = 'imu';    return

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
        elif section[0] == 'fsr':
            if key == 'uv':
                state['fsr']['uv'] = int(val)
        elif section[0] == 'tilt':
            if key == 'wrist':
                state['tilt']['wrist'] = 'tilted' in val.lower()
            elif key == 'hand':
                state['tilt']['hand'] = 'tilted' in val.lower()
        elif section[0] == 'imu':
            numbers = re.findall(r'[XYZ]:\s*([-\d.]+)', line)
            axes = ['x', 'y', 'z']
            for idx, v in enumerate(numbers[:3]):
                if key.startswith('accel'):
                    state['accel'][axes[idx]] = float(v)
                else:
                    state['gyro'][axes[idx]] = float(v)
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

# ── HTML dashboard ──
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
  .btn-clear:hover, .btn-space:hover { background: #444; }
  .fsr-bar { background: #1a1a1a; border-radius: 10px; padding: 20px; max-width: 960px; margin: 20px auto 0; }
  .fsr-bar h2 { font-size: 11px; color: #555; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 16px; }
  .fsr-track { background: #252525; border-radius: 4px; height: 14px; overflow: hidden; }
  .fsr-fill { height: 100%; border-radius: 4px; transition: width 0.1s; background: #534ab7; }
  .fsr-fill.active { background: #1D9E75; }
  .fsr-labels { display: flex; justify-content: space-between; font-size: 11px; color: #555; margin-top: 6px; }
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
    <button class="btn btn-space" onclick="sendCmd('SPACE')">Add Space</button>
    <button class="btn btn-clear" onclick="sendCmd('CLEAR')">Clear</button>
  </div>
</div>
<div class="fsr-bar">
  <h2>FSR — U/V finger contact</h2>
  <div class="fsr-track"><div class="fsr-fill" id="fsr-fill" style="width:0%"></div></div>
  <div class="fsr-labels">
    <span>0 — fingers apart (V)</span>
    <span id="fsr-val">0</span>
    <span>4095 — fingers touching (U)</span>
  </div>
</div>
<div class="oled-status">
  <div class="status-dot"></div>
  Letters also sent to OLED display (hold sign 0.8s to register)
</div>
<script>
const FLEX_MAX  = {thumb:1589,index:1403,middle:1863,ring:1651,pinky:1579};
const FLEX_MIN  = {thumb:1109,index:541, middle:839, ring:551, pinky:478};
const HALL_REST = {index:1856,middle:1840,ring:1860,pinky:1936};
const HALL_MAX  = {index:2884,middle:2861,ring:2859,pinky:2931};
let history = '';
let lastLetter = '—';
let holdStart = null;
const HOLD_MS = 800;
function flexPct(f,v){return Math.max(0,Math.min(100,((FLEX_MAX[f]-v)/(FLEX_MAX[f]-FLEX_MIN[f]))*100));}
function hallPct(f,v){return Math.max(0,Math.min(100,((v-HALL_REST[f])/(HALL_MAX[f]-HALL_REST[f]))*100));}
async function sendCmd(cmd) {
  await fetch('/cmd?action='+cmd);
  if(cmd==='SPACE'){history+=' ';document.getElementById('history-text').textContent=history;}
  if(cmd==='CLEAR'){history='';document.getElementById('history-text').textContent='';}
}
async function update() {
  try {
    const r = await fetch('/data');
    const d = await r.json();
    const letter = d.display_letter;
    const el = document.getElementById('letter');
    el.textContent = letter;
    el.className = 'letter'+(letter!=='—'?' active':'');
    if(letter!=='—'&&letter===lastLetter){
      if(!holdStart)holdStart=Date.now();
      else if(Date.now()-holdStart>HOLD_MS){
        history+=letter;
        document.getElementById('history-text').textContent=history;
        holdStart=null;
        await new Promise(res=>setTimeout(res,800));
      }
    } else {holdStart=null;}
    lastLetter=letter;
    const fingers=['thumb','index','middle','ring','pinky'];
    document.getElementById('flex-bars').innerHTML=fingers.map(f=>
      `<div class="bar-row"><div class="bar-label"><span>${f}</span><span>${d.flex[f]}</span></div>
      <div class="bar-track"><div class="bar-fill ${d.bent[f]?'bent':''}" style="width:${flexPct(f,d.flex[f])}%"></div></div></div>`).join('');
    const hf=['index','middle','ring','pinky'];
    document.getElementById('hall-bars').innerHTML=hf.map(f=>
      `<div class="bar-row"><div class="bar-label"><span>thumb → ${f}</span><span>${d.hall[f]}</span></div>
      <div class="bar-track"><div class="bar-fill ${d.touch[f]?'touch':''}" style="width:${hallPct(f,d.hall[f])}%"></div></div></div>`).join('');
    document.getElementById('finger-vis').innerHTML=fingers.map(f=>{
      const touch=f!=='thumb'&&d.touch[f];
      const cls=(d.bent[f]?'bent':'')+(touch?' touch':'');
      return `<div class="finger"><div class="finger-seg ${cls}"></div><div class="finger-seg ${cls}"></div><div class="finger-seg ${cls}"></div><div class="finger-name">${f[0].toUpperCase()}</div></div>`;
    }).join('');
    // FSR bar
    const fsrVal = d.fsr.uv;
    const fsrPct = Math.min(100, (fsrVal / 4095) * 100);
    const fsrFill = document.getElementById('fsr-fill');
    fsrFill.style.width = fsrPct + '%';
    fsrFill.className = 'fsr-fill' + (fsrVal > 1000 ? ' active' : '');
    document.getElementById('fsr-val').textContent = fsrVal;

    const axes=['x','y','z'];
    document.getElementById('imu-grid').innerHTML=
      axes.map(a=>`<div class="imu-val"><div class="imu-axis">Accel ${a.toUpperCase()}</div><div class="imu-num">${d.accel[a].toFixed(2)}</div></div>`).join('')+
      axes.map(a=>`<div class="imu-val"><div class="imu-axis">Gyro ${a.toUpperCase()}</div><div class="imu-num">${d.gyro[a].toFixed(2)}</div></div>`).join('');
    document.getElementById('tilt-row').innerHTML=
      `<div class="tilt-pill ${d.tilt_display.wrist?'active':''}">Wrist ${d.tilt_display.wrist?'TILTED':'upright'}</div>
       <div class="tilt-pill ${d.tilt_display.hand?'active':''}">Hand ${d.tilt_display.hand?'TILTED':'upright'}</div>`;
  } catch(e){}
  setTimeout(update,100);
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
            response = dict(state)
            response['display_letter'] = get_display_letter()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode())
        elif self.path.startswith('/cmd'):
            action = self.path.split('action=')[-1] if 'action=' in self.path else ''
            if action in ('SPACE', 'CLEAR'):
                send_to_oled(action)
            self.send_response(200)
            self.end_headers()

if __name__ == '__main__':
    t = threading.Thread(target=uart_thread, daemon=True)
    t.start()
    port = 5000
    server = HTTPServer(('0.0.0.0', port), Handler)
    print(f"ASL Dashboard running at http://piglove.local:{port}")
    print(f"Sending letters to OLED ESP32 via UDP broadcast on {BROADCAST_IP}:{OLED_UDP_PORT}")
    print("Press Ctrl+C to stop")
    server.serve_forever()
