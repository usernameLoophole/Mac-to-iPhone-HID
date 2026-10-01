"""Hardware check: sweeps sticks/triggers and presses each button once (never Guide/Share).
Watch https://hardwaretester.com/gamepad on the iPhone. Stop bridge.py first (it shares the port)."""
import math, time
import serial
from bridge import find_port, frame

NAMES = ["A", "B", "X", "Y", "LB", "RB", "LS", "RS", "View", "Menu"]  # bits 0..9

s = serial.Serial(find_port())
print("tap A (browsers only expose a gamepad after a button press)")
for b in (1, 0, 1, 0):
    for _ in range(25):
        s.write(frame(buttons=b)); time.sleep(0.008)
time.sleep(2)
t0 = time.time()
print("sticks + triggers, 6s")
while time.time() - t0 < 6:
    a = (time.time() - t0) * 2
    v = int(30000 * math.sin(a)), int(30000 * math.cos(a))
    trig = int(127 + 127 * math.sin(a))
    s.write(frame(lx=v[0], ly=v[1], rx=v[1], ry=v[0], lt=trig, rt=255 - trig))
    time.sleep(0.008)
for hat in range(1, 9):
    print("hat", hat)
    for _ in range(40):
        s.write(frame(hat=hat)); time.sleep(0.008)
for i, name in enumerate(NAMES):
    print("button", name)
    for _ in range(40):
        s.write(frame(buttons=1 << i)); time.sleep(0.008)
    for _ in range(40):
        s.write(frame()); time.sleep(0.008)
s.write(frame())
print("done")
