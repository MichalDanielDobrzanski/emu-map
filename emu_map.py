#!/usr/bin/env python3
"""
emu_map.py - click a map in your browser, the Android emulator moves there.

Usage:
    python3 emu_map.py                 # opens http://127.0.0.1:8765
    python3 emu_map.py --port 9000
    python3 emu_map.py --serial emulator-5556

Needs only Python 3.7+ and adb (found on PATH, via $ADB, or $ANDROID_HOME).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

EXE = ".exe" if os.name == "nt" else ""


def find_adb():
    if os.environ.get("ADB"):
        return os.environ["ADB"]
    found = shutil.which("adb")
    if found:
        return found
    roots = [os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
             os.path.expanduser("~/Library/Android/sdk"),   # macOS default
             os.path.expanduser("~/Android/Sdk"),           # Linux default
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk")]  # Windows
    for root in filter(None, roots):
        cand = os.path.join(root, "platform-tools", "adb" + EXE)
        if os.path.exists(cand):
            return cand
    sys.exit("adb not found. Add platform-tools to PATH or set ADB=/path/to/adb")


def list_emulators(adb):
    try:
        out = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return []
    devices = []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[0].startswith("emulator-") and parts[1] == "device":
            devices.append(parts[0])
    return devices


def geo_fix(adb, serial, lat, lng):
    cmd = [adb] + (["-s", serial] if serial else [])
    # NOTE: geo fix takes LONGITUDE first, then latitude
    cmd += ["emu", "geo", "fix", f"{lng:.6f}", f"{lat:.6f}"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    output = (r.stdout + r.stderr).strip()
    return r.returncode == 0 and "KO" not in output, output


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Emulator location</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<style>
  :root { --bg:#ffffff; --fg:#1b2430; --muted:#5f6b7a; --line:#d9dee5;
          --accent:#1d5d8f; --ok:#1f7a4a; --bad:#b3261e; --chip:#eef3f8; }
  @media (prefers-color-scheme: dark) {
    :root { color-scheme: dark; --bg:#161b22; --fg:#e6edf3; --muted:#9aa7b4; --line:#2e3742;
            --accent:#6cb2e8; --ok:#4fc483; --bad:#ff7b72; --chip:#212a35; }
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body { display: grid; grid-template-columns: 280px 1fr; background: var(--bg); color: var(--fg);
         font: 14px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  aside { padding: 16px; border-right: 1px solid var(--line); overflow-y: auto; display: flex;
          flex-direction: column; gap: 18px; }
  h1 { font-size: 16px; margin: 0; }
  h2 { font-size: 13px; margin: 0 0 6px; color: var(--muted); font-weight: 600; }
  #map { height: 100%; }
  select, input[type=number] { width: 100%; padding: 6px 8px; border: 1px solid var(--line);
          border-radius: 6px; background: var(--bg); color: var(--fg); font: inherit; }
  button { padding: 6px 10px; border: 1px solid var(--line); border-radius: 6px; background: var(--chip);
           color: var(--fg); font: inherit; cursor: pointer; }
  button:hover { border-color: var(--accent); }
  button:focus-visible, select:focus-visible, input:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
  button.on { background: var(--accent); color: var(--bg); border-color: var(--accent); }
  .row { display: flex; gap: 6px; flex-wrap: wrap; }
  .row > button { flex: 1; }
  .presets button { flex: 1 1 45%; text-align: left; }
  #status { padding: 8px 10px; border-radius: 6px; background: var(--chip); font-variant-numeric: tabular-nums; }
  #status.ok { color: var(--ok); } #status.bad { color: var(--bad); }
  .hint { color: var(--muted); font-size: 12px; margin: 6px 0 0; }
  label.inline { display: flex; align-items: center; gap: 6px; }
  @media (max-width: 700px) { body { grid-template-columns: 1fr; grid-template-rows: auto 60vh; } }
</style>
</head>
<body>
<aside>
  <h1>Emulator location</h1>

  <div>
    <h2>Emulator</h2>
    <div class="row">
      <select id="device" style="flex:1"></select>
      <button id="refresh" title="Refresh device list">↻</button>
    </div>
  </div>

  <div>
    <h2>Click on the map to</h2>
    <div class="row">
      <button id="modeTeleport" class="on">Teleport</button>
      <button id="modeRoute">Draw route</button>
    </div>
    <p class="hint" id="modeHint">Each click moves the emulator. You can also drag the pin.</p>
  </div>

  <div id="routeBox" hidden>
    <h2>Route</h2>
    <label>Speed (km/h)<input id="speed" type="number" min="1" max="200" value="18"></label>
    <label class="inline" style="margin-top:6px"><input id="loop" type="checkbox"> Loop</label>
    <div class="row" style="margin-top:8px">
      <button id="play">Play</button>
      <button id="undo">Undo point</button>
      <button id="clear">Clear</button>
    </div>
    <p class="hint" id="routeInfo">No points yet.</p>
  </div>

  <div>
    <h2>Amsterdam</h2>
    <div class="row presets" id="presets"></div>
  </div>

  <div id="status">Click the map to set a location.</div>
</aside>
<div id="map"></div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<script>
const $ = id => document.getElementById(id);
const START = [52.3731, 4.8926];
const PRESETS = [
  ["Dam Square", 52.3731, 4.8926], ["Centraal", 52.3791, 4.9003],
  ["Vondelpark", 52.3580, 4.8686], ["Zuidas", 52.3383, 4.8730],
  ["NDSM (Noord)", 52.4010, 4.8930], ["Amstel station", 52.3467, 4.9178],
  ["Schiphol", 52.3105, 4.7683], ["Sloterdijk", 52.3889, 4.8378],
];
const TICK_MS = 1000;

const map = L.map("map").setView(START, 14);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  { maxZoom: 19, attribution: "© OpenStreetMap contributors" }).addTo(map);
const pin = L.marker(START, { draggable: true }).addTo(map);
const routeLine = L.polyline([], { weight: 4, color: "#1d5d8f" }).addTo(map);
let route = [], dots = [], mode = "teleport", timer = null;

function status(text, ok) {
  const s = $("status"); s.textContent = text;
  s.className = ok === undefined ? "" : ok ? "ok" : "bad";
}

async function send(lat, lng) {
  pin.setLatLng([lat, lng]);
  try {
    const r = await fetch("/api/location", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lat, lng, serial: $("device").value || null }) });
    const j = await r.json();
    status(j.ok ? `Sent ${lat.toFixed(5)}, ${lng.toFixed(5)}` : `Not sent: ${j.error || j.output || "unknown error"}`, j.ok);
  } catch (e) { status("Not sent: the emu_map.py server isn't running.", false); }
}

async function loadDevices() {
  const sel = $("device");
  try {
    const j = await (await fetch("/api/devices")).json();
    sel.innerHTML = "";
    if (!j.devices.length) { sel.add(new Option("No running emulator found", "")); return; }
    j.devices.forEach(d => sel.add(new Option(d, d)));
    if (j.default && j.devices.includes(j.default)) sel.value = j.default;
  } catch (e) { sel.innerHTML = ""; sel.add(new Option("Server not reachable", "")); }
}

function setMode(m) {
  mode = m;
  $("modeTeleport").classList.toggle("on", m === "teleport");
  $("modeRoute").classList.toggle("on", m === "route");
  $("routeBox").hidden = m !== "route";
  $("modeHint").textContent = m === "teleport"
    ? "Each click moves the emulator. You can also drag the pin."
    : "Each click adds a point. Press Play to drive along it.";
}

function routeLength() {
  let d = 0; for (let i = 1; i < route.length; i++) d += route[i - 1].distanceTo(route[i]); return d;
}
function redrawRoute() {
  routeLine.setLatLngs(route);
  dots.forEach(d => map.removeLayer(d));
  dots = route.map(p => L.circleMarker(p, { radius: 4, weight: 2 }).addTo(map));
  $("routeInfo").textContent = route.length
    ? `${route.length} points, ${(routeLength() / 1000).toFixed(2)} km` : "No points yet.";
}

function stopRoute() { clearInterval(timer); timer = null; $("play").textContent = "Play"; }
function startRoute() {
  if (route.length < 2) { status("Add at least two points to play a route.", false); return; }
  let seg = 0, along = 0;
  send(route[0].lat, route[0].lng);
  $("play").textContent = "Pause";
  timer = setInterval(() => {
    let step = Math.max(0.1, parseFloat($("speed").value) || 18) / 3.6 * TICK_MS / 1000;
    while (step > 0) {
      const len = route[seg].distanceTo(route[seg + 1]);
      if (along + step < len) { along += step; step = 0; }
      else {
        step -= len - along; along = 0; seg++;
        if (seg >= route.length - 1) {
          if ($("loop").checked) { seg = 0; step = 0; }
          else { const e = route[route.length - 1]; send(e.lat, e.lng); stopRoute(); return; }
        }
      }
    }
    const a = route[seg], b = route[seg + 1], len = a.distanceTo(b), f = len ? along / len : 0;
    send(a.lat + (b.lat - a.lat) * f, a.lng + (b.lng - a.lng) * f);
  }, TICK_MS);
}

map.on("click", e => {
  if (mode === "teleport") send(e.latlng.lat, e.latlng.lng);
  else { route.push(e.latlng); redrawRoute(); }
});
pin.on("dragend", () => { const p = pin.getLatLng(); send(p.lat, p.lng); });
$("modeTeleport").onclick = () => { stopRoute(); setMode("teleport"); };
$("modeRoute").onclick = () => setMode("route");
$("play").onclick = () => timer ? stopRoute() : startRoute();
$("undo").onclick = () => { route.pop(); redrawRoute(); };
$("clear").onclick = () => { stopRoute(); route = []; redrawRoute(); };
$("refresh").onclick = loadDevices;

PRESETS.forEach(([name, lat, lng]) => {
  const b = document.createElement("button"); b.textContent = name;
  b.onclick = () => { map.setView([lat, lng], 15); if (mode === "teleport") send(lat, lng); };
  $("presets").appendChild(b);
});

loadDevices();
</script>
</body>
</html>
"""


def make_handler(adb, default_serial):
    class Handler(BaseHTTPRequestHandler):
        def _json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/api/devices":
                self._json(200, {"devices": list_emulators(adb), "default": default_serial})
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path != "/api/location":
                return self.send_error(404)
            try:
                data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                lat, lng = float(data["lat"]), float(data["lng"])
                if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                    raise ValueError("coordinates out of range")
                serial = data.get("serial") or default_serial
                if serial and not serial.startswith("emulator-"):
                    raise ValueError("serial must look like emulator-5554")
            except Exception as e:
                return self._json(400, {"ok": False, "error": str(e)})
            try:
                ok, output = geo_fix(adb, serial, lat, lng)
            except Exception as e:
                return self._json(500, {"ok": False, "error": str(e)})
            print(f"{'OK ' if ok else 'ERR'} {lat:.6f}, {lng:.6f}  {serial or ''} {output}")
            self._json(200, {"ok": ok, "output": output})

        def log_message(self, *args):
            pass  # keep the console quiet; geo fixes are printed above

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Map window that sets the Android emulator's GPS location.")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--serial", help="emulator to target, e.g. emulator-5554 (default: first one found)")
    ap.add_argument("--no-browser", action="store_true", help="don't open the browser automatically")
    args = ap.parse_args()

    adb = find_adb()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(adb, args.serial))
    url = f"http://127.0.0.1:{args.port}"
    print(f"adb: {adb}\nMap: {url}   (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
