FROM python:3.11-slim-bookworm

WORKDIR /app

COPY docker/install-libredwg.sh /tmp/install-libredwg.sh
RUN chmod +x /tmp/install-libredwg.sh \
  && apt-get update \
  && apt-get install -y --no-install-recommends libffi-dev libssl-dev fonts-dejavu-core fontconfig \
  && /tmp/install-libredwg.sh \
  && rm /tmp/install-libredwg.sh

COPY processor/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY processor/ .

ENV PYTHONUNBUFFERED=1 \
    DUPLA_CACHE_DIR=/app/cache \
    DUPLA_ARTIFACT_DIR=/app/artifacts \
    PYTHONPATH=/motor:/app

RUN mkdir -p /app/cache /app/artifacts /app/output

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
