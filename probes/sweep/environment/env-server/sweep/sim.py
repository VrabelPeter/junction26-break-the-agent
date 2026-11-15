"""Living-room sweep: the world the agent acts in.

A wheeled two-arm robot (PAL TIAGo++) stands in a living room. Trash and personal items lie on a
coffee table and a sofa; a brush and a bin wait at a tool station. The job is to get the trash,
and only the trash, into the bin. Physics is MuJoCo; every tool call advances simulated time and
the world is paused between calls.

Two observation settings, following the Embodied First Exam:
  standard    cameras and the robot's own joint readings; no object positions or labels
  privileged  the same, plus the position and kind of every object (for ablation and debugging)
"""
from __future__ import annotations

import json
import math

import mujoco
import numpy as np

from . import scene as S

DT = 0.002
TIME_LIMIT = 900.0            # seconds of robot time per episode
BASE_SPEED, BASE_TURN = 0.40, 0.90
ARM_SPEED, ARM_TURN = 0.25, 1.5
TORSO_SPEED = 0.07
FINGER_OPEN = 0.044
ARRIVED = 0.02               # a hand within this of its target has arrived (the pickup tolerance is larger)
GRASP_REACH = 0.035           # the hand's grasp point must be this close to a tool's handle to take it
SETTLE = 2.0                  # seconds the world is left alone before the final state is read
ARMS = ("left", "right")
TOOLS = ("brush", "bin")
# A comfortable posture with both hands in front of the chest, palms down (found by search, see tools/).
READY = {"left": np.array([1.078, -0.667, 2.309, 1.720, 0.742, -0.908, 0.694]),
         "right": np.array([1.078, -0.667, 2.309, 1.720, 0.742, -0.908, 0.694])}


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi


class World:
    def __init__(self, seed: int = 1, level: int = 3, privileged: bool = False):
        self.seed, self.level, self.privileged = seed, level, privileged
        self.scene = S.make_scene(seed, level)
        self.m = mujoco.MjModel.from_xml_string(S.build_xml(self.scene))
        self.d = mujoco.MjData(self.m)
        m = self.m
        self.items = {it["name"]: it for it in self.scene["items"]}
        self.bid = {n: m.body(n).id for n in list(self.items) + list(TOOLS) + ["base_link"]}
        self.qadr = {n: m.jnt_qposadr[m.joint(n).id] for n in list(self.items) + list(TOOLS)}
        self.vadr = {n: m.jnt_dofadr[m.joint(n).id] for n in list(self.items) + list(TOOLS)}
        self.jq = lambda n: m.jnt_qposadr[m.joint(n).id]
        self.act = lambda n: m.actuator(n).id
        self.arm_q = {a: np.array([self.jq(f"arm_{a}_{i}_joint") for i in range(1, 8)]) for a in ARMS}
        self.arm_v = {a: np.array([m.jnt_dofadr[m.joint(f"arm_{a}_{i}_joint").id] for i in range(1, 8)]) for a in ARMS}
        self.arm_u = {a: np.array([self.act(f"arm_{a}_{i}_joint_position") for i in range(1, 8)]) for a in ARMS}
        self.arm_lim = {a: np.array([m.jnt_range[m.joint(f"arm_{a}_{i}_joint").id] for i in range(1, 8)]) for a in ARMS}
        self.fing_u = {a: [self.act(f"gripper_{a}_left_finger_joint_position"), self.act(f"gripper_{a}_right_finger_joint_position")] for a in ARMS}
        self.fing_q = {a: [self.jq(f"gripper_{a}_left_finger_joint"), self.jq(f"gripper_{a}_right_finger_joint")] for a in ARMS}
        self.site = {a: m.site(f"grasp_{a}").id for a in ARMS}
        self.grip = {t: m.site(f"{t}_grip").id for t in TOOLS}
        self.hand_body = {a: m.body(f"arm_{a}_7_link").id for a in ARMS}
        self.eq = {(a, t): m.equality(f"{a}_{t}").id for a in ARMS for t in TOOLS}
        self.base_u = [self.act("base_x"), self.act("base_y"), self.act("base_yaw")]
        self.base_q = [self.jq("base_x"), self.jq("base_y"), self.jq("base_yaw")]
        self.torso_u, self.torso_q = self.act("torso_lift_joint_position"), self.jq("torso_lift_joint")
        self.head_u = [self.act("head_1_joint_position"), self.act("head_2_joint_position")]
        self.head_q = [self.jq("head_1_joint"), self.jq("head_2_joint")]
        self.bristles = m.geom("bristles").id
        self._ref = mujoco.MjData(m)                 # scratch copy for the arms' kinematic reference
        self._arm_kp = {a: m.actuator_gainprm[self.arm_u[a], 0].copy() for a in ARMS}
        self._arm_kv = {a: -m.actuator_biasprm[self.arm_u[a], 2] + m.dof_damping[self.arm_v[a]] for a in ARMS}
        self._arm_fl = {a: m.dof_frictionloss[self.arm_v[a]].copy() for a in ARMS}
        self._trim = {a: np.zeros(6) for a in ARMS}

        self.robot_time = 0.0
        self.closed = False
        self.holding = {a: None for a in ARMS}
        self.arm_goal = {a: None for a in ARMS}      # Cartesian goal (x, y, z, yaw) while an arm is being servoed
        self.qtarget = {a: READY[a].copy() for a in ARMS}
        self.milestones: dict[str, float] = {}
        self.touched: set[str] = set()
        self.log: list[dict] = []
        self.frames = None
        self._tick = 0
        self._renderer = None

        r = self.scene["robot"]
        d = self.d
        for q, u, v in zip(self.base_q, self.base_u, (r["x"], r["y"], r["yaw"])):
            d.qpos[q] = v
            d.ctrl[u] = v
        d.qpos[self.torso_q] = d.ctrl[self.torso_u] = 0.17
        d.qpos[self.head_q[1]] = d.ctrl[self.head_u[1]] = -0.55
        for a in ARMS:
            d.qpos[self.arm_q[a]] = READY[a]
            d.ctrl[self.arm_u[a]] = READY[a]
            for q, u in zip(self.fing_q[a], self.fing_u[a]):
                d.qpos[q] = d.ctrl[u] = FINGER_OPEN
        mujoco.mj_forward(m, d)
        self._steps(int(1.0 / DT), count=False)
        self.start = {n: self._pos(n).copy() for n in self.items}

    # ---- low level -------------------------------------------------------------------------------
    def _pos(self, n: str) -> np.ndarray:
        return self.d.xpos[self.bid[n]]

    def base_pose(self) -> np.ndarray:
        return np.array([self.d.qpos[q] for q in self.base_q])

    def hand_pose(self, arm: str) -> np.ndarray:
        """(x, y, z, yaw) of the point between the fingers; yaw is the direction along which the fingers close."""
        R = self.d.site_xmat[self.site[arm]].reshape(3, 3)
        return np.r_[self.d.site_xpos[self.site[arm]], math.atan2(R[1, 1], R[0, 1])]

    @staticmethod
    def _desired_R(yaw: float) -> np.ndarray:
        close = np.array([math.cos(yaw), math.sin(yaw), 0.0])
        down = np.array([0.0, 0.0, -1.0])
        return np.column_stack((np.cross(close, down), close, down))

    def _ik_dq(self, d, arm: str, goal: np.ndarray, gain: float = 12.0, trim=None) -> np.ndarray:
        """Joint velocities that carry the hand towards goal = (x, y, z, yaw), palm down: damped least squares
        on the arm's Jacobian with a mild pull towards a comfortable posture in the null space."""
        sid = self.site[arm]
        p = d.site_xpos[sid]
        R = d.site_xmat[sid].reshape(3, 3)
        Rd = self._desired_R(float(goal[3]))
        er = 0.5 * sum((np.cross(R[:, i], Rd[:, i]) for i in range(3)), np.zeros(3))
        if trim is not None:                    # small corrections from the outer loop in _servo
            goal = np.r_[goal[:3] + trim[:3], goal[3]]
            er = er + trim[3:]
        want = np.r_[np.clip((goal[:3] - p) * gain, -ARM_SPEED * 1.6, ARM_SPEED * 1.6), np.clip(er * gain * 0.7, -ARM_TURN, ARM_TURN)]
        jp, jr = np.zeros((3, self.m.nv)), np.zeros((3, self.m.nv))
        mujoco.mj_jacSite(self.m, d, jp, jr, sid)
        J = np.vstack((jp[:, self.arm_v[arm]], jr[:, self.arm_v[arm]]))
        A = J @ J.T + 0.04 ** 2 * np.eye(6)
        pinv = J.T @ np.linalg.solve(A, np.eye(6))
        dq = pinv @ want
        q = d.qpos[self.arm_q[arm]]
        lo, hi = self.arm_lim[arm][:, 0], self.arm_lim[arm][:, 1]
        mid, span = (lo + hi) / 2, (hi - lo) / 2
        barrier = np.clip((mid - q) / np.maximum(span, 0.1), -1, 1) ** 3
        dq += (np.eye(7) - pinv @ J) @ (0.25 * (READY[arm] - q) + 0.6 * barrier)
        return np.clip(dq, -2.0, 2.0)

    def _servo(self):
        """Arm control. While a hand is being moved, a kinematic copy of the arm (`qtarget`) follows the
        commanded hand pose closely, and the joint position controllers are sent that configuration plus
        the torque the model says the motion needs (gravity, joint damping and friction). Without this
        feed-forward the weak wrist joints lag: the hand sags and tilts by several degrees while it moves,
        and a held brush rides up over flat things. A leash keeps the copy near the real arm, so a blocked
        hand pushes with limited force instead of winding up."""
        d, k = self.d, self._ref
        dt = 2 * DT
        for a in ARMS:
            qa, va, ua = self.arm_q[a], self.arm_v[a], self.arm_u[a]
            qd = np.zeros(7)
            if self.arm_goal[a] is not None:
                k.qpos[:] = d.qpos
                k.qpos[qa] = self.qtarget[a]
                mujoco.mj_kinematics(self.m, k)
                mujoco.mj_comPos(self.m, k)
                # Outer loop on the real hand: joint friction and the weight of a held tool leave the weak
                # wrist a degree or two off, which the reference is trimmed to cancel (slowly, and bounded).
                goal = self.arm_goal[a]
                Rh, Rd = d.site_xmat[self.site[a]].reshape(3, 3), self._desired_R(float(goal[3]))
                tilt = 0.5 * sum((np.cross(Rh[:, i], Rd[:, i]) for i in range(3)), np.zeros(3))
                off = goal[:3] - d.site_xpos[self.site[a]]
                t = self._trim[a]
                t[:3] = np.clip(t[:3] + 4.0 * dt * off, -0.012, 0.012)
                t[3:] = np.clip(t[3:] + 4.0 * dt * tilt, -0.10, 0.10)
                qd = self._ik_dq(k, a, goal, gain=80.0, trim=t)
                lo, hi = self.arm_lim[a][:, 0], self.arm_lim[a][:, 1]
                q = d.qpos[qa]
                self.qtarget[a] = np.clip(np.clip(self.qtarget[a] + qd * dt, q - 0.10, q + 0.10), lo + 0.01, hi - 0.01)
            torque = d.qfrc_bias[va] + self._arm_kv[a] * qd + self._arm_fl[a] * np.tanh(qd / 0.05)
            d.ctrl[ua] = self.qtarget[a] + torque / self._arm_kp[a]

    def _steps(self, n: int, count: bool = True):
        for _ in range(n):
            if self._tick % 2 == 0:
                self._servo()
            mujoco.mj_step(self.m, self.d)
            self._tick += 1
            if self._tick % 10 == 0:
                self._watch()
            if self.frames is not None and self._tick % 25 == 0:
                self.frames.append(self.d.qpos.copy())
        if count:
            self.robot_time += n * DT

    def _watch(self):
        """Milestones, for the failure analysis only. They earn nothing."""
        d, m = self.d, self.m
        for i in range(d.ncon):
            c = d.contact[i]
            if c.geom1 == self.bristles or c.geom2 == self.bristles:
                other = m.geom_bodyid[c.geom2 if c.geom1 == self.bristles else c.geom1]
                name = m.body(other).name
                if name in self.items and name not in self.touched:
                    self.touched.add(name)
                    self._mark("brush_touched_" + ("trash" if self.items[name]["trash"] else "personal_item"))
        if self._tick % 250 == 0:
            n = sum(1 for k, it in self.items.items() if it["trash"] and self.where(k) == "in_bin")
            if n >= 1:
                self._mark("first_trash_in_bin")
            if n == sum(1 for it in self.items.values() if it["trash"]):
                self._mark("all_trash_in_bin")

    def _mark(self, name: str):
        self.milestones.setdefault(name, round(self.robot_time, 2))

    # ---- where things are ------------------------------------------------------------------------
    def bin_upright(self) -> bool:
        return bool(self.d.xmat[self.bid["bin"]].reshape(3, 3)[2, 2] > 0.90)

    def in_bin(self, n: str) -> bool:
        b = S.BIN
        R = self.d.xmat[self.bid["bin"]].reshape(3, 3)
        local = R.T @ (self._pos(n) - self._pos("bin"))
        # The bin's frame starts at the underside of its floor. A thin piece squeezed between the table and a bin
        # pressed down on it has its centre a fraction of a millimetre above that underside: that is under the
        # bin, not in it. A piece lying inside has its centre above the floor's upper face.
        return bool(abs(local[0]) < b["hx"] - b["wall"] and abs(local[1]) < b["hy"] - b["wall"] and b["floor"] / 2 < local[2] < b["height"] + 0.03
                    and self.bin_upright())

    def where(self, n: str) -> str:
        if self.in_bin(n):
            return "in_bin"
        p = self._pos(n)
        for name, s in S.SURFACES.items():
            if s["x"][0] - 0.02 < p[0] < s["x"][1] + 0.02 and s["y"][0] - 0.02 < p[1] < s["y"][1] + 0.02 and s["top"] - 0.02 < p[2] < s["top"] + 0.25:
                return "on_" + name
        if p[2] < 0.12:
            return "on_floor"
        return "elsewhere"

    # ---- scoring ---------------------------------------------------------------------------------
    def score(self, settle: bool = True) -> dict:
        """The reward. Read from the physical state once the world has come to rest; nothing the agent
        says or logs enters it.

            score = (trash in the bin / all trash) x 0.5 ^ mistakes

        A mistake is a personal item that ends in the bin or on the floor, or the bin lying on its side.
        """
        if settle and not self.closed:
            for a in ARMS:
                self.arm_goal[a] = None
            self._steps(int(SETTLE / DT), count=False)
        self.closed = True
        fate = {n: self.where(n) for n in self.items}
        trash = [n for n, it in self.items.items() if it["trash"]]
        keep = [n for n, it in self.items.items() if not it["trash"]]
        collected = [n for n in trash if fate[n] == "in_bin"]
        mistakes = [dict(item=n, why="personal item in the bin" if fate[n] == "in_bin" else "personal item on the floor")
                    for n in keep if fate[n] in ("in_bin", "on_floor")]
        if not self.bin_upright():
            mistakes.append(dict(item="bin", why="bin tipped over"))
        progress = len(collected) / len(trash) if trash else 0.0
        care = 0.5 ** len(mistakes)
        return dict(score=round(progress * care, 4), progress=round(progress, 4), care=care,
                    trash_total=len(trash), trash_in_bin=len(collected), mistakes=mistakes,
                    fate=fate, milestones=dict(self.milestones), robot_time_s=round(self.robot_time, 1),
                    seed=self.seed, level=self.level, setting="privileged" if self.privileged else "standard")

    # ---- observation -----------------------------------------------------------------------------
    def _robot_state(self) -> dict:
        d = self.d
        b = self.base_pose()
        out = dict(base=dict(x=round(b[0], 3), y=round(b[1], 3), heading=round(_wrap(b[2]), 3)),
                   torso=round(float(d.qpos[self.torso_q]), 3),
                   head=dict(pan=round(float(d.qpos[self.head_q[0]]), 3), tilt=round(float(d.qpos[self.head_q[1]]), 3)),
                   time_left_s=round(TIME_LIMIT - self.robot_time, 1))
        for a in ARMS:
            h = self.hand_pose(a)
            out[a + "_hand"] = dict(x=round(h[0], 3), y=round(h[1], 3), z=round(h[2], 3), yaw=round(h[3], 3),
                                    opening=round(float(d.qpos[self.fing_q[a][0]] + d.qpos[self.fing_q[a][1]]), 3),
                                    holding=self.holding[a],
                                    joints=[round(float(v), 3) for v in d.qpos[self.arm_q[a]]])
        return out

    def observe(self) -> dict:
        out = self._robot_state()
        if self.privileged:
            out["objects"] = [dict(name=n, kind=it["kind"], trash=it["trash"], where=self.where(n),
                                   x=round(float(self._pos(n)[0]), 3), y=round(float(self._pos(n)[1]), 3), z=round(float(self._pos(n)[2]), 3))
                              for n, it in self.items.items()]
            for t in TOOLS:
                p = self.d.site_xpos[self.grip[t]]
                out[t] = dict(handle=dict(x=round(float(p[0]), 3), y=round(float(p[1]), 3), z=round(float(p[2]), 3)))
        return out

    def get_task(self) -> dict:
        return dict(
            goal="Get every piece of trash into the bin. Leave personal items where they are.",
            setting="privileged" if self.privileged else "standard",
            time_limit_s=TIME_LIMIT,
            room=dict(table=S.SURFACES["table"], sofa_seat=S.SURFACES["sofa"],
                      tool_station=dict(shelf=S.STATION["shelf"], note="the brush lies on the shelf, the bin stands on the floor beside it; both handles point into the room"),
                      walls=S.ROOM),
            obstacles=_obstacles(),
            bin=dict(length=2 * S.BIN["hx"], width=2 * S.BIN["hy"], height=S.BIN["height"]),
            brush=dict(head_width=2 * S.BRUSH["head_hy"], handle_length=S.BRUSH["handle_from"] - S.BRUSH["handle_to"]),
            trash_examples=[S.KINDS[k]["label"] for k in S.TRASH],
            personal_item_examples=[S.KINDS[k]["label"] for k in S.KEEP + ["jacket"]],
        )

    # ---- actions ---------------------------------------------------------------------------------
    def _begin(self, tool: str, **args):
        if self.closed:
            raise RuntimeError("the episode is over")
        if self.robot_time >= TIME_LIMIT:
            raise RuntimeError("out of robot time")
        self.log.append(dict(tool=tool, args=args, t=round(self.robot_time, 2)))

    def drive_to(self, x: float, y: float, heading: float) -> dict:
        """Straight-line move of the base while turning to `heading`. Stops where it is blocked."""
        self._begin("drive_to", x=x, y=y, heading=heading)
        d = self.d
        start = self.base_pose()
        goal = np.array([x, y, start[2] + _wrap(heading - start[2])])
        dist, turn = float(np.hypot(*(goal[:2] - start[:2]))), abs(goal[2] - start[2])
        T = max(1.5 * dist / BASE_SPEED, 1.5 * turn / BASE_TURN, math.sqrt(6 * dist / 1.0), math.sqrt(6 * turn / 2.0), 0.2)   # speed and acceleration limits
        n = int(T / DT)
        blocked = False
        for i in range(1, n + 1):
            s = i / n
            s = s * s * (3 - 2 * s)
            tgt = start + (goal - start) * s
            for u, v in zip(self.base_u, tgt):
                d.ctrl[u] = v
            self._steps(1)
            now = self.base_pose()
            if np.hypot(*(now[:2] - tgt[:2])) > 0.12 or abs(now[2] - tgt[2]) > 0.35:
                blocked = True
                break
        if blocked:
            for u, v in zip(self.base_u, self.base_pose()):
                d.ctrl[u] = v
        self._steps(int(0.5 / DT))
        now = self.base_pose()
        ok = not blocked and np.hypot(*(now[:2] - goal[:2])) < 0.02 and abs(now[2] - goal[2]) < 0.03
        return dict(reached=bool(ok), **self._robot_state())

    def set_torso(self, height: float) -> dict:
        self._begin("set_torso", height=height)
        h = float(np.clip(height, 0.0, 0.34))
        now = float(self.d.qpos[self.torso_q])
        n = max(int(abs(h - now) / TORSO_SPEED / DT), 1)
        for i in range(1, n + 1):
            self.d.ctrl[self.torso_u] = now + (h - now) * i / n
            self._steps(1)
        self._steps(int(0.3 / DT))
        return self._robot_state()

    def look(self, pan: float, tilt: float) -> dict:
        self._begin("look", pan=pan, tilt=tilt)
        self.d.ctrl[self.head_u[0]] = float(np.clip(pan, -1.2, 1.2))
        self.d.ctrl[self.head_u[1]] = float(np.clip(tilt, -0.98, 0.72))
        self._steps(int(0.8 / DT))
        return self._robot_state()

    def _yaw_goal(self, arm: str, yaw: float) -> float:
        start = self.hand_pose(arm)[3]
        goal = start + _wrap(yaw - start)
        if abs(goal - start) > math.pi / 2:               # the two fingers are interchangeable
            goal -= math.copysign(math.pi, goal - start)
        return goal

    def can_reach(self, arm: str, x: float, y: float, z: float, yaw: float) -> dict:
        """Would this hand get there from where the robot stands, palm down, along a straight line? Worked out
        on the arm's kinematics alone (joint ranges, link lengths): nothing moves and no robot time passes.
        It knows nothing about obstacles."""
        k = self._ref
        k.qpos[:] = self.d.qpos
        mujoco.mj_kinematics(self.m, k)
        mujoco.mj_comPos(self.m, k)
        qa = self.arm_q[arm]
        lo, hi = self.arm_lim[arm][:, 0] + 0.01, self.arm_lim[arm][:, 1] - 0.01
        sid = self.site[arm]
        start = np.r_[k.site_xpos[sid], self.hand_pose(arm)[3]]
        goal = np.array([x, y, z, self._yaw_goal(arm, yaw)])
        steps = max(8, int(np.linalg.norm(goal[:3] - start[:3]) / 0.02), int(abs(goal[3] - start[3]) / 0.08))
        for i in range(1, steps + 1):
            for _ in range(10 if i < steps else 80):
                k.qpos[qa] = np.clip(k.qpos[qa] + self._ik_dq(k, arm, start + (goal - start) * i / steps) * 0.05, lo, hi)
                mujoco.mj_kinematics(self.m, k)
                mujoco.mj_comPos(self.m, k)
        R = k.site_xmat[sid].reshape(3, 3)
        off = float(np.linalg.norm(k.site_xpos[sid] - goal[:3]))
        yaw_off = abs(_wrap(math.atan2(R[1, 1], R[0, 1]) - goal[3]))
        yaw_off = min(yaw_off, abs(yaw_off - math.pi))
        level = bool(R[2, 2] < -0.985)
        ok = off < 0.008 and yaw_off < 0.08 and level
        why = None
        if not ok:
            why = ("the arm cannot bring the hand to that point from where the base stands" if off >= 0.008
                   else "the hand gets there but cannot turn its fingers to that direction there" if yaw_off >= 0.08
                   else "the hand gets there but not with the palm level")
        return dict(reachable=bool(ok), closest_m=round(off, 3), why=why)

    def move_arm(self, arm: str, x: float, y: float, z: float, yaw: float) -> dict:
        """Straight-line move of one hand (the point between its fingers), palm down, to (x, y, z) in room
        coordinates while turning the closing direction of the fingers to `yaw`. A target the arm cannot
        reach from where the base stands is refused before anything moves."""
        self._begin("move_arm", arm=arm, x=x, y=y, z=z, yaw=yaw)
        check = self.can_reach(arm, x, y, z, yaw)
        if not check["reachable"]:
            return dict(reached=False, moved=False, error_m=round(float(np.linalg.norm(self.hand_pose(arm)[:3] - np.array([x, y, z]))), 3),
                        why=check["why"] + "; nothing moved and no robot time was used", **self._robot_state())
        start = self.hand_pose(arm)
        yaw_goal = self._yaw_goal(arm, yaw)
        goal = np.array([x, y, z, yaw_goal])
        dist = float(np.linalg.norm(goal[:3] - start[:3]))
        T = max(dist / ARM_SPEED, abs(goal[3] - start[3]) / ARM_TURN, 0.2)
        # The target runs along the line at ARM_SPEED but waits for the hand: the arm's joints have torque
        # limits, and a target that runs ahead of them pulls the hand off the line. A hand that stops
        # following (something is in the way) ends the move.
        along, stalled = 0.0, 0
        while along < 1.0 and stalled < int(1.0 / DT):
            target = start + (goal - start) * along
            lag = float(np.linalg.norm(self.hand_pose(arm)[:3] - target[:3]))
            rate = float(np.clip((0.012 - lag) / 0.008, 0.0, 1.0))        # full speed within 4 mm of the target, waiting at 12 mm
            stalled = stalled + 1 if rate < 0.05 else 0
            along = min(1.0, along + rate * DT / T)
            self.arm_goal[arm] = start + (goal - start) * along
            self._steps(1)
        self.arm_goal[arm] = start + (goal - start) * along
        self._steps(int(0.5 / DT))
        end = self.hand_pose(arm)
        err = float(np.linalg.norm(end[:3] - goal[:3]))
        self.qtarget[arm] = self.d.qpos[self.arm_q[arm]].copy() if err > 0.03 else self.qtarget[arm]
        self.arm_goal[arm] = None
        yaw_err = abs(_wrap(end[3] - goal[3]))
        out = dict(reached=bool(err < ARRIVED and yaw_err < 0.12), moved=True, error_m=round(err, 3), **self._robot_state())
        if not out["reached"]:
            out["why"] = ("the hand was stopped on the way: it, or what it holds, is against something" if err >= ARRIVED
                          else f"the position was reached but the fingers ended {yaw_err:.2f} rad from the direction asked")
        return out

    def home_arm(self, arm: str) -> dict:
        """Bring one arm back to its ready posture (hand in front of the chest, palm down), joint by joint."""
        self._begin("home_arm", arm=arm)
        self.arm_goal[arm] = None
        start = self.d.qpos[self.arm_q[arm]].copy()
        n = max(int(float(np.max(np.abs(READY[arm] - start))) / 0.8 / DT), int(0.5 / DT))
        for i in range(1, n + 1):
            s = i / n
            self.qtarget[arm] = start + (READY[arm] - start) * (s * s * (3 - 2 * s))
            self._steps(1)
        self._steps(int(0.5 / DT))
        err = float(np.max(np.abs(self.d.qpos[self.arm_q[arm]] - READY[arm])))
        return dict(reached=bool(err < 0.08), **self._robot_state())

    def _set_fingers(self, arm: str, each: float):
        for u in self.fing_u[arm]:
            self.d.ctrl[u] = each

    def grasp(self, arm: str) -> dict:
        """Close the fingers. A tool is taken when the hand, palm down, is on its handle with the fingers
        closing across it."""
        self._begin("grasp", arm=arm)
        d = self.d
        took, why = None, None
        if self.holding[arm] is not None:
            why = f"this hand already holds the {self.holding[arm]}"
        else:
            R = d.site_xmat[self.site[arm]].reshape(3, 3)
            why = f"no handle within {GRASP_REACH * 100:.1f} cm of the hand position"
            for t in TOOLS:
                if t in self.holding.values():
                    continue
                gap = float(np.linalg.norm(d.site_xpos[self.grip[t]] - d.site_xpos[self.site[arm]]))
                handle_axis = d.site_xmat[self.grip[t]].reshape(3, 3)[:, 0]
                if gap >= GRASP_REACH:
                    continue
                if R[2, 2] >= -0.8:
                    why = "a handle is at the hand, but the palm is not level"
                elif abs(float(R[:, 1] @ handle_axis)) >= 0.5:
                    why = "a handle is at the hand, but the fingers close along it instead of across it: turn the hand a quarter turn"
                else:
                    took = t
                    break
        if took:                      # attach first: closing fingers would otherwise shove a light tool round before it is held
            self._weld(arm, took)
            self.holding[arm] = took
            self._mark(took + "_in_hand")
        self._set_fingers(arm, 0.012 if took else 0.0)
        self._steps(int(0.7 / DT))
        out = dict(holding=self.holding[arm], took=took, **self._robot_state())
        if took is None:
            out["why"] = why + ". The fingers cannot hold loose things such as trash; only the brush and the bin can be taken, by their handles"
        return out

    def _weld(self, arm: str, tool: str):
        d, m = self.d, self.m
        i, hb, tb = self.eq[(arm, tool)], self.hand_body[arm], self.bid[tool]
        R1 = d.xmat[hb].reshape(3, 3)
        neg, rel = np.zeros(4), np.zeros(4)
        mujoco.mju_negQuat(neg, d.xquat[hb])
        mujoco.mju_mulQuat(rel, neg, d.xquat[tb])
        m.eq_data[i, 0:3] = 0.0
        m.eq_data[i, 3:6] = R1.T @ (d.xpos[tb] - d.xpos[hb])
        m.eq_data[i, 6:10] = rel
        m.eq_data[i, 10] = 1.0
        d.eq_active[i] = 1

    def release(self, arm: str) -> dict:
        self._begin("release", arm=arm)
        t = self.holding[arm]
        if t:
            self.d.eq_active[self.eq[(arm, t)]] = 0
            self.holding[arm] = None
        self._set_fingers(arm, FINGER_OPEN)
        self._steps(int(0.6 / DT))
        return dict(released=t, **self._robot_state())

    # ---- cameras ---------------------------------------------------------------------------------
    def camera(self, name: str = "head", width: int = 640, height: int = 480, depth: bool = True, all_walls: bool = True) -> dict:
        """Colour image, depth in metres, and the calibration needed to turn a pixel and its depth into a
        point in room coordinates: X = cam_pos + cam_rot @ ((u - cx) / f * z, -(v - cy) / f * z, -z)."""
        m, d = self.m, self.d
        if self._renderer is None or (self._renderer.width, self._renderer.height) != (width, height):
            self._renderer = mujoco.Renderer(m, height, width)
        r = self._renderer
        opt = mujoco.MjvOption()
        opt.geomgroup[2] = 1 if all_walls else 0
        r.update_scene(d, camera=name, scene_option=opt)
        rgb = r.render().copy()
        out = dict(rgb=rgb)
        cid = m.camera(name).id
        f = 0.5 * height / math.tan(math.radians(float(m.cam_fovy[cid])) / 2)
        out["calibration"] = dict(f=round(f, 2), cx=width / 2, cy=height / 2,
                                  cam_pos=[round(float(v), 4) for v in d.cam_xpos[cid]],
                                  cam_rot=[[round(float(v), 5) for v in row] for row in d.cam_xmat[cid].reshape(3, 3)])
        if depth:
            r.enable_depth_rendering()
            r.update_scene(d, camera=name, scene_option=opt)
            out["depth"] = r.render().copy()
            r.disable_depth_rendering()
        return out

    def pixel_point(self, name: str, u: float, v: float, width: int = 640, height: int = 480) -> dict:
        """Depth at pixel (u = column from the left, v = row from the top) and the room point seen there."""
        if not (0 <= u <= width - 1 and 0 <= v <= height - 1):
            raise ValueError(f"pixel outside the image: u in 0..{width - 1}, v in 0..{height - 1}")
        key = (name, width, height, self._tick)
        if getattr(self, "_depth_key", None) != key:           # the world has not moved: reuse the last depth image
            self._depth_cache, self._depth_key = self.camera(name, width, height, depth=True), key
        c = self._depth_cache
        cal = c["calibration"]
        z = float(c["depth"][int(round(v)), int(round(u))])
        X = np.array(cal["cam_pos"]) + np.array(cal["cam_rot"]) @ np.array([(u - cal["cx"]) / cal["f"] * z, -(v - cal["cy"]) / cal["f"] * z, -z])
        return dict(depth_m=round(z, 4), x=round(float(X[0]), 4), y=round(float(X[1]), 4), z=round(float(X[2]), 4))

    # ---- one entry point for a front end: errors come back as data ---------------------------------
    CALLABLE = ("get_task", "observe", "drive_to", "move_arm", "can_reach", "home_arm", "grasp", "release", "look", "set_torso")

    def call(self, tool: str, **args) -> dict:
        if tool not in self.CALLABLE:
            return dict(ok=False, error=f"unknown tool {tool}")
        if "arm" in args and args["arm"] not in ARMS:
            return dict(ok=False, error="arm must be 'left' or 'right'")
        for k, v in args.items():
            if k != "arm" and not (isinstance(v, (int, float)) and math.isfinite(v)):
                return dict(ok=False, error=f"{k} must be a finite number")
        if tool in ("get_task", "observe"):
            if self.closed:
                return dict(ok=False, error="the episode is over")
            return dict(ok=True, **getattr(self, tool)())
        try:
            return dict(ok=True, **getattr(self, tool)(**args))
        except RuntimeError as e:
            return dict(ok=False, error=str(e), time_left_s=round(max(TIME_LIMIT - self.robot_time, 0.0), 1))

    # ---- for the dashboard and tests: put a thing somewhere by hand --------------------------------
    def place(self, name: str, where: str, slot: int = 0):
        """Teleport an item (not a legal move for the agent; used to show how end states are scored)."""
        d = self.d
        q, v = self.qadr[name], self.vadr[name]
        h = S.KINDS[self.items[name]["kind"]]["h"] if name in self.items else 0.0
        if where == "in_bin":
            R = d.xmat[self.bid["bin"]].reshape(3, 3)
            big = S.KINDS[self.items[name]["kind"]]["r"] > 0.07
            ox = 0.0 if big else (-0.07, 0.07, 0.0)[slot % 3]
            oy = 0.0 if big else (-0.03, 0.03)[slot % 2]
            p = self._pos("bin") + R @ np.array([ox, oy, 0.02 + 0.027 * slot + h])      # one above the other, they drop and settle
            d.qpos[q + 3:q + 7] = d.xquat[self.bid["bin"]]
        elif where == "on_floor":
            s = S.SURFACES[self.items[name]["surface"]]
            p = np.array([self.start[name][0], s["y"][0] - 0.18 - 0.06 * (slot % 3), h + 0.01])
        elif where == "start":
            p = self.start[name] + np.array([0, 0, 0.004])
        else:
            raise ValueError(where)
        d.qpos[q:q + 3] = p
        d.qvel[v:v + 6] = 0
        mujoco.mj_forward(self.m, d)

    def place_tool(self, tool: str, x: float, y: float, z: float, yaw: float = 0.0, tipped: bool = False):
        d = self.d
        q, v = self.qadr[tool], self.vadr[tool]
        quat = np.zeros(4)
        if tipped:
            mujoco.mju_euler2Quat(quat, np.array([math.pi / 2, 0.0, yaw]), "xyz")
        else:
            mujoco.mju_euler2Quat(quat, np.array([0.0, 0.0, yaw]), "xyz")
        d.qpos[q:q + 3] = (x, y, z)
        d.qpos[q + 3:q + 7] = quat
        d.qvel[v:v + 6] = 0
        mujoco.mj_forward(self.m, d)

    def save(self) -> dict:
        d = self.d
        return dict(qpos=d.qpos.copy(), qvel=d.qvel.copy(), ctrl=d.ctrl.copy(), eq_active=d.eq_active.copy(), eq_data=self.m.eq_data.copy(),
                    holding=dict(self.holding), qtarget={a: q.copy() for a, q in self.qtarget.items()},
                    milestones=dict(self.milestones), touched=set(self.touched), robot_time=self.robot_time, log=list(self.log))

    def load(self, st: dict):
        d = self.d
        d.qpos[:], d.qvel[:], d.ctrl[:], d.eq_active[:] = st["qpos"], st["qvel"], st["ctrl"], st["eq_active"]
        self.m.eq_data[:] = st["eq_data"]
        self.holding, self.qtarget = dict(st["holding"]), {a: q.copy() for a, q in st["qtarget"].items()}
        self.milestones, self.touched, self.robot_time, self.log = dict(st["milestones"]), set(st["touched"]), st["robot_time"], list(st["log"])
        self.arm_goal = {a: None for a in ARMS}
        self.closed = False
        mujoco.mj_forward(self.m, d)

    def rest(self, seconds: float = 1.5):
        self._steps(int(seconds / DT), count=False)


def _obstacles() -> list:
    """Footprints (x and y ranges, height) of everything fixed that the base or an arm can run into."""
    t, so, sh = S.TABLE, S.SOFA, S.STATION["shelf"]
    x1, y1 = S.ROOM["x"][1], S.ROOM["y"][1]
    box = lambda name, x0, xb, y0, yb, h: dict(name=name, x=[round(x0, 3), round(xb, 3)], y=[round(y0, 3), round(yb, 3)], height=h)
    return [
        box("coffee table", t["cx"] - t["hx"], t["cx"] + t["hx"], t["cy"] - t["hy"], t["cy"] + t["hy"], t["top"]),
        box("sofa (seat, arms and back)", so["cx"] - so["hx"] - 0.16, so["cx"] + so["hx"] + 0.16, so["cy"] - so["hy"], y1, 0.82),
        box("tool shelf", sh["cx"] - sh["hx"], sh["cx"] + sh["hx"], sh["cy"] - sh["hy"], sh["cy"] + sh["hy"], sh["top"]),
        box("TV console", x1 - 0.44, x1, -0.90, 0.50, 1.13),
        box("plant", x1 - 0.51, x1 - 0.19, 1.29, 1.61, 1.10),
        box("floor lamp", S.ROOM["x"][0] + 0.22, S.ROOM["x"][0] + 0.48, 1.32, 1.58, 1.62),
    ]


def dumps(o) -> str:
    return json.dumps(o, separators=(",", ":"))
