# =========================
# Build stage
# =========================
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install packages into /app/python
RUN pip install --no-cache-dir \
    --target=/app/python \
    -r requirements.txt

COPY . .

# =========================
# Runtime stage (DISTROLESS)
# =========================
FROM gcr.io/distroless/python3-debian12

WORKDIR /app

COPY --from=builder /app /app

# Tell Python where packages are
ENV PYTHONPATH=/app/python

USER 10003

EXPOSE 5000

ENTRYPOINT ["/usr/bin/python3"]
CMD ["-m", "gunicorn", "-b", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
