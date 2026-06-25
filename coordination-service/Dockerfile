FROM python:3.11-slim-bookworm

WORKDIR /app

COPY docker/install-libredwg.sh /tmp/install-libredwg.sh
RUN chmod +x /tmp/install-libredwg.sh \
  && apt-get update \
  && apt-get install -y --no-install-recommends libffi-dev libssl-dev pkg-config \
  && /tmp/install-libredwg.sh \
  && rm /tmp/install-libredwg.sh

# Install coordination-service deps
COPY coordination-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY coordination-service/ .

# Copy bundled motor (coordination engine)
COPY motor/ /motor/

ENV PYTHONPATH=/motor:/app
ENV DUPLA_ROOT=/motor

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
