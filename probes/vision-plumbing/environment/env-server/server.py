"""Vision plumbing check: three pictures, three routes, the truth stays here."""
import io
import json
import os
import random
import time

from fastmcp import FastMCP
from fastmcp.tools.tool import ToolResult
from fastmcp.utilities.types import Image
from mcp.types import TextContent
from PIL import Image as PILImage, ImageDraw
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

COLOURS = {"red": (220, 30, 30), "green": (30, 160, 60), "blue": (30, 60, 220),
           "yellow": (240, 210, 20), "black": (20, 20, 20)}
SHAPES = ("square", "circle", "triangle")
ROUTES = ("image_only", "image_and_text", "file")

mcp = FastMCP("env")
SEED = int(os.environ.get("VISION_SEED", "1"))
LOG: list[dict] = []
ANSWERS: dict[str, str] = {}


def note(kind: str, **kw) -> None:
    LOG.append({"t": round(time.time(), 2), "kind": kind, **kw})


def make(route: str):
    rng = random.Random(f"{SEED}-{route}")
    truth, im = [], PILImage.new("RGB", (320, 240), (235, 235, 235))
    d = ImageDraw.Draw(im)
    for slot in range(3):
        colour, shape = rng.choice(list(COLOURS)), rng.choice(SHAPES)
        cx, cy, r = 55 + slot * 105 + rng.randint(-12, 12), rng.randint(60, 180), rng.randint(28, 38)
        if shape == "square":
            d.rectangle([cx - r, cy - r, cx + r, cy + r], fill=COLOURS[colour])
        elif shape == "circle":
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=COLOURS[colour])
        else:
            d.polygon([(cx, cy - r), (cx + r, cy + r), (cx - r, cy + r)], fill=COLOURS[colour])
        truth.append((colour, shape))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return truth, buf.getvalue()


PICS = {route: make(route) for route in ROUTES}


@mcp.tool()
def look_image_only() -> Image:
    """Camera picture 1 (320x240), returned as an image."""
    note("tool", name="look_image_only")
    return Image(data=PICS["image_only"][1], format="png")


@mcp.tool(output_schema=None)
def look_image_and_text():
    """Camera picture 2 (320x240), returned as an image together with a JSON text block."""
    note("tool", name="look_image_and_text")
    meta = json.dumps({"camera": "two", "width": 320, "height": 240, "note": "the image follows"})
    return ToolResult(content=[TextContent(type="text", text=meta),
                               Image(data=PICS["image_and_text"][1], format="png").to_image_content()])


@mcp.tool()
def answer(route: str, description: str) -> str:
    """Submit what you saw. route is one of: image_only, image_and_text, file.
    description lists the three shapes from left to right as 'colour shape, colour shape, colour shape',
    or 'cannot see' if no picture reached you."""
    note("answer", route=route, description=description)
    if route not in ROUTES:
        return f"unknown route; use one of {', '.join(ROUTES)}"
    ANSWERS[route] = description
    return "recorded"


def grade(route: str) -> int:
    words = ANSWERS.get(route, "").lower().replace(",", " ").replace(";", " ").replace(".", " ").split()
    found = []
    colour = None
    for w in words:
        if w in COLOURS:
            colour = w
        elif w in SHAPES and colour:
            found.append((colour, w))
            colour = None
    return sum(1 for got, want in zip(found, PICS[route][0]) if got == want)


@mcp.custom_route("/camera.png", methods=["GET"])
async def camera(request: Request) -> Response:
    note("http", path="/camera.png")
    return Response(PICS["file"][1], media_type="image/png")


@mcp.custom_route("/score", methods=["GET"])
async def score_route(request: Request) -> JSONResponse:
    per = {route: grade(route) for route in ROUTES}
    return JSONResponse({
        "score": sum(per.values()) / 9, "correct_of_3": per, "seed": SEED,
        "truth": {r: [" ".join(t) for t in PICS[r][0]] for r in ROUTES},
        "answers": ANSWERS, "log": LOG,
    })


@mcp.custom_route("/log", methods=["GET"])
async def log_route(request: Request) -> JSONResponse:
    return JSONResponse({"log": LOG, "answers": ANSWERS})


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
