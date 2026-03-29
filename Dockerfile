FROM node:20-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8443 \
    AGENT_PORT=8050 \
    AGENT_SSL=1 \
    PATCHPILOT_DATA_DIR=/data \
    PATCHPILOT_DB_PATH=/data/patchpilot.db \
    PATCHPILOT_ENV_FILE=/data/patchpilot.env \
    PATCHPILOT_SSL_DIR=/data/ssl \
    PATCHPILOT_STATIC_DIR=/opt/patchpilot/frontend/dist \
    PATCHPILOT_RESTART_MODE=process \
    PATCHPILOT_UVICORN_BIN=uvicorn

WORKDIR /opt/patchpilot

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    gosu \
    openssl \
  && groupadd --system --gid 10001 patchpilot \
  && useradd --system --uid 10001 --gid patchpilot --create-home --home-dir /home/patchpilot patchpilot \
  && rm -rf /var/lib/apt/lists/*

COPY server/ /opt/patchpilot/server/
COPY agent/ /opt/patchpilot/agent/
COPY --from=frontend-build /build/frontend/dist /opt/patchpilot/frontend/dist
COPY docker/entrypoint.sh /usr/local/bin/patchpilot-entrypoint.sh

RUN pip install --no-cache-dir -r /opt/patchpilot/server/requirements.txt \
  && chmod +x /opt/patchpilot/server/start.sh /usr/local/bin/patchpilot-entrypoint.sh \
  && chown -R patchpilot:patchpilot /opt/patchpilot

VOLUME ["/data"]
EXPOSE 8443 8050

ENTRYPOINT ["/usr/local/bin/patchpilot-entrypoint.sh"]
