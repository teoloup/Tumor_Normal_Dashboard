FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY app/requirements.txt /app/app/requirements.txt

RUN pip install --no-cache-dir -r /app/app/requirements.txt

COPY app /app/app
COPY docker/docker_start.py /app/docker/docker_start.py
COPY README.md /app/README.md

RUN mkdir -p /app/app/local /app/docker /state /data \
    && python -c "import urllib.request; urllib.request.urlretrieve('https://cdn.jsdelivr.net/npm/igv@3.5.4/dist/igv.min.js', '/app/app/local/igv.min.js')"

EXPOSE 8501 8765

CMD ["python", "/app/docker/docker_start.py"]
