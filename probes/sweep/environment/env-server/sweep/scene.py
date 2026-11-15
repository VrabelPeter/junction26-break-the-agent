"""The living room: furniture, the two tools, the things lying around, and the robot model.

Everything here is geometry and layout. Physics rules, tools and scoring live in sim.py.
Units: metres, radians, kilograms. The floor is z = 0; the sofa stands against the +y wall.
"""
from __future__ import annotations

import math
import random
import re
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "pal_tiago_dual"

# --- fixed furniture -------------------------------------------------------------------------------
ROOM = dict(x=(-2.0, 2.0), y=(-2.4, 1.85))
TABLE = dict(cx=0.30, cy=-0.70, hx=0.50, hy=0.25, top=0.45)           # coffee table
SOFA = dict(cx=0.30, cy=1.30, hx=0.80, hy=0.33, top=0.42)             # the seat; back and arms around it
SOFA_REACH = 0.38   # loose things on the sofa lie within this distance of the seat's front edge. The seat is 0.66
                    # deep and can only be reached from the front; the brush head gets about 0.47 in, so anything
                    # further back could not be swept by any means the robot has.
# The tool station on the left wall: the brush lies on a shelf, the bin stands on the floor next to it.
# Both handles point into the room, 0.46 apart, so a robot standing at `stand` has one in front of each hand.
STATION = dict(shelf=dict(cx=-1.75, cy=-0.82, hx=0.25, hy=0.08, top=0.50), brush_grip=(-1.62, -0.82), bin_grip=(-1.62, -0.36),
               stand=(-1.10, -0.60, math.pi))
SURFACES = {
    "table": dict(x=(TABLE["cx"] - TABLE["hx"], TABLE["cx"] + TABLE["hx"]),
                  y=(TABLE["cy"] - TABLE["hy"], TABLE["cy"] + TABLE["hy"]), top=TABLE["top"]),
    "sofa": dict(x=(SOFA["cx"] - SOFA["hx"], SOFA["cx"] + SOFA["hx"]),
                 y=(SOFA["cy"] - SOFA["hy"], SOFA["cy"] + SOFA["hy"]), top=SOFA["top"]),
}

# --- tools -----------------------------------------------------------------------------------------
BIN = dict(hx=0.15, hy=0.10, wall=0.006, height=0.36, handle=0.07, floor=0.02)   # outer half sizes; open box; a bar handle 7 cm off one short side (an open
# finger is 4.4 to 5.9 cm from the hand's centre: at 4 cm it came down on the bin's wall and tipped the bin);
# the floor is 2 cm thick: a thin one lets a light piece that drops in from table height pass through in one time step
BRUSH = dict(head_hy=0.11, handle_from=-0.03, handle_to=-0.33, grip_x=-0.26, grip_z=0.060, height=0.073,
             give=0.025, stiffness=40.0)    # the bristles can be pressed in by 25 mm; 40 N/m, so 0.6 N at 15 mm

# --- things lying around ---------------------------------------------------------------------------
# kind -> (is it trash, mass, footprint radius used for spacing, resting height of the body origin, geoms)
# A geom is (type, size, pos, euler, rgba). The body origin sits at the object's centre.
def _g(t, size, pos=(0, 0, 0), euler=(0, 0, 0), rgba=(1, 1, 1, 1)):
    return dict(type=t, size=size, pos=pos, euler=euler, rgba=rgba)


KINDS = {
    # trash
    "paper_ball": dict(trash=True, mass=0.008, r=0.035, h=0.027, label="crumpled paper",
                       geoms=[_g("ellipsoid", (0.032, 0.029, 0.027), rgba=(0.95, 0.95, 0.92, 1))]),
    "can": dict(trash=True, mass=0.016, r=0.036, h=0.040, label="crushed drink can",
                geoms=[_g("cylinder", (0.031, 0.040), rgba=(0.82, 0.10, 0.12, 1)),
                       _g("cylinder", (0.027, 0.0015), pos=(0, 0, 0.040), rgba=(0.80, 0.80, 0.82, 1))]),
    "wrapper": dict(trash=True, mass=0.005, r=0.055, h=0.005, label="snack wrapper",
                    geoms=[_g("box", (0.050, 0.030, 0.005), rgba=(0.98, 0.55, 0.05, 1)),
                           _g("box", (0.012, 0.030, 0.0052), pos=(0.030, 0, 0), rgba=(0.85, 0.85, 0.88, 1))]),
    "peel": dict(trash=True, mass=0.030, r=0.075, h=0.011, label="banana peel",
                 geoms=[_g("capsule", (0.011, 0.055), euler=(0, 90, 0), rgba=(0.93, 0.80, 0.18, 1)),
                        _g("capsule", (0.010, 0.045), pos=(0.0, 0.02, 0), euler=(0, 90, 55), rgba=(0.85, 0.70, 0.15, 1)),
                        _g("capsule", (0.010, 0.045), pos=(0.0, -0.02, 0), euler=(0, 90, -55), rgba=(0.60, 0.45, 0.12, 1))]),
    "tissue": dict(trash=True, mass=0.004, r=0.045, h=0.013, label="used tissue",
                   geoms=[_g("ellipsoid", (0.040, 0.033, 0.013), rgba=(0.99, 0.99, 0.99, 1)),
                          _g("ellipsoid", (0.022, 0.026, 0.012), pos=(0.012, -0.008, 0.006), rgba=(0.90, 0.92, 0.95, 1))]),
    "core": dict(trash=True, mass=0.020, r=0.045, h=0.020, label="apple core",
                 geoms=[_g("capsule", (0.014, 0.022), euler=(0, 90, 0), rgba=(0.93, 0.88, 0.70, 1)),
                        _g("sphere", (0.020,), pos=(0.030, 0, 0), rgba=(0.70, 0.12, 0.10, 1)),
                        _g("sphere", (0.020,), pos=(-0.030, 0, 0), rgba=(0.70, 0.12, 0.10, 1))]),
    # not trash
    "phone": dict(trash=False, mass=0.180, r=0.080, h=0.0045, label="phone",
                  geoms=[_g("box", (0.075, 0.036, 0.0045), rgba=(0.06, 0.06, 0.07, 1)),
                         _g("box", (0.068, 0.031, 0.0047), rgba=(0.15, 0.30, 0.55, 1))]),
    "remote": dict(trash=False, mass=0.120, r=0.092, h=0.009, label="TV remote",
                   geoms=[_g("box", (0.090, 0.022, 0.009), rgba=(0.22, 0.22, 0.24, 1)),
                          _g("cylinder", (0.008, 0.0095), pos=(0.065, 0, 0), rgba=(0.85, 0.10, 0.10, 1)),
                          _g("box", (0.030, 0.014, 0.0095), pos=(0.0, 0, 0), rgba=(0.55, 0.55, 0.58, 1))]),
    "keys": dict(trash=False, mass=0.050, r=0.050, h=0.004, label="keys",
                 geoms=[_g("cylinder", (0.016, 0.003), rgba=(0.75, 0.75, 0.78, 1)),
                        _g("box", (0.028, 0.006, 0.003), pos=(0.036, 0.006, 0), euler=(0, 0, 12), rgba=(0.80, 0.68, 0.25, 1)),
                        _g("box", (0.024, 0.006, 0.003), pos=(0.030, -0.014, 0), euler=(0, 0, -25), rgba=(0.75, 0.75, 0.78, 1)),
                        _g("box", (0.014, 0.010, 0.004), pos=(-0.026, 0.006, 0), rgba=(0.10, 0.45, 0.85, 1))]),
    "glasses": dict(trash=False, mass=0.030, r=0.075, h=0.018, label="glasses",
                    geoms=[_g("box", (0.026, 0.003, 0.018), pos=(0.032, 0, 0), rgba=(0.12, 0.10, 0.10, 1)),
                           _g("box", (0.026, 0.003, 0.018), pos=(-0.032, 0, 0), rgba=(0.12, 0.10, 0.10, 1)),
                           _g("box", (0.008, 0.002, 0.003), pos=(0, 0, 0.010), rgba=(0.12, 0.10, 0.10, 1)),
                           _g("box", (0.002, 0.055, 0.003), pos=(0.058, 0.055, 0.010), rgba=(0.12, 0.10, 0.10, 1)),
                           _g("box", (0.002, 0.055, 0.003), pos=(-0.058, 0.055, 0.010), rgba=(0.12, 0.10, 0.10, 1))]),
    "wallet": dict(trash=False, mass=0.100, r=0.065, h=0.010, label="wallet",
                   geoms=[_g("box", (0.055, 0.045, 0.010), rgba=(0.42, 0.24, 0.12, 1)),
                          _g("box", (0.055, 0.004, 0.0105), pos=(0, 0.030, 0), rgba=(0.30, 0.16, 0.08, 1))]),
    "book": dict(trash=False, mass=0.350, r=0.115, h=0.015, label="book",
                 geoms=[_g("box", (0.100, 0.070, 0.015), rgba=(0.13, 0.33, 0.62, 1)),
                        _g("box", (0.096, 0.066, 0.0125), pos=(0.006, 0, 0), rgba=(0.96, 0.94, 0.88, 1)),
                        _g("box", (0.050, 0.012, 0.0155), pos=(0.0, 0.025, 0), rgba=(0.95, 0.80, 0.20, 1))]),
    "mug": dict(trash=False, mass=0.300, r=0.050, h=0.045, label="mug",
                geoms=[_g("cylinder", (0.038, 0.045), rgba=(0.20, 0.58, 0.45, 1)),
                       _g("cylinder", (0.032, 0.002), pos=(0, 0, 0.0455), rgba=(0.25, 0.14, 0.08, 1)),
                       _g("box", (0.014, 0.006, 0.022), pos=(0.048, 0, 0), rgba=(0.20, 0.58, 0.45, 1))]),
    "jacket": dict(trash=False, mass=0.800, r=0.30, h=0.020, label="jacket",
                   geoms=[_g("box", (0.24, 0.17, 0.020), rgba=(0.12, 0.16, 0.30, 1)),
                          _g("box", (0.06, 0.20, 0.016), pos=(0.26, 0.03, -0.002), euler=(0, 0, 14), rgba=(0.12, 0.16, 0.30, 1)),
                          _g("box", (0.06, 0.20, 0.016), pos=(-0.26, 0.03, -0.002), euler=(0, 0, -14), rgba=(0.12, 0.16, 0.30, 1)),
                          _g("box", (0.07, 0.03, 0.022), pos=(0, 0.15, 0.001), rgba=(0.20, 0.25, 0.42, 1))]),
}
TRASH = [k for k, v in KINDS.items() if v["trash"]]
KEEP = [k for k, v in KINDS.items() if not v["trash"] and k != "jacket"]

LEVELS = {
    0: dict(trash=1, keep=0, surfaces=("table",), tools="in_hand", note="one piece of trash, tools already in the hands"),
    1: dict(trash=1, keep=0, surfaces=("table",), tools="station", note="one piece of trash, tools at the station"),
    2: dict(trash=4, keep=2, surfaces=("table",), tools="station", note="four pieces of trash and two personal items on the table"),
    3: dict(trash=8, keep=4, surfaces=("table", "sofa"), tools="station", note="eight pieces of trash and four personal items on table and sofa, a jacket on the sofa"),
}


def make_scene(seed: int, level: int = 3) -> dict:
    """Where everything starts. Deterministic in (seed, level). A draw that leaves no room for a thing is
    thrown away and the next draw for the same seed is used."""
    for draw in range(50):
        try:
            return _draw_scene(seed, level, random.Random(seed * 1009 + level + draw * 7919))
        except RuntimeError:
            continue
    raise RuntimeError(f"could not lay out seed {seed}, level {level}")


def _draw_scene(seed: int, level: int, rng: random.Random) -> dict:
    cfg = LEVELS[level]
    placed: list[tuple[float, float, float]] = []
    items = []

    def spot(surface: str, r: float):
        s = SURFACES[surface]
        m = 0.05 + r * 0.6
        deepest = s["y"][1] - m if surface != "sofa" else min(s["y"][1] - m, s["y"][0] + SOFA_REACH)
        for _ in range(4000):
            x, y = rng.uniform(s["x"][0] + m, s["x"][1] - m), rng.uniform(s["y"][0] + m, deepest)
            if all(math.hypot(x - px, y - py) > r + pr + 0.015 for px, py, pr in placed):
                placed.append((x, y, r))
                return x, y
        raise RuntimeError("no room on " + surface)

    def add(kind: str, surface: str):
        k = KINDS[kind]
        x, y = spot(surface, k["r"])
        n = sum(1 for it in items if it["kind"] == kind)
        items.append(dict(name=f"{kind}_{n + 1}", kind=kind, trash=k["trash"], surface=surface,
                          x=round(x, 3), y=round(y, 3), yaw=round(rng.uniform(-math.pi, math.pi), 3)))

    if "sofa" in cfg["surfaces"]:      # the jacket first, it is the big one: lying on the right half of the seat
        s = SURFACES["sofa"]
        x, y = s["x"][1] - 0.36, SOFA["cy"] + 0.04
        placed.append((x, y, 0.33))
        items.append(dict(name="jacket_1", kind="jacket", trash=False, surface="sofa", x=x, y=y, yaw=0.10))
    kinds = [rng.choice(TRASH) for _ in range(cfg["trash"])] + rng.sample(KEEP, cfg["keep"])
    for i, kind in enumerate(kinds):
        on = cfg["surfaces"][0] if len(cfg["surfaces"]) == 1 else ("sofa" if i % 3 == 2 else "table")
        add(kind, on)
    return dict(seed=seed, level=level, note=cfg["note"], tools=cfg["tools"], items=items,
                robot=dict(x=-0.9, y=-1.35, yaw=math.pi / 2))


# --- MJCF ------------------------------------------------------------------------------------------
def _rgba(c):
    return " ".join(f"{v:g}" for v in c)


def _geom_xml(g: dict, extra: str = "") -> str:
    size = " ".join(f"{v:g}" for v in g["size"])
    pos = " ".join(f"{v:g}" for v in g["pos"])
    eul = " ".join(f"{math.radians(v):g}" for v in g["euler"])
    return f'<geom type="{g["type"]}" size="{size}" pos="{pos}" euler="{eul}" rgba="{_rgba(g["rgba"])}" {extra}/>'


def _item_xml(it: dict) -> str:
    k = KINDS[it["kind"]]
    z = SURFACES[it["surface"]]["top"] + k["h"] + 0.002
    each = k["mass"] / len(k["geoms"])
    # Light things: generous friction against rolling so a nudged paper ball stops instead of crossing the room.
    geoms = "".join(_geom_xml(g, f'mass="{each:g}" condim="6" friction="0.7 0.02 0.004" solref="0.004 1"') for g in k["geoms"])
    return (f'<body name="{it["name"]}" pos="{it["x"]:g} {it["y"]:g} {z:g}" euler="0 0 {it["yaw"]:g}">'
            f'<freejoint name="{it["name"]}"/>{geoms}</body>')


def _bin_xml() -> str:
    b = BIN
    hx, hy, w, h = b["hx"], b["hy"], b["wall"], b["height"]
    col, rim = "0.36 0.52 0.50 1", "0.16 0.22 0.22 1"
    wall = 'mass="0.05" friction="0.6 0.01 0.001"'
    gx, gy = STATION["bin_grip"]
    bar = hx + b["handle"]
    return f"""
    <body name="bin" pos="{gx:g} {gy - bar:g} 0.001" euler="0 0 {math.pi / 2:g}">
      <freejoint name="bin"/>
      <geom type="box" size="{hx:g} {hy:g} {b['floor'] / 2:g}" pos="0 0 {b['floor'] / 2:g}" rgba="{col}" mass="0.12" friction="0.8 0.01 0.001"/>
      <geom type="box" size="{hx:g} {w / 2:g} {h / 2:g}" pos="0 {hy - w / 2:g} {h / 2:g}" rgba="{col}" {wall}/>
      <geom type="box" size="{hx:g} {w / 2:g} {h / 2:g}" pos="0 {-hy + w / 2:g} {h / 2:g}" rgba="{col}" {wall}/>
      <geom type="box" size="{w / 2:g} {hy:g} {h / 2:g}" pos="{hx - w / 2:g} 0 {h / 2:g}" rgba="{col}" {wall}/>
      <geom type="box" size="{w / 2:g} {hy:g} {h / 2:g}" pos="{-hx + w / 2:g} 0 {h / 2:g}" rgba="{col}" {wall}/>
      <geom type="box" size="{hx + 0.004:g} 0.005 0.004" pos="0 {hy:g} {h:g}" rgba="{rim}" contype="0" conaffinity="0" mass="0" group="1"/>
      <geom type="box" size="{hx + 0.004:g} 0.005 0.004" pos="0 {-hy:g} {h:g}" rgba="{rim}" contype="0" conaffinity="0" mass="0" group="1"/>
      <geom type="box" size="0.005 {hy + 0.004:g} 0.004" pos="{hx:g} 0 {h:g}" rgba="{rim}" contype="0" conaffinity="0" mass="0" group="1"/>
      <geom type="box" size="0.005 {hy + 0.004:g} 0.004" pos="{-hx:g} 0 {h:g}" rgba="{rim}" contype="0" conaffinity="0" mass="0" group="1"/>
      <geom name="bin_handle" type="capsule" size="0.011 0.055" pos="{bar:g} 0 {h - 0.012:g}" euler="{math.pi / 2:g} 0 0" rgba="0.85 0.20 0.15 1" mass="0.02"/>
      <geom type="box" size="{b['handle'] / 2:g} 0.008 0.008" pos="{hx + b['handle'] / 2:g} 0.058 {h - 0.012:g}" rgba="{rim}" mass="0.005"/>
      <geom type="box" size="{b['handle'] / 2:g} 0.008 0.008" pos="{hx + b['handle'] / 2:g} -0.058 {h - 0.012:g}" rgba="{rim}" mass="0.005"/>
      <site name="bin_grip" pos="{bar:g} 0 {h - 0.012:g}" euler="0 0 {math.pi / 2:g}" size="0.006" rgba="1 1 0 0"/>
    </body>"""


def _brush_xml() -> str:
    b = BRUSH
    mid = (b["handle_from"] + b["handle_to"]) / 2
    half = (b["handle_from"] - b["handle_to"]) / 2
    return f"""
    <body name="brush" pos="{STATION['brush_grip'][0] + b['grip_x']:g} {STATION['brush_grip'][1]:g} {STATION['shelf']['top'] + 0.001:g}" euler="0 0 {math.pi:g}">
      <freejoint name="brush"/>
      <!-- The bristles give: they slide up into the head against a soft spring. A rigid block of bristles on a
           position-controlled arm either hovers over flat things or is pressed so hard that it drags and tilts. -->
      <body name="brush_bristles">
        <joint name="bristle_give" type="slide" axis="0 0 1" range="0 {b['give']:g}" stiffness="{b['stiffness']:g}" damping="1.5"/>
        <geom name="bristles" type="box" size="0.018 {b['head_hy'] - 0.004:g} 0.0165" pos="0 0 0.0165" rgba="0.12 0.12 0.14 1" mass="0.02"
              friction="0.25 0.005 0.0005"/>
      </body>
      <geom type="box" size="0.022 {b['head_hy']:g} 0.012" pos="0 0 0.045" rgba="0.72 0.50 0.28 1" mass="0.07"/>
      <geom name="brush_handle" type="capsule" size="0.013 {half:g}" pos="{mid:g} 0 {b['grip_z']:g}" euler="0 {math.pi / 2:g} 0" rgba="0.72 0.50 0.28 1" mass="0.003"/>
      <geom type="sphere" size="0.016" pos="{b['handle_to']:g} 0 {b['grip_z']:g}" rgba="0.85 0.20 0.15 1" mass="0.001"/>
      <site name="brush_grip" pos="{b['grip_x']:g} 0 {b['grip_z']:g}" size="0.006" rgba="1 1 0 0"/>
    </body>"""


def _room_xml() -> str:
    t, s, sh = TABLE, SOFA, STATION["shelf"]
    x0, x1 = ROOM["x"]
    y0, y1 = ROOM["y"]
    wood, dark = "0.55 0.38 0.24 1", "0.30 0.20 0.13 1"
    fabric, fabric2 = "0.58 0.62 0.66 1", "0.50 0.54 0.59 1"
    legs = "".join(f'<geom type="box" size="0.025 0.025 {(t["top"] - 0.03) / 2:g}" pos="{t["cx"] + sx * (t["hx"] - 0.05):g} '
                   f'{t["cy"] + sy * (t["hy"] - 0.05):g} {(t["top"] - 0.03) / 2:g}" rgba="{dark}"/>'
                   for sx in (-1, 1) for sy in (-1, 1))
    return f"""
    <geom name="floor" type="plane" size="0 0 0.05" material="floor"/>
    <geom type="box" size="1.0 0.75 0.004" pos="{t['cx']:g} {t['cy'] + 0.25:g} 0.004" rgba="0.74 0.70 0.62 1" contype="0" conaffinity="0"/>
    <geom type="box" size="{(x1 - x0) / 2:g} 0.03 0.7" pos="{(x0 + x1) / 2:g} {y1 + 0.03:g} 0.7" material="wall"/>
    <geom type="box" size="0.03 {(y1 - y0) / 2:g} 0.7" pos="{x0 - 0.03:g} {(y0 + y1) / 2:g} 0.7" material="wall"/>
    <geom type="box" size="0.03 {(y1 - y0) / 2:g} 0.7" pos="{x1 + 0.03:g} {(y0 + y1) / 2:g} 0.7" material="wall" group="2"/>
    <geom type="box" size="{(x1 - x0) / 2:g} 0.03 0.7" pos="{(x0 + x1) / 2:g} {y0 - 0.03:g} 0.7" material="wall" group="2"/>

    <geom name="table_top" type="box" size="{t['hx']:g} {t['hy']:g} 0.015" pos="{t['cx']:g} {t['cy']:g} {t['top'] - 0.015:g}" rgba="{wood}" friction="0.5 0.01 0.001"/>
    {legs}
    <geom type="box" size="{t['hx'] - 0.06:g} {t['hy'] - 0.06:g} 0.008" pos="{t['cx']:g} {t['cy']:g} 0.14" rgba="{dark}"/>

    <geom name="sofa_seat" type="box" size="{s['hx']:g} {s['hy']:g} 0.16" pos="{s['cx']:g} {s['cy']:g} {s['top'] - 0.16:g}" rgba="{fabric}" friction="0.7 0.01 0.001"/>
    <geom type="box" size="0.002 {s['hy']:g} 0.001" pos="{s['cx']:g} {s['cy']:g} {s['top'] + 0.0005:g}" rgba="{fabric2}" contype="0" conaffinity="0"/>
    <geom type="box" size="{s['hx'] + 0.16:g} 0.11 0.41" pos="{s['cx']:g} {s['cy'] + s['hy'] + 0.11:g} 0.41" rgba="{fabric2}"/>
    <geom type="box" size="0.08 {s['hy']:g} 0.30" pos="{s['cx'] - s['hx'] - 0.08:g} {s['cy']:g} 0.30" rgba="{fabric2}"/>
    <geom type="box" size="0.08 {s['hy']:g} 0.30" pos="{s['cx'] + s['hx'] + 0.08:g} {s['cy']:g} 0.30" rgba="{fabric2}"/>
    <geom type="box" size="{s['hx'] + 0.16:g} {s['hy'] + 0.09:g} 0.05" pos="{s['cx']:g} {s['cy'] + 0.11:g} 0.05" rgba="{dark}"/>

    <geom name="station_shelf" type="box" size="{sh['hx']:g} {sh['hy']:g} {sh['top'] / 2:g}" pos="{sh['cx']:g} {sh['cy']:g} {sh['top'] / 2:g}" rgba="0.82 0.82 0.80 1"/>
    <geom type="box" size="0.012 0.50 0.30" pos="{x0 + 0.012:g} -0.60 0.95" rgba="0.90 0.74 0.30 1" contype="0" conaffinity="0"/>
    <geom type="box" size="0.30 0.52 0.002" pos="-1.70 -0.60 0.002" rgba="0.90 0.74 0.30 1" contype="0" conaffinity="0"/>

    <geom type="box" size="0.22 0.70 0.24" pos="{x1 - 0.22:g} -0.2 0.24" rgba="{dark}"/>
    <geom type="box" size="0.02 0.50 0.30" pos="{x1 - 0.30:g} -0.2 0.83" rgba="0.05 0.05 0.06 1"/>
    <geom type="cylinder" size="0.16 0.17" pos="{x1 - 0.35:g} 1.45 0.17" rgba="0.80 0.45 0.30 1"/>
    <geom type="ellipsoid" size="0.24 0.24 0.38" pos="{x1 - 0.35:g} 1.45 0.72" rgba="0.20 0.48 0.25 1" contype="0" conaffinity="0"/>
    <geom type="cylinder" size="0.13 0.012" pos="{x0 + 0.35:g} 1.45 0.012" rgba="0.15 0.15 0.16 1"/>
    <geom type="cylinder" size="0.012 0.72" pos="{x0 + 0.35:g} 1.45 0.72" rgba="0.15 0.15 0.16 1"/>
    <geom type="cylinder" size="0.15 0.12" pos="{x0 + 0.35:g} 1.45 1.50" rgba="0.97 0.92 0.78 1" contype="0" conaffinity="0"/>
    """


def _robot_xml(scene: dict) -> tuple[str, str, str]:
    """The TIAGo++ model from MuJoCo Menagerie with three changes: the base slides and turns on the floor
    under position control instead of rolling on simulated wheels, a camera sits in the head, and each
    hand carries a site at the point between its fingers. Returns (assets, defaults, body)."""
    src = (ASSETS / "tiago_dual.xml").read_text()
    assets = re.search(r"<asset>(.*?)</asset>", src, re.S).group(1)
    defaults = re.search(r"(<default class=\"main\">.*?</default>\s*</default>)", src, re.S).group(1)
    defaults = defaults.replace('<geom condim="6"/>', '<geom contype="0" conaffinity="0"/>')
    body = re.search(r"<worldbody>(.*)</worldbody>", src, re.S).group(1)
    body = body.replace('<body name="base_link">', '<body name="base_link" childclass="main">', 1)
    body = body.replace('<joint name="reference" type="free"/>',
                        '<joint name="base_x" type="slide" axis="1 0 0" damping="20"/>'
                        '<joint name="base_y" type="slide" axis="0 1 0" damping="20"/>'
                        '<joint name="base_yaw" type="hinge" axis="0 0 1" damping="10"/>', 1)
    body = body.replace('<joint name="head_2_joint"',
                        '<camera name="head" pos="0.115 0.03 0" xyaxes="0 0 1 0 1 0" fovy="58"/>\n            <joint name="head_2_joint"', 1)
    body = body.replace('<joint name="arm_left_7_joint"',
                        '<site name="grasp_left" pos="0 0 -0.27" quat="0 0 1 0" size="0.008" rgba="0 1 0 0"/>\n'
                        '<camera name="wrist_left" pos="0.05 0 -0.07" xyaxes="0 1 0 -1 0 0" fovy="70"/>\n'
                        '<joint name="arm_left_7_joint"', 1)
    body = body.replace('<joint name="arm_right_7_joint"',
                        '<site name="grasp_right" pos="0 0 0.27" size="0.008" rgba="0 1 0 0"/>\n'
                        '<camera name="wrist_right" pos="0.05 0 0.07" xyaxes="0 1 0 1 0 0" fovy="70"/>\n'
                        '<joint name="arm_right_7_joint"', 1)
    # The Menagerie file gives the two third arm joints ranges that are not mirror images of each other
    # (the same joint values put the arms in mirrored postures), which leaves the right arm unable to
    # take most palm-down poses the left arm can. The robot is symmetric, so the right arm gets the left's range.
    assert 'name="arm_right_3_joint" range="-3.53429 1.5708"' in body
    body = body.replace('name="arm_right_3_joint" range="-3.53429 1.5708"', 'name="arm_right_3_joint" range="-0.785398 3.92699"')
    return assets, defaults, body


def _actuators_xml() -> str:
    src = (ASSETS / "tiago_dual_position.xml").read_text()
    block = re.search(r"<actuator>(.*?)</actuator>", src, re.S).group(1)
    keep = [ln for ln in re.findall(r"<position.*?/>", block, re.S)]
    base = ('<position name="base_x" joint="base_x" kp="60000" kv="3000" forcerange="-400 400"/>'
            '<position name="base_y" joint="base_y" kp="60000" kv="3000" forcerange="-400 400"/>'
            '<position name="base_yaw" joint="base_yaw" kp="15000" kv="800" forcerange="-200 200"/>')
    return base + "\n".join(keep)


def _cam(name: str, pos, target, fovy: float, up=(0, 0, 1)) -> str:
    """A fixed camera at `pos` looking at `target`."""
    f = [t - p for p, t in zip(pos, target)]
    n = math.sqrt(sum(v * v for v in f)); f = [v / n for v in f]
    r = [f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0]]
    n = math.sqrt(sum(v * v for v in r)); r = [v / n for v in r]
    u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]]
    return (f'<camera name="{name}" pos="{pos[0]:g} {pos[1]:g} {pos[2]:g}" '
            f'xyaxes="{r[0]:.4f} {r[1]:.4f} {r[2]:.4f} {u[0]:.4f} {u[1]:.4f} {u[2]:.4f}" fovy="{fovy:g}"/>')


def build_xml(scene: dict) -> str:
    assets, defaults, robot = _robot_xml(scene)
    env = _room_xml() + _bin_xml() + _brush_xml() + "\n".join(_item_xml(it) for it in scene["items"])
    env = env.replace("<geom ", '<geom class="env" ')
    welds = "\n".join(f'<weld name="{hand}_{tool}" body1="arm_{hand}_7_link" body2="{tool}" active="false" solref="0.004 1"/>'
                      for hand in ("left", "right") for tool in ("brush", "bin"))
    return f"""
<mujoco model="living_room_sweep">
  <compiler angle="radian" meshdir="{ASSETS / 'assets'}" autolimits="true"/>
  <option timestep="0.002" integrator="implicitfast" cone="elliptic" impratio="3"/>
  <size memory="200M"/>
  <visual>
    <global offwidth="1600" offheight="1200" azimuth="130" elevation="-30"/>
    <quality shadowsize="4096"/>
    <headlight ambient="0.42 0.42 0.42" diffuse="0.45 0.45 0.45" specular="0 0 0"/>
    <map znear="0.02" zfar="30"/>
  </visual>
  <asset>
    {assets}
    <texture name="floor" type="2d" builtin="checker" rgb1="0.80 0.69 0.55" rgb2="0.77 0.66 0.52" width="256" height="256"/>
    <material name="floor" texture="floor" texrepeat="5 5" reflectance="0.04"/>
    <material name="wall" rgba="0.93 0.91 0.86 1"/>
    <texture type="skybox" builtin="gradient" rgb1="0.93 0.94 0.96" rgb2="0.80 0.83 0.88" width="64" height="64"/>
  </asset>
  {defaults[:defaults.rindex('</default>')]}
    <default class="position"><position dampratio="1"/></default>
    <default class="env"><geom contype="1" conaffinity="1" group="0" mass="0"/></default>
  </default>
  <worldbody>
    <light pos="0.5 -0.5 3.2" dir="-0.15 0.25 -1" diffuse="0.55 0.55 0.52" specular="0.1 0.1 0.1" castshadow="true"/>
    {_cam("overview", (3.1, -3.9, 3.5), (0.1, -0.1, 0.35), 44)}
    {_cam("top", (0.0, -0.28, 6.9), (0.0, -0.28, 0.0), 36, up=(0, 1, 0))}
    {_cam("table", (TABLE['cx'] + 1.0, TABLE['cy'] - 1.2, 1.35), (TABLE['cx'], TABLE['cy'], TABLE['top']), 42)}
    {_cam("sofa", (SOFA['cx'] - 0.3, SOFA['cy'] - 1.7, 1.6), (SOFA['cx'], SOFA['cy'], SOFA['top']), 50)}
    {_cam("stage", (TABLE['cx'] + 1.25, TABLE['cy'] - 2.2, 2.25), (TABLE['cx'] - 0.05, TABLE['cy'] + 0.35, 0.35), 46)}
    {_cam("station", (-0.55, 0.95, 1.45), (-1.50, -0.60, 0.45), 48)}
    {env}
    {robot}
  </worldbody>
  <contact>
    <!-- The torso's collision shape is the convex hull of its mesh, which fills the hollow between the shoulders.
         The upper arms run into that hull where the real robot has free space, and a hand could then not
         work in front of the chest. The upper arm links are exempt from it. -->
    <exclude body1="torso_lift_link" body2="arm_left_2_link"/>
    <exclude body1="torso_lift_link" body2="arm_right_2_link"/>
    <exclude body1="torso_lift_link" body2="arm_left_3_link"/>
    <exclude body1="torso_lift_link" body2="arm_right_3_link"/>
  </contact>
  <equality>
    {welds}
  </equality>
  <actuator>
    {_actuators_xml()}
  </actuator>
</mujoco>
"""
