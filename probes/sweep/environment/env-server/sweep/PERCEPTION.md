# Camera pipeline (perception.py): section for the task README

**What it does.** `survey(world)` drives the robot to a few places around the coffee table and in front of
the sofa, takes head-camera pictures, and lists what lies on each surface: position (middle of the
footprint), length, width, orientation, height, colour, and a judgement (kind; trash, personal item or
tool; confidence). `locate_tools(world)` finds where to hold the brush and the bin at the tool station.
Both use only what the standard setting gives an agent: the head camera's colour picture, depth and
calibration, the robot's own state, the floor plan. Driving goes through a small planner that keeps the
base and arms clear of the furniture in the floor plan.

- **Colour and depth (default).** Every pixel becomes a point in the room. A thing is the set of points
  3 mm or more above a known surface, grouped on a 5 mm top-down grid.
- **Colour only (`depth=False`, for the ablation).** A pixel's viewing ray is met with the plane of the
  surface (height from the floor plan). Pixels are split into bare surface and things by colour. A thing
  that stands up leaves a tail behind it in each picture; a spot counts as footprint only if no picture
  shows it bare. Where only one side is reachable (the sofa), the tail is cut off using how high that
  kind of thing stands.
- **Judging what a thing is.** Nearest examples in `perception_model.json` (size, height, colours), one
  table per mode, built by `perception_eval.py --train` from rooms with seeds 1000 and up. Ground truth is
  read only in `perception_eval.py`.

**Measured** (seeds 1 to 40, levels 1 to 3; 117 rooms, 760 things; three level-3 rooms cannot be generated
and are skipped; `python -m sweep.perception_eval --eval [--colour-only]`):

| | Colour and depth | Colour only |
|---|---|---|
| Things found | 760 of 760 | 757 of 760 |
| Rooms with everything found | 100% | 97.4% |
| False detections per room | 0.01 | 0.36 (loose pieces of a real thing, next to it) |
| Position error, median / mean / 95th percentile | 0.9 / 1.7 / 5.2 mm | 3.0 / 7.5 / 29 mm |
| Within the brush's 5 cm tolerance | 99.9% | 98.3% |
| Trash or personal item judged right | 100% | 99.7% |
| Kind right | 99.7% | 98.7% |
| Pictures per survey / robot time | 5.5 / 47 s | 12 / 84 s |

Tool handles (colour and depth): found in 27 of 27 cases including tools put down up to 10 cm and 30
degrees differently; error 6 to 7 mm, worst 16 mm; all within the grasp's 3.5 cm reach and direction.
Colour only: fine where the tools start (brush 10 mm, bin 2 mm), unreliable for the bin when it stands
elsewhere (18 of 24).

**Limits.**
- The survey needs empty hands. With the brush and the bin in the hands there is no place in this room
  from which the robot can face a surface without the tools reaching into the furniture, and the survey
  returns no pictures. Survey first, or put the tools down.
- It assumes the arms are in their rest posture.
- A strip behind anything that stands up is hidden from the front of the sofa; `unseen` reports the share.
- Colour only: positions on the sofa are worse (things that stand up: 1 to 3 cm, up to 7 cm), glasses and
  apple cores come out in pieces (their middle parts do not touch the surface), a dark thing lying against
  the jacket merges with it.
- The middle of a footprint is not the body's origin for lopsided things (jacket, glasses, keys).
- Something of the robot's own lying on a surface (the brush) is judged like any thing unless its place
  is passed in `ignore`.
