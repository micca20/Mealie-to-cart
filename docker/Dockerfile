FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
  && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
COPY mealie_to_cart /app/mealie_to_cart

RUN pip install --no-cache-dir -U pip \
  && pip install --no-cache-dir requests playwright

# We connect to a remote browser (Kasm/Browserless) over CDP — no local browsers needed.

ENTRYPOINT ["python", "-u", "-m", "mealie_to_cart"]
