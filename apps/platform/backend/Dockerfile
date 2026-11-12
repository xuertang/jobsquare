# API image. Build context is apps/ (the parent of platform/), so the image
# can carry the scraper it calls and runs anywhere without bind mounts:
#
#   docker build -f platform/backend/Dockerfile apps/
#
# The apply worker is not in here: it needs a visible browser and runs on
# your own machine (python -m worker).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    COPILOT_DATA_DIR=/data COPILOT_SCRAPER_DIR=/scraper HOME=/tmp

RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY platform/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY platform/backend/copilot ./copilot
# The existing scraper: only the four files the app reads.
COPY job-ops/fetchers.py job-ops/models.py job-ops/notify.py job-ops/sources.yaml /scraper/

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "copilot.main:app", "--host", "0.0.0.0", "--port", "8000"]
