FROM python:3.12-slim-bookworm

WORKDIR /app

COPY docker/install-libredwg.sh /tmp/install-libredwg.sh
RUN chmod +x /tmp/install-libredwg.sh \
  && apt-get update \
  && apt-get install -y --no-install-recommends libffi-dev libssl-dev fonts-dejavu-core fontconfig \
  && /tmp/install-libredwg.sh \
  && rm /tmp/install-libredwg.sh

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY motor/ /motor/

RUN mkdir -p var/uploads var/coord_output/cad_cache app/static

ENV PYTHONUNBUFFERED=1
ENV DUPLA_ROOT=/motor
ENV PYTHONPATH=/motor:/app
ENV COORDINATION_CACHE_ROOT=/app/var/coord_output/cad_cache

EXPOSE 8000

COPY backend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
