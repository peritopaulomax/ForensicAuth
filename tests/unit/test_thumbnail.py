"""Tests for evidence thumbnail generation."""

import sys

import numpy as np
import pytest
from PIL import Image as PILImage

from services.thumbnail_service import ThumbnailError, generate_thumbnail


class TestThumbnailService:
    def test_image_thumbnail(self, tmp_path):
        img_path = tmp_path / "test.png"
        PILImage.new("RGB", (200, 100), color=(255, 0, 0)).save(img_path)

        buf = generate_thumbnail(img_path, "imagem")
        assert buf.getvalue()[:2] == b"\xff\xd8"

        out = PILImage.open(buf)
        assert max(out.size) <= 80

    def test_unsupported_type(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4")
        with pytest.raises(ThumbnailError):
            generate_thumbnail(f, "pdf")

    def test_invalid_image_bytes_raises_thumbnail_error(self, tmp_path):
        bad = tmp_path / "fake.png"
        bad.write_text('{"not": "an image"}', encoding="utf-8")
        with pytest.raises(ThumbnailError):
            generate_thumbnail(bad, "imagem")

    def test_video_thumbnail_mocked(self, tmp_path, monkeypatch):
        video_path = tmp_path / "clip.mp4"
        video_path.write_bytes(b"fake")

        class FakeCap:
            def isOpened(self):
                return True

            def read(self):
                return True, np.zeros((48, 64, 3), dtype=np.uint8)

            def release(self):
                pass

        fake_cv2 = type(sys)("cv2")
        fake_cv2.VideoCapture = lambda _p: FakeCap()
        fake_cv2.cvtColor = lambda frame, _code: frame
        fake_cv2.COLOR_BGR2RGB = 4
        monkeypatch.setitem(sys.modules, "cv2", fake_cv2)

        buf = generate_thumbnail(video_path, "video")
        assert buf.getvalue()[:2] == b"\xff\xd8"

    def test_jpeg2000_thumbnail_via_fitz_fallback(self, tmp_path, monkeypatch):
        jp2_path = tmp_path / "tile.jp2"
        jp2_path.write_bytes(b"\x00\x00\x00\x0cjP  \x0d\x0a\x87\x0a" + b"\x00" * 16)

        class FakePixmap:
            n = 3
            alpha = 0
            width = 32
            height = 24
            samples = bytes([200, 100, 50] * (32 * 24))

            def __init__(self, *_args, **_kwargs):
                pass

        fake_fitz = type(sys)("fitz")
        fake_fitz.csRGB = object()
        fake_fitz.Pixmap = lambda *_a, **_k: FakePixmap()
        monkeypatch.setitem(sys.modules, "fitz", fake_fitz)

        def _fail_open(_path):
            raise OSError("no jpeg2000 in pillow")

        monkeypatch.setattr(
            "services.thumbnail_service.PILImage.open",
            lambda _path: (_ for _ in ()).throw(OSError("no jpeg2000 in pillow")),
        )

        buf = generate_thumbnail(jp2_path, "imagem")
        assert buf.getvalue()[:2] == b"\xff\xd8"
