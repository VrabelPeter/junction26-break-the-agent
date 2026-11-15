FROM python:3.12-slim-bookworm
# No GPU in the container: MuJoCo renders the robot's cameras in software through OSMesa.
RUN apt-get update && apt-get install -y --no-install-recommends libosmesa6 libgl1 libglx-mesa0 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir fastmcp==2.12.4 mujoco==4.0.1 numpy==2.5.4 pillow==13.0.0
ENV MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa
WORKDIR /srv
COPY assets ./assets
COPY sweep ./sweep
COPY server.py .
EXPOSE 8000
CMD ["python", "server.py"]
