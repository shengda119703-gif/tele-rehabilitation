"""Reuse Ankang's hardware-neutral capture contracts without starting Route2 spatial inference."""
from pathlib import Path
from .capture_contracts import CaptureFile, CaptureBatch, CaptureSource, BrowserUploadCaptureSource


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
