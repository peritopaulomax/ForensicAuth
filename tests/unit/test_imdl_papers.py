"""Tests for local IMDL paper references."""

import pytest


class TestImdlPapers:
    def test_manifest_lists_dl_techniques(self):
        from core.references.imdl_papers import list_paper_technique_ids

        ids = list_paper_technique_ids()
        assert "jpeg_structure_compare" in ids
        assert "jpeg_ghosts" in ids
        assert "prnu" in ids
        assert "noiseprint" in ids
        assert "safire" in ids
        assert "trufor" in ids
        assert "co_transformers" in ids

    def test_resolve_safire_pdf(self):
        from core.references.imdl_papers import resolve_paper_path

        path = resolve_paper_path("safire")
        assert path is not None
        assert path.name == "paper.pdf"
        assert path.stat().st_size > 10_000

    def test_resolve_bfree_pdf(self):
        from core.references.imdl_papers import resolve_paper_path

        path = resolve_paper_path("bfree")
        assert path is not None
        assert path.name == "guillaro_2025_bias_free.pdf"
        assert path.stat().st_size > 10_000

    def test_resolve_corvi2023_pdf(self):
        from core.references.imdl_papers import resolve_paper_path

        path = resolve_paper_path("corvi2023")
        assert path is not None
        assert path.name == "corvi_2023_diffusion_synthetic_detection.pdf"
        assert path.stat().st_size > 10_000

    def test_metadata_available_flag(self):
        from core.references.imdl_papers import get_paper_metadata

        meta = get_paper_metadata("cat_net")
        assert meta is not None
        assert meta["available"] is True
        assert meta["venue"]
        assert meta["suggested_filename"].endswith(".pdf")

    def test_metadata_supports_multiple_files(self):
        from core.references.imdl_papers import get_paper_metadata

        meta = get_paper_metadata("prnu")
        assert meta is not None
        assert len(meta["files"]) == 3
        assert meta["files"][0]["index"] == 0
        assert meta["files"][1]["suggested_filename"].endswith(".pdf")

    def test_rejects_invalid_id(self):
        from core.references.imdl_papers import resolve_paper_path

        with pytest.raises(ValueError):
            resolve_paper_path("../etc/passwd")
