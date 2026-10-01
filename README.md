# Mac-to-iPhone-HID

Play iPhone games with your Mac's keyboard and mouse. An ESP32-S3 shows up on
the iPhone as an **Xbox Wireless Controller**. A small Python script on the Mac
turns key presses and mouse movement into controller input.

Built for Fortnite, which on iOS only accepts touch and game controllers.

```
Mac keyboard + mouse ──USB──▶ ESP32-S3 ──Bluetooth LE──▶ iPhone
   (bridge.py)               (pretends to be an          (sees a normal
                              Xbox Series controller)     Xbox controller)
```

- WASD → left stick, mouse → right stick (aim), keys and mouse buttons → controller buttons
- Bindings and aim settings live in a text file and reload while you play
- One hotkey (**Ctrl+Opt+Cmd+K**) switches your keyboard and mouse between the Mac and the iPhone
- No drivers and no jailbreak. The iPhone sees a standard controller.

> **Status:** tested end to end with Fortnite on an iPhone and an ESP32-S3-WROOM-1 (N8R2).

## What you need

| | |
|---|---|
| Board | An **ESP32-S3** dev board with a native USB port (often labelled `USB`, next to a `UART`/`COM` port). Other ESP32s have no native USB and won't work as-is |
| Mac | macOS with Python **3.11+** (the installer can get it through Homebrew) |
| Phone | iPhone (or iPad) that supports Xbox controllers |
| Cable | USB cable from the Mac to the board's **USB** port |

## Installation

### Quick install

Plug the ESP32-S3 into your Mac, then paste this into Terminal:

```sh
curl -fsSL https://raw.githubusercontent.com/usernameLoophole/Mac-to-iPhone-HID/main/install.sh | bash
```

The script:
1. Checks for git and Python 3.11+, and installs what's missing.
2. Clones the repo into `~/Mac-to-iPhone-HID`.
3. Creates a private Python environment containing the bridge's packages and PlatformIO.
4. Runs the self-test.
5. Offers to flash the firmware. The first build downloads ~500 MB of tools.
6. Opens the macOS permission pages you need.

Running it again is safe: it updates the folder and skips what's already done.
Set `INSTALL_DIR=/some/path` to install somewhere else.
[Read the script](install.sh) before running it if you like. It's short.

`firmware/platformio.ini` is set up for 8 MB flash modules (e.g. `…N8R2`). For a
4 MB module, delete the two `flash_size`/`partitions` lines and flash again
(command below).

### Manual install

```sh
git clone https://github.com/usernameLoophole/Mac-to-iPhone-HID.git
cd Mac-to-iPhone-HID
python3 -m venv host/.venv
host/.venv/bin/pip install -r host/requirements.txt -r firmware/requirements.txt
host/.venv/bin/python host/bridge.py --selftest     # should print "selftest ok"
host/.venv/bin/pio run -d firmware -t upload        # flash the ESP32-S3
```

### After installing (once)

1. **Permissions:** System Settings → Privacy & Security → turn on **Terminal** under
   both **Input Monitoring** and **Accessibility**. Then quit and reopen Terminal.
2. **Pairing:** iPhone → **Settings → Bluetooth** → tap **Xbox Wireless Controller**.
   Afterwards, **Settings → General → Game Controller** should appear.

## Usage

1. Plug in the board. The iPhone reconnects to it on its own.
2. In **Terminal.app** (it won't work over SSH):
   ```sh
   ~/Mac-to-iPhone-HID/start.sh
   ```
3. Press **Ctrl+Opt+Cmd+K** to send keyboard and mouse to the iPhone. Press it again to get them back.

Quit with Ctrl+C. **If you ever get stuck, unplug the board:** the script exits
and gives your keyboard and mouse back.

To check that the iPhone receives input without a game, open
<https://hardwaretester.com/gamepad> in Safari and run
`host/.venv/bin/python host/sweep.py` from the project folder.
It moves every stick and presses every button once.

## Configuration

Everything is in [`host/config.toml`](host/config.toml). Saved changes apply within a second.

**Default bindings**

| Mac | Controller |
|---|---|
| W A S D | Left stick |
| Mouse movement | Right stick |
| Left / right click | RT (fire) / LT (aim) |
| Wheel up / down | LB / RB |
| Space · R/E · Q | A · X · Y |
| C · F · middle click | RS click (crouch) |
| Shift | LS click (sprint) |
| Tab · Esc | View · Menu |
| 1 2 3 4 | D-pad ↑ → ↓ ← |

Change them to match your in-game controller layout. Controller targets you can
use: `A B X Y LB RB LS RS View Menu Share LT RT DU DD DL DR LS_UP LS_DOWN LS_LEFT LS_RIGHT`.

## Aim settings

A mouse reports how far it moved, while a stick sets how fast you turn. Every
8 ms, `bridge.py` measures how fast the mouse is moving and turns that into a
right-stick position. These settings under `[aim]` in
[`host/config.toml`](host/config.toml) shape that conversion. Saved changes
apply live.

| Setting | Default | What it does |
|---|---|---|
| `full_speed` | `1800` | Mouse speed (counts per second) that pushes the stick all the way. **Lower = more sensitive.** The main sensitivity knob |
| `deadzone` | `0.33` | Where the stick starts as soon as the mouse moves. It must sit just **above the game's real dead zone**, or slow moves do nothing. On Fortnite iOS that's ~32%, even with the in-game setting at 5% |
| `gamma` | `1.2` | Shape of the curve between `deadzone` and full stick. **Above 1:** slow moves stay gentle (fine aim). **Below 1:** slow moves ramp up quickly |
| `window_ms` | `40` | How much mouse history is averaged. **Higher:** smoother, no stutter on slow moves, slightly more lag. **Lower:** snappier but can stutter |
| `y_ratio` | `1.0` | Vertical sensitivity relative to horizontal |

**What to change when…**

| You notice | Change |
|---|---|
| Everything too slow / too fast | Lower / raise `full_speed` |
| Slow, small moves don't turn the camera | Raise `deadzone` by 0.01–0.02 |
| Small moves jump too far | Raise `gamma` (1.3–1.5) |
| Camera stutters on slow moves | Raise `window_ms` (50–60) |
| Aim feels laggy or floaty | Lower `window_ms` (30) |
| Up/down too fast compared to left/right | Lower `y_ratio` (e.g. 0.8) |

**The game sets a floor.** The slowest possible turn is the game's turn speed
just past its dead zone, and no setting here can go below it. For even finer
aim, lower the game's look speed (see below) and then lower `full_speed` to
win back fast turns.

**Measuring a game's real dead zone:** stop `bridge.py` and run
`host/.venv/bin/python host/probe.py 4 40 2`. It holds the right stick at 4, 6, … 40%,
3 s each. Set `deadzone` about 0.01–0.02 above the first value that turns the camera.

**Calibrating** in Fortnite Creative:
1. Adjust `full_speed` until a fixed mouse swipe gives about a 360° turn.
2. Adjust `gamma` until small corrections feel right.
3. Adjust `window_ms` until slow moves are smooth.

## Fortnite settings

Recommended in-game settings to pair with the script. They're under
**Settings → Controller**, mostly in the sensitivity section, with
**Use Advanced Options** turned on.

| Setting | Value | Why |
|---|---|---|
| Look Horizontal / Vertical Speed | High (80–100%) | The game sets the **fastest** turn and the script can't exceed it, so give it room. Lower it only for finer slow aim (see above) |
| ADS Look Horizontal / Vertical Speed | High | Same, while aiming down sights |
| Look Dead Zone | Minimum (5%) | Less dead zone for `deadzone` to jump over |
| Look Input Curve | **Linear** | The exponential curve squashes small stick values, which kills fine aim |
| Turning Boost (Horizontal / Vertical) | Off (0) | Boost speeds up the turn when the stick stays near full, so the same mouse move turns by different amounts |
| Turning Boost Ramp Time / Delay | 0 | Same reason |
| Aim Assist | Your choice | It slows the camera near targets. Turn it off while calibrating, then try both |
| Auto Sprint (Settings → Game → Movement) | **Off** | Otherwise you're always sprinting and Shift (sprint = LS click) can't control it. Also turn off *Sprint by Default* if your version has it |

Match the button layout to [`host/config.toml`](host/config.toml), or the other way round.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Event tap failed` | Grant Terminal **Input Monitoring + Accessibility**, then restart Terminal |
| `ESP32 not found` | Use the board's **USB** port, not UART. Check with `ls /dev/cu.usbmodem*` |
| Game Center overlay keeps popping up | Something is pressing the **Xbox/Guide** button. Don't bind `Guide` |
| iPhone doesn't reconnect | Settings → Bluetooth → tap the controller. If that fails: *Forget This Device*, then pair again |
| Mouse wheel switches weapons the wrong way | macOS *natural scrolling* flips the wheel. Swap `wheel_up` / `wheel_down` in `config.toml` |
| `config error: …` in the terminal | Typo in `config.toml`. The message names the line. The previous config stays active until you fix it |
| Pressing a controller button does nothing in Fortnite | Compare `config.toml` with Fortnite's controller layout |

## How it works

- **`host/bridge.py`** captures keyboard and mouse with a macOS event tap. While
  forwarding is on, it hides them from the Mac and freezes the cursor. Every 8 ms
  it sends the **whole controller state** as one 15-byte message over USB serial.
- **`firmware/`** (ESP32-S3) reads those messages and sends them to the iPhone
  as a Bluetooth controller. It uses the Xbox Series X mode of
  [ESP32-BLE-Gamepad](https://github.com/lemmingDev/ESP32-BLE-Gamepad). If
  messages stop for 200 ms, it returns every input to neutral, so nothing gets
  stuck when the Mac side dies.

### Serial protocol (Mac → ESP32)

One 15-byte message per 8 ms, little-endian, always carrying the whole controller state:

| Byte | Field |
|---|---|
| 0 | sync `0xA5` |
| 1–2 | buttons: bits 0–10 = A, B, X, Y, LB, RB, LS, RS, View, Menu, Guide · bit 11 = Share |
| 3 | D-pad: 0 = centre, 1–8 = N, NE, E, … NW |
| 4–11 | left X, left Y, right X, right Y (`int16`, +Y = down) |
| 12–13 | LT, RT (`uint8`) |
| 14 | XOR of bytes 1–13 |

### Mouse → right stick

Every 8 ms, the mouse movement from the last `window_ms` becomes a speed. Speed
divided by `full_speed` gives a value `m`. The stick is pushed in the same
direction as the movement by `deadzone + (1 − deadzone) · min(1, m)^gamma`.
X and Y are scaled together, so diagonal aim keeps its angle. No movement →
the stick returns to centre.

While the stick is off centre, its value is nudged by 1 (out of 32767) on every
other frame. iOS/Fortnite ignore a right stick that holds perfectly still, so
every update has to carry a slightly different value.

```
install.sh                  one-line installer
start.sh                    starts the bridge
firmware/
  platformio.ini            pinned toolchain + dependencies
  requirements.txt          PlatformIO itself (installed into host/.venv)
  src/main.cpp              USB-serial → controller bridge
  lib/ESP32-BLE-Gamepad/    vendored library (MIT), unmodified
host/
  bridge.py                 Mac capture, bindings, aim
  config.toml               your bindings and aim settings
  requirements.txt          pinned Python packages
  sweep.py                  hardware test: exercises every input
  probe.py                  measures the game's real right-stick dead zone
```

## Fair play

This only remaps your own keyboard and mouse to controller input. It has no
macros, no automation and no recoil compensation, and none will be added.
Using adapters like this may still go against a game's terms of service.
Use at your own risk.

## Credits

- [lemmingDev/ESP32-BLE-Gamepad](https://github.com/lemmingDev/ESP32-BLE-Gamepad) (MIT): BLE gamepad and Xbox emulation, vendored in `firmware/lib/`
- [h2zero/NimBLE-Arduino](https://github.com/h2zero/NimBLE-Arduino): Bluetooth LE stack

## License

[MIT](LICENSE)
