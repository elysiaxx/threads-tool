"""Test validate media theo ràng buộc Threads (định dạng + dung lượng)."""
import pytest

from app.modules.collector.service import _validate_media


def test_accepts_valid_image_and_video():
    _validate_media("image/jpeg", 1000)
    _validate_media("image/png", 5 * 1024 * 1024)
    _validate_media("video/mp4; codecs=avc1", 10 * 1024 * 1024)
    _validate_media("video/quicktime", 1000)


def test_rejects_oversized_image():
    with pytest.raises(ValueError):
        _validate_media("image/jpeg", 9 * 1024 * 1024)


def test_rejects_oversized_video():
    with pytest.raises(ValueError):
        _validate_media("video/mp4", 2 * 1024 * 1024 * 1024)


@pytest.mark.parametrize("ct", ["application/pdf", "image/gif", "text/html", ""])
def test_rejects_unsupported_type(ct):
    with pytest.raises(ValueError):
        _validate_media(ct, 100)
