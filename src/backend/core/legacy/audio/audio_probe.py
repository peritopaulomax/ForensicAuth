"""Metadados tecnicos de arquivos de audio (taxa, duracao, bits, codec)."""

from __future__ import annotations

import logging
import struct
import wave
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_SF_BIT_DEPTH = {
    "PCM_S8": 8,
    "PCM_U8": 8,
    "PCM_16": 16,
    "PCM_24": 24,
    "PCM_32": 32,
    "FLOAT": 32,
    "DOUBLE": 64,
}


def _round_duration(seconds: Optional[float]) -> Optional[float]:
    if seconds is None:
        return None
    return round(float(seconds), 2)


def _probe_mp3_first_frame(path: Path) -> Dict[str, Any]:
    from core.legacy.audio.mp3_parser import MP3Analyzer

    analyzer = MP3Analyzer(str(path))
    with open(path, "rb") as handle:
        data = handle.read(65536)

    offset = 0
    if data[:3] == b"ID3":
        size = ((data[6] & 0x7F) << 21) | ((data[7] & 0x7F) << 14) | ((data[8] & 0x7F) << 7) | (data[9] & 0x7F)
        offset = 10 + size

    frame = None
    for idx in range(offset, max(offset, len(data) - 4)):
        if data[idx : idx + 2] == b"\xff\xfb" or data[idx : idx + 2] == b"\xff\xfa":
            frame = analyzer.parse_frame_header(data[idx : idx + 4])
            if frame:
                break

    if not frame:
        return {"codec": "MP3"}

    version = frame.get("version", "?")
    layer = frame.get("layer", "?")
    return {
        "sample_rate_hz": int(frame["samplerate"]) if frame.get("samplerate") else None,
        "codec": f"MPEG-{version} Layer {layer}",
        "channels": 1 if frame.get("channel") == "Mono" else 2 if frame.get("channel") else None,
    }


def _probe_opus_id_header(path: Path) -> Dict[str, Any]:
    from core.legacy.audio.opus_parser import OggOpusAnalyzer

    analyzer = OggOpusAnalyzer(str(path))
    try:
        with open(path, "rb") as handle:
            first_page = analyzer.parse_single_page(handle)
            if first_page is not None:
                analyzer.pages = [first_page]
            analyzer.parse_id_header()
    except Exception as exc:
        logger.debug("Falha ao parsear Opus %s: %s", path, exc)
        return {"codec": "Opus"}

    header = analyzer.id_header
    if header is None:
        return {"codec": "Opus"}

    sr = int(header.input_sample_rate) if header.input_sample_rate else 48000
    return {
        "sample_rate_hz": sr,
        "codec": "Opus",
        "channels": int(header.channels),
        "bit_depth": 16,
    }


def _probe_wav(path: Path) -> Dict[str, Any]:
    with wave.open(str(path), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frames = wav_file.getnframes()
        duration = frames / sample_rate if sample_rate else None
        bit_depth = sample_width * 8

    codec = "PCM"
    try:
        with open(path, "rb") as handle:
            if handle.read(4) != b"RIFF":
                raise ValueError("nao e RIFF")
            handle.seek(20)
            audio_format = struct.unpack("<H", handle.read(2))[0]
            if audio_format == 0x0011:
                codec = "IMA ADPCM"
            elif audio_format == 0x0001:
                codec = "PCM"
            elif audio_format == 0x0003:
                codec = "IEEE float"
    except Exception:
        pass

    return {
        "sample_rate_hz": int(sample_rate),
        "duration_sec": _round_duration(duration),
        "bit_depth": int(bit_depth),
        "codec": codec,
        "channels": int(channels),
    }


def _probe_with_librosa(path: Path) -> Dict[str, Any]:
    import librosa

    duration = librosa.get_duration(path=str(path))
    sample_rate = librosa.get_samplerate(path=str(path))
    return {
        "sample_rate_hz": int(sample_rate) if sample_rate else None,
        "duration_sec": _round_duration(duration),
    }


def _probe_with_soundfile(path: Path) -> Dict[str, Any]:
    import soundfile as sf

    info = sf.info(str(path))
    bit_depth = _SF_BIT_DEPTH.get(info.subtype)
    duration = info.duration if info.duration and info.duration > 0 else None
    codec = info.format
    if info.subtype and info.subtype != info.format:
        codec = f"{info.format} ({info.subtype})"
    return {
        "sample_rate_hz": int(info.samplerate),
        "duration_sec": _round_duration(duration),
        "bit_depth": bit_depth,
        "codec": codec,
        "channels": int(info.channels),
    }


def probe_audio_metadata(file_path: str) -> Dict[str, Any]:
    """
    Extrai metadados tecnicos do arquivo de audio.

    Retorna dict com: sample_rate_hz, duration_sec, bit_depth, codec, channels.
    """
    path = Path(file_path)
    if not path.is_file():
        return {}

    ext = path.suffix.lower()
    result: Dict[str, Any] = {}

    try:
        if ext in {".wav", ".wave"}:
            result.update(_probe_wav(path))
        elif ext == ".mp3":
            result.update(_probe_mp3_first_frame(path))
            try:
                import librosa

                result["duration_sec"] = _round_duration(librosa.get_duration(path=str(path)))
            except Exception:
                pass
            result.setdefault("bit_depth", 16)
        elif ext in {".opus", ".oga"}:
            result.update(_probe_opus_id_header(path))
            try:
                import librosa

                result["duration_sec"] = _round_duration(librosa.get_duration(path=str(path)))
            except Exception:
                pass
        else:
            try:
                result.update(_probe_with_soundfile(path))
            except Exception:
                result.update(_probe_with_librosa(path))
                ext_label = ext.lstrip(".") or "audio"
                result.setdefault("codec", ext_label.upper())
    except Exception as exc:
        logger.warning("Falha ao sondar metadados de %s: %s", path, exc)
        try:
            result.update(_probe_with_librosa(path))
        except Exception:
            return {}

    if not result.get("codec"):
        result["codec"] = ext.lstrip(".").upper() or "AUDIO"

    if result.get("duration_sec") is None:
        try:
            import librosa

            result["duration_sec"] = _round_duration(librosa.get_duration(path=str(path)))
        except Exception:
            pass

    if result.get("sample_rate_hz") is not None:
        result["sample_rate_hz"] = int(result["sample_rate_hz"])
    if result.get("bit_depth") is not None:
        result["bit_depth"] = int(result["bit_depth"])
    if result.get("channels") is not None:
        result["channels"] = int(result["channels"])

    return result
