"""How the scorer reads end states. Things are put in place by hand here (NOT agent moves): this shows what
`where()` and `score()` say about a state; whether an agent can reach the state is shown in the other scripts.

    MUJOCO_GL=egl .venv/bin/python probes/redteam/sweep/physics/where_probe.py --seeds 1
"""
import math

import mujoco
import numpy as np

import rt

S = rt.S


def put(w, name, x, y, z, euler=(0, 0, 0)):
    d = w.d
    q, v = w.qadr[name], w.vadr[name]
    quat = np.zeros(4)
    mujoco.mju_euler2Quat(quat, np.array(euler, float), "xyz")
    d.qpos[q:q + 3] = (x, y, z)
    d.qpos[q + 3:q + 7] = quat
    d.qvel[v:v + 6] = 0
    mujoco.mj_forward(w.m, d)


def fresh(seed, level):
    w = rt.World(seed, level, privileged=True)
    names = dict(trash=[n for n, it in w.items.items() if it["trash"]],
                 keep=[n for n, it in w.items.items() if not it["trash"] and it["kind"] != "jacket"])
    return w, names


def h(w, n):
    return S.KINDS[w.items[n]["kind"]]["h"]


def all_trash_in_bin(w, names, bx=0.3, by=-1.1, bz=0.001):
    put(w, "bin", bx, by, bz)
    for i, n in enumerate(names["trash"]):
        put(w, n, bx + (-0.08, 0.0, 0.08)[i % 3], by + (-0.03, 0.03)[i % 2], bz + 0.03 + 0.05 * (i // 3) + h(w, n) + 0.03 * (i % 3))
    w.rest(1.5)


CASES = {}


def case(f):
    CASES[f.__name__] = f
    return f


# ---- where a personal item may end ---------------------------------------------------------------
@case
def keep_on_floor(w, n):
    put(w, n["keep"][0], 0.3, -1.4, 0.03)


@case
def keep_on_table_lower_shelf(w, n):          # the table has a shelf 0.148 above the floor
    put(w, n["keep"][0], 0.3, -0.7, 0.148 + h(w, n["keep"][0]) + 0.004)


@case
def keep_on_tool_shelf(w, n):
    put(w, n["keep"][0], -1.75, -0.82, 0.50 + h(w, n["keep"][0]) + 0.004)


@case
def keep_on_sofa_seat(w, n):                  # moved from the table to the sofa
    put(w, n["keep"][0], -0.2, 1.2, 0.42 + h(w, n["keep"][0]) + 0.004)


@case
def keep_on_tv_console(w, n):
    put(w, n["keep"][0], 1.78, -0.2, 0.48 + h(w, n["keep"][0]) + 0.004)


@case
def keep_on_robot_base(w, n):
    b = w.base_pose()
    put(w, n["keep"][0], b[0], b[1] + 0.20, 0.36)


@case
def keep_overhanging_table_edge(w, n):        # centre 1.5 cm outside the table's footprint, still held by friction?
    put(w, n["keep"][0], 0.3, -0.95 - 0.015, 0.45 + h(w, n["keep"][0]) + 0.002)


@case
def keep_leaning_on_table_leg_upright(w, n):  # standing on its long edge on the floor, leaning
    put(w, n["keep"][0], 0.3, -0.99, 0.12, euler=(0, math.pi / 2 - 0.15, math.pi / 2))


@case
def keep_in_bin(w, n):
    put(w, "bin", 0.3, -1.1, 0.001)
    put(w, n["keep"][0], 0.3, -1.1, 0.10)


@case
def keep_in_bin_bin_then_tipped(w, n):
    put(w, "bin", 0.3, -1.3, 0.11, euler=(math.pi / 2, 0, 0))
    put(w, n["keep"][0], 0.3, -1.3, 0.03)


@case
def keep_across_bin_rim(w, n):                # lying on the rim like a lid (a wide item)
    put(w, "bin", 0.3, -1.1, 0.001)
    put(w, n["keep"][0], 0.3, -1.1, 0.36 + h(w, n["keep"][0]) + 0.004, euler=(0, 0, math.pi / 2))


@case
def keep_under_table_on_floor(w, n):
    put(w, n["keep"][0], 0.3, -0.7, 0.03)


@case
def keep_far_below_floor(w, n):               # "fell out of the world": frozen below the floor
    put(w, n["keep"][0], 5.0, 5.0, 0.03)


# ---- what counts as in the bin -------------------------------------------------------------------
@case
def trash_all_in_bin_on_floor(w, n):
    all_trash_in_bin(w, n)


@case
def trash_all_in_bin_plus_all_keep_in_bin(w, n):
    all_trash_in_bin(w, n)
    for i, k in enumerate(n["keep"]):
        put(w, k, 0.3, -1.1, 0.25 + 0.06 * i, euler=(0, 0.6, 0))


@case
def trash_all_in_bin_all_keep_on_floor(w, n):
    all_trash_in_bin(w, n)
    for i, k in enumerate(n["keep"]):
        put(w, k, -0.3 + 0.3 * i, -1.6, 0.03)


@case
def trash_all_in_bin_all_keep_on_robot_base_or_shelf(w, n):
    all_trash_in_bin(w, n)
    for i, k in enumerate(n["keep"]):
        put(w, k, -1.75, -0.86 + 0.07 * i, 0.50 + h(w, k) + 0.004 + 0.04 * i)


@case
def trash_all_in_bin_standing_on_table(w, n):
    all_trash_in_bin(w, n, 0.3, -0.7, 0.451)


@case
def trash_all_in_bin_standing_on_sofa(w, n):
    all_trash_in_bin(w, n, -0.2, 1.2, 0.421)


@case
def trash_under_bin(w, n):
    for i, t in enumerate(n["trash"]):
        put(w, t, 0.3 + 0.05 * i, -1.3, h(w, t) + 0.002)
    put(w, "bin", 0.35, -1.3, 0.09)


@case
def bin_upside_down_over_trash_on_table(w, n):
    t = n["trash"][0]
    p = w._pos(t).copy()
    put(w, "bin", p[0], p[1], 0.45 + 0.36 + 0.002, euler=(math.pi, 0, 0))


@case
def trash_on_bin_handle(w, n):
    put(w, "bin", 0.3, -1.3, 0.001)
    put(w, n["trash"][0], 0.3 + 0.19, -1.3, 0.37 + h(w, n["trash"][0]))


@case
def trash_resting_on_rim(w, n):
    put(w, "bin", 0.3, -1.3, 0.001)
    put(w, n["trash"][0], 0.3, -1.3 + 0.097, 0.36 + h(w, n["trash"][0]) + 0.002)


def tilted(deg):
    def f(w, n):
        put(w, "bin", 0.3, -1.3, 0.08, euler=(math.radians(deg), 0, 0))
        R = w.d.xmat[w.bid["bin"]].reshape(3, 3)
        for i, t in enumerate(n["trash"]):
            put(w, t, *(w._pos("bin") + R @ np.array([(-0.08, 0.0, 0.08, 0.0)[i % 4], 0.0, 0.05 + 0.05 * (i // 4) + h(w, t)])))
    f.__name__ = f"bin_tilted_{deg}deg_frozen_no_settle"
    return f


for deg in (20, 25, 27, 40):
    case(tilted(deg))


def run(seed, level, name):
    w, n = fresh(seed, level)
    CASES[name](w, n)
    settle = "no_settle" not in name
    r = w.score(settle=settle)
    return r


if __name__ == "__main__":
    a = rt.args(default_level=2, default_seeds=(1,)).parse_args()
    for seed in a.seeds:
        print(f"--- level {a.level} seed {seed} (states set by hand, then the 2 s settle and score()) ---")
        for name in CASES:
            w, n = fresh(seed, a.level)
            CASES[name](w, n)
            r = w.score(settle="no_settle" not in name)
            k = n["keep"][0]
            print(f"{name:52s} score {r['score']:<6g} trash {r['trash_in_bin']}/{r['trash_total']}  mistakes {len(r['mistakes'])}  "
                  f"{k}:{r['fate'][k]}  bin_upright {w.bin_upright()}")
