"""Unit tests for synthetic-image reference ingestion script (no GPU)."""

from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ingest_synthetic_image_reference.py"


def _load_ingest_module():
    spec = importlib.util.spec_from_file_location("ingest_synthetic_image_reference", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ingest():
    return _load_ingest_module()


def _write_png(path: Path, color: tuple[int, int, int] = (20, 40, 60)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), color).save(path)


def test_parse_y_fake(ingest):
    assert ingest.parse_y_fake(1) == 1
    assert ingest.parse_y_fake("fake") == 1
    assert ingest.parse_y_fake("ai") == 1
    assert ingest.parse_y_fake(0) == 0
    assert ingest.parse_y_fake("real") == 0
    assert ingest.parse_y_fake("nature") == 0
    with pytest.raises(ValueError):
        ingest.parse_y_fake("maybe")


def test_load_protocol_csv_and_single_base(ingest, tmp_path: Path):
    img_a = tmp_path / "a.png"
    img_b = tmp_path / "b.png"
    _write_png(img_a)
    _write_png(img_b, (90, 10, 10))
    protocol = tmp_path / "protocol.csv"
    protocol.write_text(
        "image_path,base_id,subgroup,y_fake,source_id\n"
        f"{img_a},demo_bench,GenA,1,s1\n"
        f"{img_b},demo_bench,GenA,0,s2\n",
        encoding="utf-8",
    )
    rows = ingest.load_protocol_csv(protocol)
    assert len(rows) == 2
    assert rows[0].base_id == "demo_bench"
    assert rows[0].y_fake == 1
    assert rows[1].y_fake == 0


def test_load_protocol_rejects_mixed_base_ids(ingest, tmp_path: Path):
    img = tmp_path / "a.png"
    _write_png(img)
    protocol = tmp_path / "protocol.csv"
    protocol.write_text(
        "image_path,base_id,subgroup,y_fake\n"
        f"{img},bench_a,G,1\n"
        f"{img},bench_b,G,0\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unico base_id"):
        ingest.load_protocol_csv(protocol)


def test_make_augmentation_variants(ingest, tmp_path: Path):
    img_path = tmp_path / "src.png"
    _write_png(img_path, (100, 150, 200))
    image = Image.open(img_path)
    for aug in ingest.AUGMENTATION_NAMES:
        payload, suffix, params = ingest.make_augmentation(image, aug, ".png")
        assert isinstance(payload, (bytes, bytearray)) and len(payload) > 32
        assert suffix.startswith(".")
        assert isinstance(params, dict)


def test_materialize_and_augment_end_to_end(ingest, tmp_path: Path):
    media = tmp_path / "media"
    build = tmp_path / "va-reference_build"
    img_fake = media / "fake.png"
    img_real = media / "real.png"
    _write_png(img_fake, (200, 30, 30))
    _write_png(img_real, (30, 30, 200))

    protocol = tmp_path / "protocol.csv"
    with protocol.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["image_path", "base_id", "subgroup", "y_fake", "source_id"])
        writer.writeheader()
        writer.writerow(
            {
                "image_path": str(img_fake),
                "base_id": "demo_bench",
                "subgroup": "GenA",
                "y_fake": "1",
                "source_id": "fake1",
            }
        )
        writer.writerow(
            {
                "image_path": "real.png",
                "base_id": "demo_bench",
                "subgroup": "GenA",
                "y_fake": "real",
                "source_id": "real1",
            }
        )

    rows = ingest.load_protocol_csv(protocol, media_root=media)
    originals = ingest.materialize_originals(rows, build_root=build, dataset_id="DemoBench")
    assert len(originals) == 2
    for record in originals:
        assert record.local_path.is_file()
        assert record.sha256
        assert "synthetic_image/originals/demo_bench/" in record.local_relpath

    augs = ingest.generate_augmentations(originals, build_root=build)
    assert len(augs) == 2 * len(ingest.AUGMENTATION_NAMES)
    assert all(r.local_path.is_file() for r in augs)
    assert {r.augmentation for r in augs} == set(ingest.AUGMENTATION_NAMES)

    orig_manifest = build / "synthetic_image" / "manifests" / "originals.csv"
    aug_manifest = build / "synthetic_image" / "manifests" / "augmented.csv"
    ingest.append_manifest(orig_manifest, originals)
    ingest.append_manifest(aug_manifest, augs)
    ingest.append_manifest(orig_manifest, originals)  # idempotent
    with orig_manifest.open(encoding="utf-8") as fh:
        assert len(list(csv.DictReader(fh))) == 2
    with aug_manifest.open(encoding="utf-8") as fh:
        assert len(list(csv.DictReader(fh))) == len(augs)

    ingest.update_bases_json(build, base_id="demo_bench", dataset_id="DemoBench")
    bases = (build / "bases.json").read_text(encoding="utf-8")
    assert "demo_bench" in bases and "DemoBench" in bases


def test_score_row_builders(ingest, tmp_path: Path):
    img = tmp_path / "x.png"
    _write_png(img)
    protocol = ingest.ProtocolRow(
        image_path=img,
        base_id="demo",
        subgroup="G",
        y_fake=1,
        source_id="s1",
        purpose="calibration_train",
        row_index=1,
    )
    record = ingest.MediaRecord(
        protocol=protocol,
        dataset_id="Demo",
        local_path=img,
        local_relpath="synthetic_image/originals/demo/x.png",
        sha256="abc",
        nbytes=10,
        source_sha256="abc",
        source_path=str(img),
        augmentation=ingest.ORIGINAL_TAG,
    )
    scores = {
        "ai_image_detector_deploy": {
            "fake_prob": 0.9,
            "real_prob": 0.1,
            "raw_score": None,
            "decision": "AI",
            "device": "CPU",
            "embedding_dim": 4,
        }
    }
    row = ingest._score_row_from_detector_scores(record, scores, elapsed=0.5)
    assert row["dataset"] == "Demo"
    assert row["ai_image_detector_deploy_fake_prob"] == 0.9
    assert "augmentation" not in row or row.get("augmentation") in ("", None)

    record_aug = ingest.MediaRecord(
        protocol=protocol,
        dataset_id="Demo",
        local_path=img,
        local_relpath="synthetic_image/augmented/demo/x.jpg",
        sha256="def",
        nbytes=11,
        source_sha256="abc",
        source_path=str(img),
        augmentation="jpeg_85",
    )
    row_aug = ingest._score_row_from_detector_scores(record_aug, scores, elapsed=0.2)
    assert row_aug["augmentation"] == "jpeg_85"

    rep = ingest._rep_row_from_detector_scores(
        record,
        scores,
        {"ai_image_detector_deploy": "/tmp/e.npy"},
    )
    assert rep["sample_id"].endswith("__original")
    assert rep["ai_image_detector_deploy_embedding_path"] == "/tmp/e.npy"


def test_cli_skip_scoring(ingest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    media = tmp_path / "media"
    build = tmp_path / "build"
    data = tmp_path / "reference_data"
    img = media / "f.png"
    _write_png(img)
    protocol = tmp_path / "p.csv"
    protocol.write_text(
        "image_path,base_id,subgroup,y_fake,source_id\n"
        f"{img.name},cli_bench,GenX,1,id1\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    rc = ingest.main(
        [
            "--protocol",
            str(protocol),
            "--media-root",
            str(media),
            "--dataset-id",
            "CliBench",
            "--base-group",
            "CliBench",
            "--reference-build-dir",
            str(build),
            "--reference-data-dir",
            str(data),
            "--skip-scoring",
        ]
    )
    assert rc == 0
    originals = list((build / "synthetic_image" / "originals" / "cli_bench").rglob("*.png"))
    assert len(originals) == 1
    augs = list((build / "synthetic_image" / "augmented" / "cli_bench").rglob("*"))
    assert any(p.is_file() for p in augs)


def test_query_for_item_generic_fallback():
    import pandas as pd

    from core.synthetic_lr_reference import PopulationItem, _query_for_item

    df = pd.DataFrame(
        {
            "dataset": ["BrandNewBench", "BrandNewBench"],
            "generator": ["Alpha", "Alpha"],
            "y_fake": [1, 0],
        }
    )
    item = PopulationItem("BrandNewBench", "Alpha")
    assert int(_query_for_item(df, item, 1).sum()) == 1
    assert int(_query_for_item(df, item, 0).sum()) == 1
