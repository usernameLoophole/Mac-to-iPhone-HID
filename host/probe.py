"""Find the game's real right-stick dead zone: holds the stick right at increasing
amounts, 3 s each. Note the first % where the camera starts turning and set
`deadzone` in config.toml just above it. Stop bridge.py first (it shares the port).

    .venv/bin/python probe.py [start% [end% [step%]]]     default: 4 30 2
"""
import glob, sys, time
import serial
from bridge import frame

a = [float(x) for x in sys.argv[1:4]] + [4, 30, 2][len(sys.argv[1:4]):]
start, end, step = a
ports = glob.glob("/dev/cu.usbmodem*")
if not ports:
    sys.exit("ESP32 not found: plug it into the board's USB port.")
s = serial.Serial(ports[0])
for b in (1, 0):  # tap A so the controller is active
    for _ in range(25):
        s.write(frame(buttons=b)); time.sleep(0.008)
print("Starting in 3 s: look at the camera in game.")
time.sleep(3)
p, j = start, 0
while p <= end + 1e-9:
    print(f"right stick {p:4.0f}%", flush=True)
    t = time.time()
    while time.time() - t < 3:
        j = 1 - j  # 1-LSB wiggle so every frame is a new BLE report
        s.write(frame(rx=round(p / 100 * 32767) - j)); time.sleep(0.008)
    for _ in range(60):  # 0.5 s neutral between steps
        s.write(frame()); time.sleep(0.008)
    p += step
s.write(frame())
print("done")
