# Shape board

You control a robot arm through the MCP server `robot`. The job is a shape-sorting
board: **6 pegs** (star, rectangle, triangle, square, cross, hexagon, in an order
`get_task` gives), each to be pushed into its own matching hole and seated at the
bottom. Nothing useful is in the local filesystem.

For every peg the arm already holds the peg upright, 3 mm above the spot where a
camera thinks the hole is. The camera is not exact: the real hole is up to
**2 mm** away, turned by up to **4 degrees**, and the board surface is up to
0.5 mm higher or lower than estimated. That error is fixed while you work on a
peg and different for every peg. The peg fits its hole with **0.2 mm** to spare
on every side, so the camera estimate is not good enough: you find the hole by
what the wrist feels.

## Score (0 to 1)

Each peg is scored where it is when you call `next_peg` (or when you stop):

| Outcome | Score |
|---|---|
| Seated at the bottom of its hole | 1.0 |
| In the hole but not seated | 0.5 x depth / 8 mm |
| Not in the hole | 0.0 |
| Board damaged while working on this peg | 0.0, whatever else happens |

The score of the job is the mean over the 6 pegs. A peg you never started scores 0.

## Tools

| Tool | What it does |
|---|---|
| `get_task()` | Everything known in advance: the pegs and their outlines, and every constant mentioned below |
| `observe()` | The latest reading again. Free. It is the same reading, not a new measurement |
| `move(dx, dy, dz, dyaw, max_force)` | One guarded move relative to where the arm is: at most 5 mm in total and 5 degrees. The arm stops early (event `force limit reached`) as soon as going further would push the contact force above `max_force` (1 to 25 N). Costs one move. Returns the new reading |
| `next_peg()` | Closes this peg as it stands and picks up the next one. Cannot be undone. After the sixth peg the job is over |

You have **24 moves per peg**; unused moves are lost. A refused move (out of
range, too long) costs nothing and says why.

## The reading

```
tool    x, y, z, yaw     where the arm holds the peg
wrench  fx, fy, fz       force the board puts on the peg, newtons
        tx, ty, tz       torque the board puts on the peg about the centre of its tip, newton-millimetres
moved   dx, dy, dz, dyaw what the last move really achieved
seated, events, moves_left, peg, shape
```

- Millimetres, degrees, newtons. `x`, `y`, `yaw` are relative to the camera's
  estimate: `(0, 0, 0)` is exactly where the camera thinks the hole is. `z` is
  the height of the peg tip above the estimated board surface; negative is below it.
- The `x` and `y` axes are fixed to the board and do not turn with the peg.
  `yaw` is counter-clockwise seen from above. Forces and torques use the same axes.
- `fz` is positive when the board pushes up, that is, when you are pressing down.
- The wrist between arm and peg is a spring: 10 N/mm vertically, 15 N/mm
  sideways, 60 N mm per degree of twist. `tool` is the arm. Under load the peg
  is not exactly where the arm is; the wrench divided by the stiffness says by how much.
- Sensor noise: 0.02 mm, 0.05 degrees, 0.1 N, 2 N mm. One reading per move.
- Nothing tells you directly whether the peg stands on the board or is in the
  hole. `z` and the wrench do.

## What the peg does

**In the air** the wrench is zero (plus noise).

**On the board.** Going down, the peg lands on the board face unless it fits the
hole. The arm keeps going and compresses the wrist until the force reaches
`max_force`. The board carries the peg where the peg's rim overhangs the edge of
the hole, more strongly where it overhangs further. `tx` and `ty` tell you where
that is: the centre of support, relative to the centre of the peg, is

```
cx = -ty / fz        cy = tx / fz
```

A peg that sits to one side of its hole is supported on that side. A peg that is
centred over the hole but turned is supported all the way round, and the centre
of support is near zero. With an offset and a turn together, the centre of
support need not lie exactly in the direction of the offset.

**Pressing harder than 15 N on the board face damages the board.** You choose
`max_force` on every move, so this is your decision.

**Dropping in.** The peg drops into the hole when it fits. It also drops in when
it nearly fits: the mouth of the hole has a 0.5 mm chamfer, and if the peg
overhangs by no more than that anywhere, the chamfer pushes the peg into place
against the wrist springs. That takes a side load of

```
15 N/mm x sideways shift needed  +  4 N/degree x turn needed
```

and the chamfer delivers at most **0.6 x the force you press with**. So a
stronger press pulls the peg in from further away. A peg that is being dragged
or turned across the board does not drop in on the way; whether it drops is
decided where the move ends, or during a move that only goes straight down.

**On the chamfer but not in.** If the overhang is within the chamfer everywhere
but the press is too weak to bend the wrist that far, `fx`, `fy` and `tz` show
the correction that is missing. For a missing shift `(sx, sy)` mm and a missing
turn `a` degrees:

```
fx = 15 sx g      fy = 15 sy g      tz = 60 a g      g = 0.6 fz / (15 |s| + 4 |a|)
```

Further away than the chamfer, `fx`, `fy` and `tz` are zero on the board face.

**In the hole.** The walls hold the peg. If the arm is not straight above it,
the wrist springs are loaded and you feel it: `fx`, `fy` are 15 N per mm that
the walls hold the peg away from where the arm wants it, `tz` is 60 N mm per
degree. Moving the arm by `(fx / 15, fy / 15)` and turning it by `tz / 60`
relaxes the springs. Going down costs friction, `0.5 N + 0.6 x side load`, where
the side load is `|fx, fy| + |tz| / 15`. The arm stops when `fz` and the side
load together (root of the sum of squares) reach `max_force`. `tx` and `ty` are
zero in the hole.

**Seating.** The hole is 8 mm deep. Pressing the peg against the bottom with at
least 5 N seats it: the reading says `seated: true` and the event `peg seated`.
A seated peg cannot be moved any more; call `next_peg`.

## Limits

- One move: at most 5 mm (`dx`, `dy`, `dz` together) and 5 degrees.
- Working range: `x`, `y` within 10 mm of the estimate, `yaw` within 15 degrees,
  `z` from -14 to 15.
- `max_force` from 1 to 25 N.
