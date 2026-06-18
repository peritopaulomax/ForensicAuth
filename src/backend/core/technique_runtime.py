"""Runtime availability probes per forensic technique."""

from __future__ import annotations

from typing import Tuple

from core.technique_ids import SYNTHETIC_IMAGE_DETECTION, resolve_technique_id


def technique_runtime_status(technique_name: str) -> Tuple[bool, str]:
    """
    Return (available, reason).

    reason is empty when the technique can run on this server.
    """
    technique_name = resolve_technique_id(technique_name)

    if technique_name == "zero_grid":
        from core.legacy.zero.libzero_loader import zero_runtime_status

        return zero_runtime_status()
    if technique_name == SYNTHETIC_IMAGE_DETECTION:
        from core.legacy.synthetic_image_detection.runtime import runtime_status

        return runtime_status()
    if technique_name == "safire":
        from core.legacy.safire.safire_runtime import safire_runtime_status

        return safire_runtime_status()
    if technique_name == "noiseprint":
        from core.legacy.noiseprint.noiseprint_runtime import noiseprint_runtime_status

        return noiseprint_runtime_status()
    if technique_name == "imdlbenco":
        from core.legacy.imdlbenco.imdlbenco_runtime import imdlbenco_runtime_status

        return imdlbenco_runtime_status()
    if technique_name == "videofact":
        from core.legacy.videofact.videofact_runtime import videofact_runtime_status

        return videofact_runtime_status()
    if technique_name == "stil_video_detection":
        from core.legacy.stil.stil_runtime import stil_runtime_status

        return stil_runtime_status()
    if technique_name == "lowres_fake_video":
        from core.legacy.lowres_fake_video.lfv_runtime import lfv_runtime_status

        return lfv_runtime_status()
    if technique_name == "distildire":
        from core.legacy.distildire.distildire_runtime import distildire_runtime_status

        return distildire_runtime_status()
    if technique_name == "metadata":
        import shutil

        if shutil.which("exiftool") or shutil.which("exiftool.exe"):
            return True, ""
        return (
            True,
            "ExifTool nao esta no PATH — metadados parciais (EXIF/ICC/JPEG). "
            "Instale ExifTool para IPTC, XMP e MakerNotes completos.",
        )
    return True, ""
