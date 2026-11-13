# =========================
# Build stage
# =========================
FROM node:20.11.1-alpine3.19 AS builder
WORKDIR /app

RUN apk update && apk upgrade --no-cache
# RUN npm install --package-lock-only

COPY package.json ./
RUN npm install

# COPY package.json package-lock.json ./
# RUN npm ci

COPY . .
RUN npm run build

# =========================
# Runtime stage (DISTROLESS)
# =========================
FROM gcr.io/distroless/nodejs20-debian12
WORKDIR /app

# Copy standalone output only
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public


ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV TMPDIR=/tmp
ENV HOST=0.0.0.0
ENV PORT=3000


# Distroless requires numeric UID
USER 10002

EXPOSE 3000
CMD ["server.js"]
