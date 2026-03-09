FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY dashboard/requirements.txt /app/dashboard/requirements.txt

RUN pip install --no-cache-dir -r /app/dashboard/requirements.txt

COPY dashboard /app/dashboard
COPY README.md /app/README.md

RUN mkdir -p /app/dashboard/local /state /data \
    && python -c "import urllib.request; urllib.request.urlretrieve('https://cdn.jsdelivr.net/npm/igv@3.5.4/dist/igv.min.js', '/app/dashboard/local/igv.min.js')"

EXPOSE 8501 8765

CMD ["python", "/app/dashboard/docker_start.py"]
