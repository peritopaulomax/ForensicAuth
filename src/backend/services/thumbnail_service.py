"""Generate JPEG thumbnails for image and video evidence files."""

from io import BytesIO
from pathlib import Path

from PIL import Image as PILImage
from PIL import UnidentifiedImageError


class ThumbnailError(Exception):
    """Raised when thumbnail generation fails."""


THUMBNAIL_SIZE = (80, 80)
JPEG2000_SUFFIXES = frozenset({".jp2", ".jpx", ".jpx2"})


def _pil_thumbnail_jpeg(img: PILImage.Image) -> BytesIO:
    img = img.convert("RGB")
    img.thumbnail(THUMBNAIL_SIZE)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return buf


def _jpeg2000_thumbnail(file_path: Path) -> BytesIO:
    try:
        with PILImage.open(str(file_path)) as img:
            return _pil_thumbnail_jpeg(img)
    except Exception:
        pass
    try:
        import fitz

        pix = fitz.Pixmap(str(file_path))
        if pix.n - pix.alpha > 3:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        mode = "RGBA" if pix.alpha else "RGB"
        img = PILImage.frombytes(mode, [pix.width, pix.height], pix.samples)
        return _pil_thumbnail_jpeg(img.convert("RGB"))
    except Exception as exc:
        raise ThumbnailError(
            f"Nao foi possivel gerar thumbnail JPEG2000: {file_path.name}"
        ) from exc


def _image_thumbnail(file_path: Path) -> BytesIO:
    if file_path.suffix.lower() in JPEG2000_SUFFIXES:
        return _jpeg2000_thumbnail(file_path)
    try:
        with PILImage.open(str(file_path)) as img:
            return _pil_thumbnail_jpeg(img)
    except UnidentifiedImageError as exc:
        raise ThumbnailError(f"Arquivo nao e uma imagem valida: {file_path.name}") from exc


def _video_thumbnail(file_path: Path) -> BytesIO:
    import cv2

    cap = cv2.VideoCapture(str(file_path))
    if not cap.isOpened():
        cap.release()
        raise ThumbnailError("Nao foi possivel abrir o video")

    try:
        ok, frame = cap.read()
        if not ok or frame is None:
            raise ThumbnailError("Nao foi possivel ler frame do video")

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return _pil_thumbnail_jpeg(PILImage.fromarray(frame_rgb))
    finally:
        cap.release()


def generate_thumbnail(file_path: Path, file_type: str) -> BytesIO:
    """Return JPEG bytes for an image or video evidence file."""
    if file_type == "imagem":
        return _image_thumbnail(file_path)
    if file_type == "video":
        return _video_thumbnail(file_path)
    raise ThumbnailError(f"Tipo nao suportado para thumbnail: {file_type}")
