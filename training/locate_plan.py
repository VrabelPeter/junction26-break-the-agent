"""The shell script of the camera-task training episodes (round 2): from one pixel of the head picture to a step list.

The agent runs it in its shell after robot_camera(head). It downloads the depth image and the calibration, finds
what stands on the coffee table near the named pixel (so a rough pointing is enough), and prints the steps that
sweep it into the bin: the scripted reference's way of working (sweep/policies.py: plan, fetch_tools, Bin.set_down,
gather, into_bin) for one piece of trash on the table, written out once. A value like `right_hand.x` means: take it
from the reply of the last observe.

`SRC` is the Python text, `command(u, v)` the full shell command, `run(depth, cal, u, v)` executes the same text on
a depth image here (for building and checking the training episodes), `execute(recorder, steps)` plays a printed
step list on the simulator.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile

SRC = r"""
import json, math, numpy as np
c = json.load(open('cal.json')); d = np.load('depth.npy'); u, v = U_PIX, V_PIX
TOP, X0, X1, Y0, Y1 = 0.45, -0.2, 0.8, -0.95, -0.45
vv, uu = np.mgrid[max(0, v - 80):min(480, v + 81), max(0, u - 80):min(640, u + 81)]
z = d[vv, uu]
P = np.array(c['cam_pos']) + np.stack([(uu - c['cx']) / c['f'] * z, -(vv - c['cy']) / c['f'] * z, -z], -1) @ np.array(c['cam_rot']).T
on = (P[..., 2] > TOP + 0.004) & (P[..., 2] < TOP + 0.3) & (P[..., 0] > X0) & (P[..., 0] < X1) & (P[..., 1] > Y0) & (P[..., 1] < Y1)
if on.sum() < 4:
    print('ERROR: nothing stands on the table within 80 pixels of (%d, %d)' % (u, v)); raise SystemExit
near = P.reshape(-1, 3)[np.argmin(np.where(on, (uu - u) ** 2 + (vv - v) ** 2, 1e9))]
Q = P[on]; Q = Q[np.hypot(Q[:, 0] - near[0], Q[:, 1] - near[1]) < 0.12]
x, y = (Q[:, 0].min() + Q[:, 0].max()) / 2, (Q[:, 1].min() + Q[:, 1].max()) / 2
r = min(0.06, max(0.015, max(np.ptp(Q[:, 0]), np.ptp(Q[:, 1])) / 2)); h = float(Q[:, 2].max()) - TOP
steps, base = [], [0.3, -1.835, math.pi / 2]
def S(tool, **a): steps.append(tool + ''.join(' %s=%s' % (k, w if isinstance(w, str) else round(float(w), 3)) for k, w in a.items()))
def drive(bx, by, th): S('drive_to', x=bx, y=by, heading=th); base[:] = [bx, by, th]
def zone(wy): return 'south' if wy < -1.2 else 'north' if wy > -0.1 else 'lane'
def travel(bx, by, th):
    turn = abs(math.remainder(th - base[2], 2 * math.pi))
    if turn < 0.05 and zone(base[1]) == zone(by) != 'lane': return drive(bx, by, th)
    drive(-0.95, base[1], base[2])
    if turn >= 0.05: drive(-0.95, -0.2, base[2]); drive(-0.95, -0.2, th)
    drive(-0.95, by, th); drive(bx, by, th)
def carry():
    co, si = math.cos(base[2]), math.sin(base[2]); S('observe')
    S('move_arm', arm='left', x=base[0] + co * 0.45 - si * 0.35, y=base[1] + si * 0.45 + co * 0.35, z=0.62, yaw='left_hand.yaw')
def fetch(tools):
    travel(-0.95, -0.6, math.pi); drive(-1.1, -0.6, math.pi)
    for arm, tool, hy, hz in (('left', 'brush', -0.82, 0.54), ('right', 'bin', -0.36, 0.348)):
        if tool in tools:
            S('observe')
            for dz in (0.14, 0.004, None, 0.10):
                S('move_arm', arm=arm, x=-1.62, y=hy, z=hz + dz, yaw=arm + '_hand.yaw') if dz else S('grasp', arm=arm)
    drive(-0.95, -0.6, math.pi); S('set_torso', height=0.25); carry()
def set_down(line, fwd):
    bx, by = line - fy * 0.02, e - fy * (fwd + 0.11)
    travel(bx, by - fy * 0.25, th); drive(bx, by, th); S('observe')
    S('move_arm', arm='right', x='right_hand.x', y='right_hand.y', z=0.354, yaw='right_hand.yaw'); S('release', arm='right')
    S('move_arm', arm='right', x='right_hand.x', y='right_hand.y', z=0.474, yaw='right_hand.yaw'); drive(bx, by - fy * 0.25, th)
def pull(standoff, a, b):
    bx, by = line + fy * 0.35, e - fy * standoff
    travel(bx, by - fy * 0.25, th); carry(); drive(bx, by, th); S('observe')
    hand = lambda dep: dep + standoff - 0.26
    st, en = min(hand(a), 0.65), max(hand(b), 0.36)
    for f, hz in ((st, 0.62), (st, 0.498), (en, 0.498)):
        S('move_arm', arm='left', x=line, y=e + fy * (f - standoff), z=hz, yaw='left_hand.yaw')
    if en > hand(b) + 0.005: drive(bx, by - fy * (en - hand(b)), th)
    S('observe'); S('move_arm', arm='left', x='left_hand.x', y='left_hand.y', z=0.62, yaw='left_hand.yaw'); drive(bx, by - fy * 0.25, th)
best = None
for name, e, fy in (('south', Y0, 1.0), ('north', Y1, -1.0)):
    dep = (y - e) * fy; start = dep + r + 0.048
    if best is None or (start > 0.49, round(dep, 2)) < best[0]: best = ((start > 0.49, round(dep, 2)), name, e, fy, dep, start)
_, name, e, fy, dep, start = best
th = fy * math.pi / 2; dx = 0.033 + min(r, 0.05) if h > 0.045 else 0.0; line = x + dx
deep = start > 0.29
fetch(('brush',) if deep else ('brush', 'bin'))
if deep:
    pull(max(0.42, min(0.52, 0.91 - start)), start, 0.17)
    start = max(0.02, 0.161 - min(r, 0.04)) + r + 0.048; fetch(('bin',))
set_down(line + max(-0.03, min(0.03, x - line)), 0.521 if deep else 0.52); pull(0.62, start, -0.08)
print(json.dumps(dict(u=u, v=v, x=round(float(x), 3), y=round(float(y), 3), radius=round(float(r), 3), height=round(h, 3), edge=name, gather=bool(deep), steps=len(steps))))
for i, s in enumerate(steps): print(i + 1, s)
"""

SHELL = ("curl -s http://env-server:8000/camera/head/depth.npy -o depth.npy && "
         "curl -s http://env-server:8000/camera/head/calibration.json -o cal.json && python3 -c \"")


def source(u: int, v: int) -> str:
    return SRC.replace("U_PIX", str(int(u))).replace("V_PIX", str(int(v)))


def command(u: int, v: int) -> str:
    src = source(u, v)
    assert not any(ch in src for ch in '"$`\\'), "the script must survive double quotes in a shell"
    return SHELL + src + '"'


def run(depth, cal: dict, u: int, v: int) -> str:
    """What the script prints for this depth image and calibration: the same text, executed here."""
    import numpy as np
    here = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        np.save(os.path.join(tmp, "depth.npy"), np.asarray(depth, dtype=np.float32))
        with open(os.path.join(tmp, "cal.json"), "w") as f:
            json.dump(dict(camera="head", width=640, height=480, **cal), f)
        buf = io.StringIO()
        os.chdir(tmp)
        try:
            with contextlib.redirect_stdout(buf):
                try:
                    exec(compile(source(u, v), "<locate_plan>", "exec"), {"__name__": "__main__"})
                except SystemExit:
                    pass
        finally:
            os.chdir(here)
    return buf.getvalue()


def parse(text: str):
    """(header dict, [(tool, args)]) of a printed plan; (None, []) for an error line."""
    lines = [ln for ln in text.strip().split("\n") if ln]
    if not lines or lines[0].startswith("ERROR"):
        return None, []
    head, steps = json.loads(lines[0]), []
    for ln in lines[1:]:
        parts = ln.split(" ")
        args = {}
        for p in parts[2:]:
            k, _, val = p.partition("=")
            try:
                args[k] = float(val)
            except ValueError:
                args[k] = val
        steps.append((parts[1], args))
    return head, steps


def execute(rec, steps) -> None:
    """Play a step list through a collect.Recorder: names like left_hand.x are read from the last observe reply."""
    seen = None
    for tool, args in steps:
        if tool == "observe":
            seen = rec._call("observe")
            continue
        a = {}
        for k, val in args.items():
            if isinstance(val, str) and "." in val and k != "arm":
                part, field = val.split(".")
                val = seen[part][field]
            a[k] = val
        rec._call(tool, **a)
