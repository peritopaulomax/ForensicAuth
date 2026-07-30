"""Reference-population assets for LR calibration and latent typicality.

Runtime code should resolve paths via :mod:`core.reference_data.paths`
(or the ``DEFAULT_*`` constants re-exported from the LR modules).
"""

from core.reference_data.paths import (
    project_root,
    get_reference_data_root,
    get_reference_build_root,
    get_bases_root,
    lr_cache_dir,
    audio_score_matrix,
    audio_augmented_score_matrix,
    audio_representations_matrix,
    audio_samples_root,
    synthetic_score_matrix,
    synthetic_augmented_score_matrix,
    synthetic_representations_matrix,
    synthetic_samples_root,
)

__all__ = [
    "project_root",
    "get_reference_data_root",
    "get_reference_build_root",
    "get_bases_root",
    "lr_cache_dir",
    "audio_score_matrix",
    "audio_augmented_score_matrix",
    "audio_representations_matrix",
    "audio_samples_root",
    "synthetic_score_matrix",
    "synthetic_augmented_score_matrix",
    "synthetic_representations_matrix",
    "synthetic_samples_root",
]
