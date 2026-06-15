FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    pkg-config \
  && rm -rf /var/lib/apt/lists/*

# Install coordination-service deps
COPY coordination-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY coordination-service/ .

# Copy bundled motor (coordination engine + aps_integration)
COPY motor/ /motor/

ENV PYTHONPATH=/motor:/app
ENV DUPLA_ROOT=/motor

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
