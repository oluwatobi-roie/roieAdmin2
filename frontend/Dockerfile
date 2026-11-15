# =========================
# Build stage
# =========================
FROM node:24-bookworm-slim AS builder
WORKDIR /app

ENV NEXT_TELEMETRY_DISABLED=1

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# =========================
# Runtime stage (DISTROLESS)
# =========================
FROM gcr.io/distroless/nodejs24-debian13
WORKDIR /app

# Copy standalone output only
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public


ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV TMPDIR=/tmp
ENV HOSTNAME=0.0.0.0
ENV PORT=3000


# Distroless requires numeric UID
USER 10002

EXPOSE 3000
CMD ["server.js"]
