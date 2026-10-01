"""Find the game's real right-stick dead zone: holds the stick right at increasing
amounts, 3 s each. Note the first % where the camera starts turning and set
`deadzone` in config.toml just above it. Stop bridge.py first (it shares the port).

    .venv/bin/python probe.py [start% [end% [step%]]]     default: 4 30 2
"""
import sys, time
import serial
from bridge import find_port, frame

a = [float(x) for x in sys.argv[1:4]] + [4, 30, 2][len(sys.argv[1:4]):]
del sys.argv[1:]  # the numbers above are not a serial port
start, end, step = a
s = serial.Serial(find_port())
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
