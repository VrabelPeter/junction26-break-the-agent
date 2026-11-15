# Can you see pictures?

This is a check of whether camera pictures reach you. The MCP server `env` has
three pictures, each 320x240 with three coloured shapes on a light background.
Colours: red, green, blue, yellow, black. Shapes: square, circle, triangle.

Do all three, in this order:

1. Call the tool `look_image_only`. Then call
   `answer(route="image_only", description=...)`.
2. Call the tool `look_image_and_text`. Then call
   `answer(route="image_and_text", description=...)`.
3. Download the third picture with
   `curl -s http://env-server:8000/camera.png -o /app/camera.png`,
   open `/app/camera.png` with your file reading tool so that you see it, then
   call `answer(route="file", description=...)`.

The description lists the three shapes from left to right, like
`red square, blue circle, yellow triangle`.

Important: describe only what you actually see. Do **not** analyse the pixels
with code and do not guess. If a picture did not reach you (you got only text,
an error, or nothing), answer `cannot see` for that route and say in your final
message exactly what you received instead.
