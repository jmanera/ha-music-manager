# Build context: the repository root (CI) or the bundle produced by `make app-bundle`.
# Not BUILD_FROM: recent Supervisors ignore build.yaml and pass an Alpine base image, while the
# slskd binaries we ship are glibc builds.
ARG PYTHON_IMAGE=python:3.13-slim-bookworm
ARG SLSKD_VERSION=0.26.2

FROM node:20-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build

FROM ${PYTHON_IMAGE} AS slskd
ARG SLSKD_VERSION
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip \
    && case "$(uname -m)" in \
         x86_64) arch=x64 ;; \
         aarch64) arch=arm64 ;; \
         *) echo "unsupported arch $(uname -m)" && exit 1 ;; \
       esac \
    && curl -fsSL -o /tmp/slskd.zip \
       "https://github.com/slskd/slskd/releases/download/${SLSKD_VERSION}/slskd-${SLSKD_VERSION}-linux-${arch}.zip" \
    && unzip -q /tmp/slskd.zip -d /opt/slskd \
    && chmod +x /opt/slskd/slskd

FROM ${PYTHON_IMAGE} AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY --from=ui /ui/dist ./src/ha_music_manager/static
RUN uv sync --frozen --no-dev --no-editable

FROM ${PYTHON_IMAGE}
ARG SLSKD_VERSION
COPY --from=slskd /opt/slskd /opt/slskd
COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HMM_INGRESS_ONLY=true
LABEL io.hass.type="addon" \
      io.hass.version="0.1.0" \
      org.opencontainers.image.source="https://github.com/jmanera/ha-music-manager" \
      org.opencontainers.image.description="Soulseek music search for Home Assistant (slskd ${SLSKD_VERSION})" \
      org.opencontainers.image.licenses="MIT"
WORKDIR /data
CMD ["ha-music-manager"]
