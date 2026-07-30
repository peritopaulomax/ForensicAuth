"""Unit tests for audio-spoofing reference ingestion script (no GPU)."""

from __future__ import annotations

import csv
import importlib.util
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ingest_audio_spoofing_reference.py"


def _load_ingest_module():
    spec = importlib.util.spec_from_file_location("ingest_audio_spoofing_reference", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ingest():
    return _load_ingest_module()


def _write_wav(path: Path, seconds: float = 0.4, sr: int = 16000) -> None:
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    audio = (0.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    sf.write(str(path), audio, sr)


def test_parse_y_spoof(ingest):
    assert ingest.parse_y_spoof(1) == 1
    assert ingest.parse_y_spoof("spoof") == 1
    assert ingest.parse_y_spoof("fake") == 1
    assert ingest.parse_y_spoof(0) == 0
    assert ingest.parse_y_spoof("bonafide") == 0
    assert ingest.parse_y_spoof("real") == 0
    with pytest.raises(ValueError):
        ingest.parse_y_spoof("maybe")


def test_load_protocol_accepts_y_fake_alias(ingest, tmp_path: Path):
    wav = tmp_path / "a.wav"
    _write_wav(wav)
    protocol = tmp_path / "p.csv"
    protocol.write_text(
        "audio_path,base_id,subgroup,y_fake,source_id\n"
        f"{wav},demo_audio,GenA,1,s1\n",
        encoding="utf-8",
    )
    rows = ingest.load_protocol_csv(protocol)
    assert len(rows) == 1
    assert rows[0].y_spoof == 1
    assert rows[0].base_id == "demo_audio"


def test_load_protocol_rejects_mixed_bases(ingest, tmp_path: Path):
    wav = tmp_path / "a.wav"
    _write_wav(wav)
    protocol = tmp_path / "p.csv"
    protocol.write_text(
        "audio_path,base_id,subgroup,y_spoof\n"
        f"{wav},bench_a,G,1\n"
        f"{wav},bench_b,G,0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unico base_id"):
        ingest.load_protocol_csv(protocol)


def test_noise_augmentation(ingest, tmp_path: Path):
    wav = tmp_path / "src.wav"
    _write_wav(wav)
    audio, sr = ingest._read_audio(wav)
    out, out_sr, params = ingest.apply_augmentation(
        audio, sr, "noise_snr_20", source_id="s1", source_sha256="abc"
    )
    assert out_sr == ingest.SAMPLE_RATE
    assert len(out) == len(audio)
    assert params["snr_db"] == 20.0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg required for codec augs")
def test_mp3_augmentation_roundtrip(ingest, tmp_path: Path):
    wav = tmp_path / "src.wav"
    _write_wav(wav, seconds=0.5)
    audio, sr = ingest._read_audio(wav)
    out, out_sr, params = ingest.apply_augmentation(audio, sr, "mp3_128k")
    assert out_sr == ingest.SAMPLE_RATE
    assert len(out) > 100
    assert params["bitrate_kbps"] == 128


def test_materialize_and_noise_augs(ingest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Restrict augs to noise-only so tests do not require ffmpeg.
    monkeypatch.setattr(ingest, "AUGMENTATION_NAMES", ("noise_snr_20", "noise_snr_15"))

    media = tmp_path / "media"
    build = tmp_path / "build"
    spoof = media / "spoof.wav"
    bona = media / "bona.wav"
    _write_wav(spoof)
    _write_wav(bona, seconds=0.35)

    protocol = tmp_path / "protocol.csv"
    with protocol.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["audio_path", "base_id", "subgroup", "y_spoof", "source_id"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "audio_path": str(spoof),
                "base_id": "demo_audio",
                "subgroup": "GenA",
                "y_spoof": "1",
                "source_id": "sp1",
            }
        )
        writer.writerow(
            {
                "audio_path": "bona.wav",
                "base_id": "demo_audio",
                "subgroup": "GenA",
                "y_spoof": "bonafide",
                "source_id": "bn1",
            }
        )

    rows = ingest.load_protocol_csv(protocol, media_root=media)
    originals = ingest.materialize_originals(rows, build_root=build, dataset_id="DemoAudio")
    assert len(originals) == 2
    assert all(r.local_path.is_file() for r in originals)

    augs = ingest.generate_augmentations(originals, build_root=build)
    assert len(augs) == 4
    assert all(r.local_path.is_file() for r in augs)
    assert {r.augmentation for r in augs} == {"noise_snr_20", "noise_snr_15"}

    orig_manifest = build / "audio_spoofing" / "manifests" / "originals.csv"
    aug_manifest = build / "audio_spoofing" / "manifests" / "augmented.csv"
    ingest.append_manifest_originals(orig_manifest, originals)
    ingest.append_manifest_augmented(aug_manifest, augs)
    ingest.append_manifest_originals(orig_manifest, originals)
    with orig_manifest.open(encoding="utf-8") as fh:
        assert len(list(csv.DictReader(fh))) == 2


def test_score_and_rep_builders(ingest, tmp_path: Path):
    wav = tmp_path / "x.wav"
    _write_wav(wav)
    protocol = ingest.ProtocolRow(
        audio_path=wav,
        base_id="demo",
        subgroup="G",
        y_spoof=1,
        source_id="s1",
        purpose="reference_population",
        row_index=1,
    )
    record = ingest.MediaRecord(
        protocol=protocol,
        dataset_id="Demo",
        local_path=wav,
        local_relpath="audio_spoofing/originals/demo/x.wav",
        sha256="abc",
        nbytes=10,
        source_sha256="abc",
        source_path=str(wav),
        augmentation=ingest.ORIGINAL_TAG,
    )
    scores = {
        "df_arena_1b": {
            "spoof_prob": 0.8,
            "bonafide_prob": 0.2,
            "spoof_logit": 1.0,
            "bonafide_logit": -1.0,
            "decision": "Spoof",
            "device": "CPU",
            "window_count": 1,
            "embedding_dim": 8,
        }
    }
    row = ingest._score_row(record, scores, elapsed=0.3)
    assert row["dataset"] == "Demo"
    assert row["y_spoof"] == 1
    assert row["df_arena_1b_spoof_prob"] == 0.8
    assert row["augmentation"] == ""

    rep = ingest._rep_row(record, scores, {"df_arena_1b": "/tmp/e.npy"}, elapsed=0.3)
    assert rep["sample_id"].endswith("__original")
    assert rep["df_arena_1b_embedding_path"] == "/tmp/e.npy"


def test_cli_skip_scoring(ingest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ingest, "AUGMENTATION_NAMES", ("noise_snr_20",))
    media = tmp_path / "media"
    build = tmp_path / "build"
    data = tmp_path / "reference_data"
    wav = media / "f.wav"
    _write_wav(wav)
    protocol = tmp_path / "p.csv"
    protocol.write_text(
        "audio_path,base_id,subgroup,y_spoof,source_id\n"
        f"{wav.name},cli_audio,GenX,1,id1\n",
        encoding="utf-8",
    )
    rc = ingest.main(
        [
            "--protocol",
            str(protocol),
            "--media-root",
            str(media),
            "--dataset-id",
            "CliAudio",
            "--base-group",
            "CliAudio",
            "--reference-build-dir",
            str(build),
            "--reference-data-dir",
            str(data),
            "--skip-scoring",
        ]
    )
    assert rc == 0
    originals = list((build / "audio_spoofing" / "originals" / "cli_audio").rglob("*.wav"))
    assert len(originals) == 1
    augs = list((build / "audio_spoofing" / "augmented" / "cli_audio").rglob("*.wav"))
    assert len(augs) == 1
