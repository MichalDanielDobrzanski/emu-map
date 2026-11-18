# emu-map

Click on a map, and your Android emulator is there. Instantly.

The emulator's built-in Location panel makes you pick a point and then press
*Set location*, or play back a recorded route. `emu-map` gives you a map in a
browser window next to the emulator: every click moves the device's GPS right away.

## Features

- **One-click teleport.** Click anywhere on the map, or drag the pin.
- **Draw a route and drive it.** Click points along streets, set a speed
  (km/h), press Play. The emulator moves along the route with one update per second,
  optionally on a loop.
- **Presets** for Amsterdam (Dam, Centraal, Vondelpark, Zuidas, NDSM, Schiphol…).
  Edit the `PRESETS` list in the script to add your own.
- **Multiple emulators.** Choose the target from a dropdown.
- **No dependencies.** Python 3.7+ standard library and `adb`. That's it.

## Usage

```bash
# 1. Start an emulator (Android Studio or `emulator -avd <name>`)
# 2. Run:
python3 emu_map.py
```

The map opens at <http://127.0.0.1:8765>. Put the window next to the emulator and click.

Options:

```bash
python3 emu_map.py --port 9000              # different port
python3 emu_map.py --serial emulator-5556   # target a specific emulator
python3 emu_map.py --no-browser             # don't open the browser automatically
```

### Finding adb

The script looks for `adb` in this order: the `ADB` environment variable, your `PATH`,
`$ANDROID_HOME` / `$ANDROID_SDK_ROOT`, and then the default SDK folders
(`~/Library/Android/sdk` on macOS, `~/Android/Sdk` on Linux, `%LOCALAPPDATA%\Android\Sdk` on Windows).

```bash
ADB=/custom/path/to/adb python3 emu_map.py
```

## How it works

A tiny local HTTP server (bound to `127.0.0.1` only) serves a Leaflet + OpenStreetMap
page. Each click sends the coordinates to the server, which runs:

```bash
adb -s emulator-5554 emu geo fix <longitude> <latitude>
```

(`geo fix` takes **longitude first**.)

## Tips

- If your app uses the fused location provider and doesn't react to the first update,
  open Google Maps in the emulator once to refresh the last known location.
- Map tiles load from OpenStreetMap, so the browser needs internet access.
- Works with emulators only. Physical devices need a mock-location app instead.

## License

MIT
