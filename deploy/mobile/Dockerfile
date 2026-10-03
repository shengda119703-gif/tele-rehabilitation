FROM python:3.13-slim-bookworm
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 YOLO_OFFLINE=true YOLO_AUTOINSTALL=false
WORKDIR /opt/rehab
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY mobile_rehab/requirements.txt /tmp/mobile-requirements.txt
COPY deploy/mobile/requirements.txt /tmp/inference-requirements.txt
RUN pip install torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r /tmp/mobile-requirements.txt -r /tmp/inference-requirements.txt
COPY mobile_rehab /opt/rehab/mobile_rehab
COPY rehab_codex_single_camera_v2_1/app /opt/rehab/rehab_codex_single_camera_v2_1/app
COPY rehab_codex_single_camera_v2_1/camera_reference.py /opt/rehab/rehab_codex_single_camera_v2_1/camera_reference.py
COPY rehab_codex_single_camera_v2_1/configs /opt/rehab/rehab_codex_single_camera_v2_1/configs
RUN useradd --uid 10001 --create-home rehab && mkdir -p .runtime/mobile rehab_codex_single_camera_v2_1/.runtime rehab_codex_single_camera_v2_1/assets/models && chown -R rehab:rehab /opt/rehab
USER rehab
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health',timeout=3)"
CMD ["python", "-m", "mobile_rehab.server", "--host", "0.0.0.0", "--port", "8765"]
