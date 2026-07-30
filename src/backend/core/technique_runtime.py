"""Runtime availability probes per forensic technique."""

from __future__ import annotations

from functools import lru_cache
from typing import Tuple

from core.plugin_registry import get_plugin_registry
from core.technique_ids import (
    MOE_FFD,
    PRESENTATION_ATTACK_DETECTION,
    SYNTHETIC_IMAGE_DETECTION,
    resolve_technique_id,
)


def _plugin_runtime_status(technique_name: str) -> Tuple[bool, str] | None:
    """Return plugin-native runtime status, or None if plugin is unavailable."""
    registry = get_plugin_registry()
    plugin_cls = registry.PLUGINS.get(technique_name)
    if plugin_cls is None:
        return None
    plugin = plugin_cls()
    if not hasattr(plugin, "is_runtime_available") or not callable(plugin.is_runtime_available):
        return None
    try:
        available, reason = plugin.is_runtime_available()
    except Exception as exc:
        return False, f"Falha ao verificar runtime: {type(exc).__name__}: {exc}"
    return available, reason or ""


@lru_cache(maxsize=64)
def technique_runtime_status(technique_name: str) -> Tuple[bool, str]:
    """
    Return (available, reason).

    reason is empty when the technique can run on this server.
    Cached for the process lifetime — listing techniques must stay cheap.
    """
    technique_name = resolve_technique_id(technique_name)

    # Prefer plugin-native declaration.
    plugin_status = _plugin_runtime_status(technique_name)
    if plugin_status is not None:
        return plugin_status

    if technique_name == SYNTHETIC_IMAGE_DETECTION:
        from forensics.synthetic_image_detection.runtime import runtime_status

        return runtime_status()
    if technique_name == "safire":
        from forensics.safire.safire_runtime import safire_runtime_status

        return safire_runtime_status()
    if technique_name == "imdlbenco":
        from forensics.imdlbenco.imdlbenco_runtime import imdlbenco_runtime_status

        return imdlbenco_runtime_status()
    if technique_name == "videofact":
        from forensics.videofact.videofact_runtime import videofact_runtime_status

        return videofact_runtime_status()
    if technique_name == "stil_video_detection":
        from forensics.stil.stil_runtime import stil_runtime_status

        return stil_runtime_status()
    if technique_name == "lowres_fake_video":
        from forensics.lowres_fake_video.lfv_runtime import lfv_runtime_status

        return lfv_runtime_status()
    if technique_name == PRESENTATION_ATTACK_DETECTION:
        from forensics.pad.runtime import pad_runtime_status

        return pad_runtime_status()
    if technique_name == MOE_FFD:
        from forensics.moe_ffd.runtime import moe_ffd_runtime_status

        return moe_ffd_runtime_status()
    if technique_name == "metadata":
        import shutil

        if shutil.which("exiftool") or shutil.which("exiftool.exe"):
            return True, ""
        return (
            True,
            "ExifTool nao esta no PATH — metadados parciais (EXIF/ICC/JPEG). "
            "Instale ExifTool para IPTC, XMP e MakerNotes completos.",
        )
    if technique_name == "audio_metadata":
        import shutil

        if shutil.which("exiftool") or shutil.which("exiftool.exe"):
            return True, ""
        return (
            True,
            "ExifTool nao esta no PATH — tags ID3/Vorbis/RIFF/QuickTime ficam indisponiveis; "
            "o probe tecnico (codec/taxa/duracao) ainda funciona.",
        )
    if technique_name == "video_metadata":
        import shutil

        has_exif = bool(shutil.which("exiftool") or shutil.which("exiftool.exe"))
        has_ff = bool(shutil.which("ffprobe"))
        if has_exif and has_ff:
            return True, ""
        missing = []
        if not has_exif:
            missing.append("ExifTool")
        if not has_ff:
            missing.append("ffprobe")
        return (
            True,
            f"{' e '.join(missing)} ausente(s) no PATH — extracao parcial "
            "(ISO BMFF resumido ainda pode rodar).",
        )
    return True, ""


def clear_technique_runtime_cache() -> None:
    technique_runtime_status.cache_clear()
    try:
        from forensics.imdlbenco.imdlbenco_runtime import imdlbenco_runtime_status

        imdlbenco_runtime_status.cache_clear()
    except Exception:
        pass
    try:
        from forensics.safire.safire_runtime import clear_runtime_cache

        clear_runtime_cache()
    except Exception:
        pass
