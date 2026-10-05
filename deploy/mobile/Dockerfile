FROM node:22-bookworm-slim AS health-build
WORKDIR /build/ankang/route1-health-agent
COPY ankang/route1-health-agent/package.json ankang/route1-health-agent/package-lock.json ./
RUN npm ci
COPY ankang/route1-health-agent/src ./src
COPY ankang/route1-health-agent/scripts ./scripts
COPY ankang/route1-health-agent/tsconfig.bridge.json ./
RUN npm run build:bridge

FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 YOLO_OFFLINE=true YOLO_AUTOINSTALL=false
WORKDIR /opt/rehab
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libstdc++6 libgcc-s1 && rm -rf /var/lib/apt/lists/*
COPY mobile_rehab/requirements.txt /tmp/mobile-requirements.txt
COPY deploy/mobile/requirements.txt /tmp/inference-requirements.txt
COPY mobile_rehab/requirements.voice.txt /tmp/voice-requirements.txt
COPY mobile_rehab/requirements.ocr.txt /tmp/ocr-requirements.txt
ARG ENABLE_LOCAL_TEXT=1
RUN pip install torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r /tmp/mobile-requirements.txt -r /tmp/inference-requirements.txt
RUN if [ "$ENABLE_LOCAL_TEXT" = "1" ]; then pip install -r /tmp/voice-requirements.txt -r /tmp/ocr-requirements.txt; fi
COPY mobile_rehab /opt/rehab/mobile_rehab
COPY bridges /opt/rehab/bridges
COPY --from=health-build /usr/local/bin/node /usr/local/bin/node
COPY --from=health-build /build/ankang/route1-health-agent/.bridge-build /opt/rehab/ankang/route1-health-agent/.bridge-build
COPY ankang/route1-health-agent/scripts/product-local-store.cjs /opt/rehab/ankang/route1-health-agent/scripts/product-local-store.cjs
COPY rehab_codex_single_camera_v2_1/app /opt/rehab/rehab_codex_single_camera_v2_1/app
COPY rehab_codex_single_camera_v2_1/camera_reference.py /opt/rehab/rehab_codex_single_camera_v2_1/camera_reference.py
COPY rehab_codex_single_camera_v2_1/configs /opt/rehab/rehab_codex_single_camera_v2_1/configs
RUN useradd --uid 10001 --create-home rehab && mkdir -p .runtime/mobile rehab_codex_single_camera_v2_1/.runtime rehab_codex_single_camera_v2_1/assets/models && chown -R rehab:rehab /opt/rehab
USER rehab
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health',timeout=3)"
CMD ["python", "-m", "mobile_rehab.server", "--host", "0.0.0.0", "--port", "8765"]
