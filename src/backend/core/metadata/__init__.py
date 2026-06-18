"""Extracao de metadados de imagem (EXIF, IPTC, XMP, ICC, estrutura JPEG)."""

from core.metadata.extractor import extract_image_metadata

__all__ = ["extract_image_metadata"]
