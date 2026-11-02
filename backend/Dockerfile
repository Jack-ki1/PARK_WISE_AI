FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /srv

# Non-root runtime user. The named data volume is chowned via the image-side
# directory created below (Docker seeds a fresh volume with this ownership).
RUN useradd --create-home --uid 10001 parkwise \
    && mkdir -p /srv/data/uploads /srv/data/processed /srv/data/previews /srv/data/streams \
    && chown -R parkwise:parkwise /srv/data

# Build context is the repo root (see docker-compose.yml) so the admin bootstrap
# script ships with the image: with auth enabled it is how the first key is minted.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt
COPY backend/app ./app
COPY scripts ./scripts

USER parkwise
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
