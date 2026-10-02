"""Migrated capture contract -> existing ProductBackend/Node archive, TEST files only."""
import pytest

from app.product.backend import ProductBackend
from app.product.capture import BrowserUploadCaptureSource, CaptureFile, archive_payload
from app.ui.product_dialogs import blank_health


def test_capture_contract_reaches_real_archive_without_spatial_or_health_inference(tmp_path, monkeypatch):
    monkeypatch.setenv('ANKANG_PRODUCT_DISABLE_MODEL', '1')
    media = tmp_path / 'TEST-capture.mp4'
    media.write_bytes(b'TEST capture protocol fixture')
    batch = BrowserUploadCaptureSource().from_files(batch_id='TEST-batch', captured_at='2026-10-02T10:00:00Z',
        media_kind='video', files=[CaptureFile(media, 'TEST video', 'video/mp4', media.stat().st_size)])
    backend = ProductBackend(tmp_path)
    def receive():
        operation, owner, token, result, error = backend.results.get(timeout=20)
        assert not error, (operation, error)
        return result
    try:
        backend.submit('profile.save', 'TEST-capture', {'profile': blank_health('TEST capture')})
        receive()
        backend.submit_capture('TEST-capture', batch)
        result = receive()
        assert len(result['attachments']) == 1
        assert result['state']['events'] == []
        attachment = result['attachments'][0]
        assert attachment['mediaType'] == 'video/mp4'
        backend.submit('archive.read', 'TEST-capture', {'id': attachment['id']})
        assert bytes(receive()['bytes']) == media.read_bytes()
        backend.submit('family.summary', 'TEST-capture')
        assert receive()['attachments'] == []
    finally:
        backend.close()
        backend.thread.join(5)
    assert not backend.thread.is_alive()


def test_capture_rejects_changed_file_before_submitting(tmp_path):
    media = tmp_path / 'TEST-image.png'
    media.write_bytes(b'TEST')
    batch = BrowserUploadCaptureSource().from_files(batch_id='TEST', captured_at='2026-10-02T10:00:00Z',
        media_kind='image', files=[CaptureFile(media, 'TEST image', 'image/png', 5)])
    with pytest.raises(ValueError, match='size changed'):
        archive_payload(batch)
