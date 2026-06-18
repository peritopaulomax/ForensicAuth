"""Whitelist de snapshots PNG de overlay de audio."""

from api.v1.endpoints.analysis import AUDIO_PLOT_SNAPSHOT_FILENAMES


def test_audio_plot_snapshot_filenames_map_to_techniques():
    assert AUDIO_PLOT_SNAPSHOT_FILENAMES["enf_overlay_snapshot.png"] == "audio_enf"
    assert AUDIO_PLOT_SNAPSHOT_FILENAMES["levels_overlay_snapshot.png"] == "audio_levels"
    assert AUDIO_PLOT_SNAPSHOT_FILENAMES["dc_overlay_snapshot.png"] == "audio_dc_local"
    assert len([t for t in AUDIO_PLOT_SNAPSHOT_FILENAMES.values() if t == "audio_ltas"]) == 4
