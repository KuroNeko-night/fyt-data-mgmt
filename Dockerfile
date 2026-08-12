# Dockerfile 保留标准官方源，便于 GitHub Actions 和普通 ``docker build`` 使用；Compose
# 可按部署网络通过构建参数覆盖为公开镜像或组织内部镜像仓库。
ARG NODE_IMAGE=node:22-bookworm-slim
ARG PYTHON_IMAGE=python:3.13-slim-bookworm
ARG NPM_REGISTRY=https://registry.npmjs.org
ARG PIP_INDEX_URL=https://pypi.org/simple

FROM ${NODE_IMAGE} AS web-build
ARG NPM_REGISTRY
WORKDIR /src
COPY web-app/package.json web-app/package-lock.json ./web-app/
RUN npm --prefix web-app ci --no-audit --no-fund --registry="${NPM_REGISTRY}"
COPY web-app ./web-app
RUN npm --prefix web-app run build

FROM ${PYTHON_IMAGE} AS runtime
ARG PIP_INDEX_URL
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8 \
    FYT_WEB_HOST=0.0.0.0 \
    FYT_WEB_PORT=8787 \
    FYT_WEB_DATA=/data \
    HOME=/data
WORKDIR /app
COPY requirements-runtime.txt /tmp/requirements-runtime.txt
RUN pip install --no-cache-dir --disable-pip-version-check \
        --index-url "${PIP_INDEX_URL}" --timeout 60 --retries 4 \
        -r /tmp/requirements-runtime.txt \
    && rm -f /tmp/requirements-runtime.txt
COPY core ./core
COPY web_backend ./web_backend
COPY web_server.py ./web_server.py
COPY assets ./assets
COPY --from=web-build /src/web-app/dist ./web-app/dist
RUN groupadd --system --gid 10001 fyt \
    && useradd --system --uid 10001 --gid 10001 --home-dir /data --no-create-home fyt \
    && mkdir -p /data \
    && chown -R fyt:fyt /app /data
USER fyt
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=3); raise SystemExit(0 if r.status == 200 else 1)"]
CMD ["python", "web_server.py"]
