"""Reuse Ankang's hardware-neutral capture contracts without starting Route2 spatial inference."""
import importlib.util
import sys
from pathlib import Path

_source = Path(__file__).resolve().parents[3] / 'ankang' / 'route2-home-3d' / 'backend' / 'capture.py'
_name = 'ankang_product_capture_contract'
if _name not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_name, _source)
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_name] = _module
    _spec.loader.exec_module(_module)
else:
    _module = sys.modules[_name]
CaptureFile = _module.CaptureFile
CaptureBatch = _module.CaptureBatch
CaptureSource = _module.CaptureSource
BrowserUploadCaptureSource = _module.BrowserUploadCaptureSource


def archive_payload(batch, *, visibility='private'):
    """Explicitly selected capture files enter the existing archive, never inferred health/spatial facts."""
    if visibility not in ('private', 'family_ok'):
        raise ValueError('Invalid capture visibility')
    files = []
    for entry in batch.files:
        path = Path(entry.path)
        if not (entry.media_type.startswith('image/') or entry.media_type.startswith('video/')):
            raise ValueError('Capture requires image or video media')
        if entry.size_bytes < 0 or entry.size_bytes > 20 * 1024 * 1024:
            raise ValueError('Capture file exceeds attachment limit')
        data = path.read_bytes()
        if len(data) != entry.size_bytes:
            raise ValueError('Capture size changed')
        files.append({'name': entry.name, 'fileName': path.name, 'category': '影像资料',
                      'mediaType': entry.media_type, 'bytes': list(data), 'visibility': visibility})
    return {'batchId': batch.batch_id, 'capturedAt': batch.captured_at, 'source': batch.source, 'files': files}
