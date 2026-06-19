FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
  && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
  && pip install --no-cache-dir pymupdf ezdxf shapely requests

COPY backend/ .
COPY motor/ /motor/

RUN mkdir -p var/uploads var/coord_output/aps_cache

ENV PYTHONUNBUFFERED=1
ENV DUPLA_ROOT=/motor
ENV PYTHONPATH=/motor:/app
ENV COORDINATION_CACHE_ROOT=/app/var/coord_output/aps_cache

EXPOSE 8000

COPY backend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
