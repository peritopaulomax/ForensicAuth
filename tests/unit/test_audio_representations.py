"""Tests for audio representation sample_id and merge helpers."""

from __future__ import annotations

from core.latent_typicality.representations_utils import (
    ORIGINAL_AUGMENTATION_TAG,
    build_sample_id,
    parse_sample_id,
    resolve_parent_source_id,
)


def test_build_sample_id_with_augmentation():
    sid = build_sample_id(
        dataset="SONAR",
        generator="xTTS",
        source_id="clip_01",
        augmentation="mp3_128k",
    )
    assert sid == "SONAR__xTTS__clip_01__mp3_128k"


def test_build_sample_id_original_tag():
    sid = build_sample_id(dataset="ADD2022", generator="track1test", source_id="foo.wav")
    assert sid.endswith(f"__{ORIGINAL_AUGMENTATION_TAG}")
    parsed = parse_sample_id(sid)
    assert parsed["augmentation"] == ORIGINAL_AUGMENTATION_TAG


def test_resolve_parent_source_id_prefers_manifest_parent():
    row = {
        "parent_source_id": "E_0001858027",
        "source_id": "E_0001858027_mp3_128k",
        "augmentation": "mp3_128k",
    }
    assert resolve_parent_source_id(row) == "E_0001858027"


def test_resolve_parent_source_id_strips_aug_suffix_when_parent_missing():
    row = {
        "source_id": "clip_01_mp3_128k",
        "augmentation": "mp3_128k",
    }
    assert resolve_parent_source_id(row) == "clip_01"


def test_resolve_parent_source_id_does_not_truncate_asvspoof_ids():
    """Regression: rsplit on '_' must not turn E_0001858027 into E."""
    row = {
        "parent_source_id": "E_0001858027",
        "source_id": "E_0001858027_mp3_128k",
        "augmentation": "mp3_128k",
        "dataset": "ASVspoof5",
        "generator": "flac_E_eval",
    }
    parent = resolve_parent_source_id(row)
    sid = build_sample_id(
        dataset=row["dataset"],
        generator=row["generator"],
        source_id=parent,
        augmentation=row["augmentation"],
    )
    assert sid == "ASVspoof5__flac_E_eval__E_0001858027__mp3_128k"


def test_source_id_stem_preserves_dots_in_protocol_ids():
    from core.latent_typicality.representations_utils import source_id_stem

    assert source_id_stem("ADD2023_T1.2R1_E_00056324") == "ADD2023_T1.2R1_E_00056324"
    assert source_id_stem("E_0001858027.flac") == "E_0001858027"


def test_build_sample_id_no_collision_on_add2023_ids():
    a = build_sample_id(
        dataset="ADD2023",
        generator="Track1.2_testR1",
        source_id="ADD2023_T1.2R1_E_00056324",
        augmentation="mp3_128k",
    )
    b = build_sample_id(
        dataset="ADD2023",
        generator="Track1.2_testR1",
        source_id="ADD2023_T1.2R1_E_00074782",
        augmentation="mp3_128k",
    )
    assert a != b


def test_asvspoof_manifest_rows_produce_unique_sample_ids():
    rows = [
        {
            "parent_source_id": "E_0001858027",
            "source_id": "E_0001858027_mp3_128k",
            "augmentation": "mp3_128k",
            "dataset": "ASVspoof5",
            "generator": "flac_E_eval",
        },
        {
            "parent_source_id": "E_0008018711",
            "source_id": "E_0008018711_mp3_128k",
            "augmentation": "mp3_128k",
            "dataset": "ASVspoof5",
            "generator": "flac_E_eval",
        },
    ]
    ids = [
        build_sample_id(
            dataset=r["dataset"],
            generator=r["generator"],
            source_id=resolve_parent_source_id(r),
            augmentation=r["augmentation"],
        )
        for r in rows
    ]
    assert len(set(ids)) == 2


def test_repair_augmented_representations_renames_embeddings(tmp_path):
    import importlib.util
    import sys
    from pathlib import Path

    import numpy as np
    import pandas as pd

    repo = Path(__file__).resolve().parents[2]
    script = repo / "scripts" / "repair_audio_augmented_representations.py"
    spec = importlib.util.spec_from_file_location("repair_audio_augmented_representations", script)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["repair_audio_augmented_representations"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    repair_augmented_representations = mod.repair_augmented_representations

    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "purpose,dataset,generator,label,parent_source_id,source_id,augmentation,resolved_path\n"
        'reference_population,ASVspoof5,flac_E_eval,bonafide,E_0001858027,'
        "E_0001858027_mp3_128k,mp3_128k,/data/aug.wav\n",
        encoding="utf-8",
    )
    embed_dir = tmp_path / "embeddings"
    embed_dir.mkdir()
    wrong_sid = "ASVspoof5__flac_E_eval__E__mp3_128k"
    right_sid = "ASVspoof5__flac_E_eval__E_0001858027__mp3_128k"
    for det in ("df_arena_1b", "sls_xlsr", "wedefense_wavlm_mhfa"):
        np.save(embed_dir / f"{wrong_sid}__{det}.npy", np.zeros(4, dtype=np.float32))

    reps = tmp_path / "representations.csv"
    pd.DataFrame(
        [
            {
                "sample_id": wrong_sid,
                "source_id": "E",
                "dataset": "ASVspoof5",
                "generator": "flac_E_eval",
                "audio_path": "/data/aug.wav",
                "augmentation": "mp3_128k",
                "label": "bonafide",
                "df_arena_1b_embedding_path": str(embed_dir / f"{wrong_sid}__df_arena_1b.npy"),
                "error": "",
            }
        ]
    ).to_csv(reps, index=False)

    summary = repair_augmented_representations(
        manifest_path=manifest,
        representations_csv=reps,
        embeddings_dir=embed_dir,
        dry_run=False,
        backup=False,
    )
    fixed = pd.read_csv(reps)
    assert fixed.iloc[0]["sample_id"] == right_sid
    assert fixed.iloc[0]["source_id"] == "E_0001858027"
    assert (embed_dir / f"{right_sid}__df_arena_1b.npy").is_file()
    assert summary["rows_fixed"] == 1
    assert summary["still_missing_extraction"] == 0
