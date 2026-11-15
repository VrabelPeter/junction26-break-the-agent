FROM python:3.12-slim
RUN pip install --no-cache-dir fastmcp==2.12.4 pillow==11.3.0
WORKDIR /srv
COPY server.py .
EXPOSE 8000
CMD ["python", "server.py"]
