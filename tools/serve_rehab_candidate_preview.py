"""Local-only, isolated TEST runner; never injected by the production server.
Run with the existing QA Python: --data-dir NEW_DIR --port 18971.
"""
import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--port', type=int, default=18971)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    data = args.data_dir.resolve()
    if data == repo or repo in data.parents:
        raise RuntimeError('TEST 数据目录必须在仓库外')
    marker = data / 'TEST-ONLY.txt'
    if data.exists() and any(data.iterdir()) and not marker.exists():
        raise RuntimeError('拒绝复用未标记目录')
    data.mkdir(parents=True, exist_ok=True)
    marker.write_text('仅康复候选图片内部预览，无真实患者或医学推理。\n', encoding='utf-8')
    os.environ['ANKANG_PRODUCT_DISABLE_MODEL'] = '1'
    os.environ['ANKANG_VOICE_DISABLED'] = '1'
    sys.path[:0] = [str(repo / 'rehab_codex_single_camera_v2_1'), str(repo)]
    import uvicorn
    from starlette.responses import Response
    from app.product.backend import ProductBackend
    from app.ui.product_dialogs import blank_health
    from mobile_rehab.unified import SharedProduct
    from mobile_rehab.server import create_app
    backend = ProductBackend(data / 'desktop')
    owner = 'TEST-candidate-image-preview'
    if not backend.call('profile.list', ''):
        backend.call('profile.save', owner, {'profile': blank_health('TEST 图片预览')})
    app = create_app(data / 'phone', 'TEST-candidate-images', shared=SharedProduct(backend, owner))

    @app.get('/_internal/rehab-image-preview.js')
    def preview_marker():
        return Response('window.__ANKANG_INTERNAL_IMAGE_PREVIEW__=true;', media_type='application/javascript', headers={'cache-control': 'no-store'})

    @app.middleware('http')
    async def internal_html_marker(request, call_next):
        response = await call_next(request)
        if request.url.path in ('/capture', '/static/rehab-image-review.html') and response.headers.get('content-type', '').startswith('text/html'):
            body = b''.join([chunk async for chunk in response.body_iterator])
            body = body.replace(b'</head>', b'<script src="/_internal/rehab-image-preview.js"></script></head>', 1)
            headers = {k: v for k, v in response.headers.items() if k.lower() not in ('content-length', 'etag', 'last-modified')}
            headers['cache-control'] = 'no-store'
            return Response(body, status_code=response.status_code, headers=headers)
        return response

    try:
        uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')
    finally:
        backend.close()


if __name__ == '__main__':
    main()
