"""Unit tests for scripts/technique/scaffold_technique.py (no repo pollution)."""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "technique" / "scaffold_technique.py"


def _load_scaffold_module():
    spec = importlib.util.spec_from_file_location("scaffold_technique", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["scaffold_technique"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def scaffold():
    return _load_scaffold_module()


def test_validate_rejects_bad_template(scaffold):
    errs = scaffold.validate_manifest(
        {
            "id": "ok_id",
            "template": "complex",
            "media": "imagem",
            "title": "X",
            "card": {"mode": "none"},
            "artifacts": [],
        }
    )
    assert any("template" in e for e in errs)


def test_validate_simple_ok(scaffold):
    errs = scaffold.validate_manifest(
        {
            "id": "ok_technique",
            "template": "simple",
            "media": "imagem",
            "title": "Ok",
            "card": {"mode": "existing", "group_id": "classicas-compressao"},
            "artifacts": [
                {"key": "heatmap_path", "filename": "heatmap.png", "role": "heatmap"},
            ],
        }
    )
    assert errs == []


def test_validate_card_required_for_all_media(scaffold):
    errs = scaffold.validate_manifest(
        {
            "id": "audio_demo_tech",
            "template": "simple",
            "media": "audio",
            "title": "Ok",
            "card": {"mode": "existing"},
            "artifacts": [],
        }
    )
    assert any("group_id" in e for e in errs)


def test_validate_card_existing_audio_group(scaffold):
    errs = scaffold.validate_manifest(
        {
            "id": "audio_demo_tech",
            "template": "simple",
            "media": "audio",
            "title": "Ok",
            "card": {"mode": "existing", "group_id": "audio-spoofing"},
            "artifacts": [],
        }
    )
    assert errs == []


def test_validate_card_rejects_image_group_on_audio(scaffold):
    errs = scaffold.validate_manifest(
        {
            "id": "audio_demo_tech",
            "template": "simple",
            "media": "audio",
            "title": "Ok",
            "card": {"mode": "existing", "group_id": "classicas-compressao"},
            "artifacts": [],
        }
    )
    assert any("não existe" in e for e in errs)


def test_validate_rejects_unknown_artifact_role(scaffold):
    errs = scaffold.validate_manifest(
        {
            "id": "ok_technique",
            "template": "medium",
            "media": "imagem",
            "title": "Ok",
            "card": {"mode": "none"},
            "artifacts": [
                {"key": "x_path", "filename": "x.png", "role": "trufor_magic"},
            ],
        }
    )
    assert any("role" in e for e in errs)


def test_validate_slider_requires_min_max(scaffold):
    errs = scaffold.validate_manifest(
        {
            "id": "ok_technique",
            "template": "simple",
            "media": "imagem",
            "title": "Ok",
            "card": {"mode": "none"},
            "parameters": [
                {"name": "k", "type": "int", "widget": "slider", "default": 5},
            ],
            "artifacts": [],
        }
    )
    assert any("slider" in e and "min" in e for e in errs)


def test_validate_radio_requires_enum(scaffold):
    errs = scaffold.validate_manifest(
        {
            "id": "ok_technique",
            "template": "simple",
            "media": "imagem",
            "title": "Ok",
            "card": {"mode": "none"},
            "parameters": [
                {"name": "mode", "type": "string", "widget": "radio", "options": ["a", "b"]},
            ],
            "artifacts": [],
        }
    )
    assert any("radio" in e for e in errs)


def test_ts_parameter_defs_includes_widget(scaffold):
    out = scaffold._ts_parameter_defs(
        [
            {
                "name": "gain",
                "type": "float",
                "widget": "slider",
                "default": 1.0,
                "min": 0.1,
                "max": 10.0,
                "step": 0.1,
            },
            {
                "name": "channel",
                "type": "enum",
                "widget": "radio",
                "default": "rgb",
                "options": ["rgb", "y"],
            },
        ]
    )
    assert 'widget: "slider"' in out
    assert 'widget: "radio"' in out


def test_render_plugin_and_pipeline_compile(scaffold):
    m = {
        "id": "unit_scaffold_demo",
        "template": "medium",
        "media": "imagem",
        "title": "Unit Demo",
        "subtitle": "sub",
        "description": "desc",
        "card": {"mode": "none"},
        "parameters": [
            {"name": "gain", "type": "float", "default": 1.0, "min": 0.1, "max": 5.0},
            {"name": "mode", "type": "enum", "default": "a", "options": ["a", "b"]},
        ],
        "artifacts": [
            {"key": "heatmap_path", "filename": "heatmap.png", "role": "heatmap", "savable": True},
            {"key": "overlay_image_path", "filename": "overlay.png", "role": "overlay"},
        ],
    }
    plugin_src = scaffold._render_plugin(m)
    pipeline_src = scaffold._render_pipeline(m)
    ast.parse(plugin_src)
    ast.parse(pipeline_src)
    assert "UnitScaffoldDemoPlugin" in plugin_src
    assert "def run(" in pipeline_src


def test_render_plugin_multiline_description_is_valid_python(scaffold):
    """Regressão: description com \\n do YAML folded block nao pode quebrar o .py."""
    m = {
        "id": "median_denoise_residual",
        "template": "medium",
        "media": "imagem",
        "title": "Resíduo de Denoising (Filtro de Mediana)",
        "subtitle": "Imagem − mediana",
        "description": (
            "Aplica filtro de mediana à evidência e calcula o resíduo (original −\n"
            "filtrada), útil para evidenciar texturas e ruído local.\n\n"
        ),
        "card": {"mode": "none"},
        "parameters": [
            {"name": "kernel_size", "type": "int", "default": 5, "min": 3, "max": 31},
        ],
        "artifacts": [
            {"key": "heatmap_path", "filename": "heatmap.png", "role": "heatmap"},
        ],
    }
    plugin_src = scaffold._render_plugin(m)
    ast.parse(plugin_src)
    assert "\nfiltrada" not in plugin_src.split("def description", 1)[1].split("def parameters_schema", 1)[0]
    # repr/normalize: uma string Python válida, sem newline cru no meio do literal
    assert "return " in plugin_src


def test_upsert_entry_between_markers(scaffold):
    text = (
        "export const X = {\n"
        "// --- scaffold:meta:start ---\n"
        "// --- scaffold:meta:end ---\n"
        "};\n"
    )
    entry = "  // scaffold-entry:foo\n  foo: { title: \"Foo\" },\n  // scaffold-entry-end:foo\n"
    updated = scaffold._upsert_entry_between_markers(
        text,
        "// --- scaffold:meta:start ---",
        "// --- scaffold:meta:end ---",
        "foo",
        entry,
    )
    assert "foo: { title: \"Foo\" }" in updated
    updated2 = scaffold._upsert_entry_between_markers(
        updated,
        "// --- scaffold:meta:start ---",
        "// --- scaffold:meta:end ---",
        "foo",
        "  // scaffold-entry:foo\n  foo: { title: \"Bar\" },\n  // scaffold-entry-end:foo\n",
    )
    assert updated2.count("scaffold-entry:foo") == 1
    assert 'title: "Bar"' in updated2


def test_example_manifests_validate(scaffold):
    for name in ("simple", "medium", "comparison", "ensemble"):
        path = ROOT / "scripts" / "technique" / "examples" / f"{name}.yaml"
        m = scaffold._load_manifest(path)
        assert scaffold.validate_manifest(m) == []


def test_validate_ensemble_requires_detectors(scaffold):
    errs = scaffold.validate_manifest(
        {
            "id": "ok_ensemble",
            "template": "ensemble",
            "media": "imagem",
            "title": "Ok",
            "card": {"mode": "none"},
            "ensemble": {"detectors": []},
            "artifacts": [],
        }
    )
    assert any("detectors" in e for e in errs)


def test_ensemble_config_and_plugin(scaffold):
    path = ROOT / "scripts" / "technique" / "examples" / "ensemble.yaml"
    m = scaffold._load_manifest(path)
    assert scaffold.validate_manifest(m) == []
    cfg = scaffold._ensemble_config(m)
    assert len(cfg["detectors"]) == 2
    assert cfg["selectedParam"] == "selected_analyses"
    assert cfg["scoreDisplay"]["positiveKey"] == "score_positive"
    lr = cfg["referenceLr"]
    assert lr["enabled"] is True
    assert lr["mode"] == "calibrated"
    assert lr["domain"] == "demo_ensemble_lr"
    assert lr["scoresPath"] == "features/scores/scores.csv"
    assert lr["featureMap"]["detector_a"] == "score_a"
    assert lr["allowTypicality"] is True
    assert len(lr["macros"]) >= 1
    assert lr["macros"][0]["bases"]
    plugin_src = scaffold._render_plugin(m)
    ast.parse(plugin_src)
    assert "selected_analyses" in plugin_src
    assert "reference_population" in plugin_src
    assert "use_latent_typicality" in plugin_src
    pipeline_src = scaffold._render_pipeline(m)
    ast.parse(pipeline_src)
    assert "individual_results" in pipeline_src
    assert "bigaussian" in pipeline_src.lower() or "reference_population" in pipeline_src


def test_validate_ensemble_calibrated_requires_domain(scaffold):
    errs = scaffold.validate_manifest(
        {
            "id": "ok_ensemble",
            "template": "ensemble",
            "media": "imagem",
            "title": "Ok",
            "card": {"mode": "none"},
            "ensemble": {
                "detectors": [{"id": "a", "label": "A"}],
                "reference_lr": {"mode": "calibrated", "enabled": True},
            },
            "artifacts": [],
        }
    )
    assert any("domain" in e for e in errs)
    assert any("feature_map" in e for e in errs)


def test_comparison_plugin_declares_forensic_roles(scaffold):
    path = ROOT / "scripts" / "technique" / "examples" / "comparison.yaml"
    m = scaffold._load_manifest(path)
    plugin_src = scaffold._render_plugin(m)
    ast.parse(plugin_src)
    assert "x-forensic-role" in plugin_src
    assert "reference_evidence_ids" in plugin_src
    assert "questioned_evidence_ids" in plugin_src
    pipeline_src = scaffold._render_pipeline(m)
    ast.parse(pipeline_src)
    assert "questioned_paths" in pipeline_src


def test_comparison_config_mapping(scaffold):
    cfg = scaffold._comparison_config(
        {
            "comparison": {
                "modes": ["with_reference"],
                "reference_source": "case_references",
                "min_questioned": 2,
                "min_references": 3,
            }
        }
    )
    assert cfg["modes"] == ["with_reference"]
    assert cfg["referenceSource"] == "case_references"
    assert cfg["minQuestioned"] == 2
    assert cfg["minReferences"] == 3


def test_dry_run_example_does_not_write(scaffold, tmp_path, monkeypatch):
    # Point ROOT to a temp tree with the marker files expected by apply_scaffold
    monkeypatch.setattr(scaffold, "ROOT", tmp_path)
    # minimal frontend/backend skeleton
    meta = tmp_path / "src/frontend/src/config/scaffoldedTechniqueMeta.ts"
    tech = tmp_path / "src/frontend/src/config/scaffoldedTechniques.tsx"
    routes = tmp_path / "src/frontend/src/config/scaffoldedRouteMeta.ts"
    groups = tmp_path / "src/frontend/src/config/scaffoldedMediaGroups.ts"
    papers_ts = tmp_path / "src/frontend/src/config/scaffoldedTechniquePapers.ts"
    papers_json = tmp_path / "docs/references/papers/imdl/scaffolded_manifest.json"
    arts = tmp_path / "src/backend/core/scaffolded_artifact_mappings.py"
    for p, body in [
        (
            meta,
            "export const SCAFFOLDED_TECHNIQUE_META = {\n"
            "// --- scaffold:meta:start ---\n"
            "// --- scaffold:meta:end ---\n"
            "};\n",
        ),
        (
            tech,
            "export const SCAFFOLDED_TECHNIQUES = [\n"
            "// --- scaffold:techniques:start ---\n"
            "// --- scaffold:techniques:end ---\n"
            "];\n",
        ),
        (
            routes,
            "export const SCAFFOLDED_ROUTE_META = {\n"
            "// --- scaffold:routes:start ---\n"
            "// --- scaffold:routes:end ---\n"
            "};\n",
        ),
        (
            groups,
            "export const SCAFFOLDED_MEDIA_GROUP_HOOKS = [\n"
            "// --- scaffold:media-groups:start ---\n"
            "// --- scaffold:media-groups:end ---\n"
            "];\n",
        ),
        (
            papers_ts,
            "export const SCAFFOLDED_TECHNIQUE_PAPER_IDS = new Set([\n"
            "// --- scaffold:papers:start ---\n"
            "// --- scaffold:papers:end ---\n"
            "]);\n",
        ),
        (
            papers_json,
            '{"description": "x", "techniques": {}}\n',
        ),
        (
            arts,
            "# --- scaffold:artifact-mappings:start ---\n"
            "SCAFFOLDED_ARTIFACT_MAPPINGS: list[tuple[str, str]] = []\n"
            "# --- scaffold:artifact-mappings:end ---\n",
        ),
    ]:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")

    m = scaffold._load_manifest(ROOT / "scripts/technique/examples/medium.yaml")
    actions = scaffold.apply_scaffold(m, dry_run=True)
    assert any(a.startswith("DRY") for a in actions)
    assert not (tmp_path / "src/backend/core/plugins/demo_medium_heatmap_plugin.py").exists()
    assert any("scaffolded_manifest.json" in a for a in actions)


def test_apply_paper_registers_download_hooks(scaffold, tmp_path, monkeypatch):
    monkeypatch.setattr(scaffold, "ROOT", tmp_path)
    papers_ts = tmp_path / "src/frontend/src/config/scaffoldedTechniquePapers.ts"
    papers_json = tmp_path / "docs/references/papers/imdl/scaffolded_manifest.json"
    # stubs mínimos exigidos pelo apply
    for rel, body in [
        (
            "src/frontend/src/config/scaffoldedTechniqueMeta.ts",
            "export const X = {\n// --- scaffold:meta:start ---\n// --- scaffold:meta:end ---\n};\n",
        ),
        (
            "src/frontend/src/config/scaffoldedTechniques.tsx",
            "export const X = [\n// --- scaffold:techniques:start ---\n// --- scaffold:techniques:end ---\n];\n",
        ),
        (
            "src/frontend/src/config/scaffoldedRouteMeta.ts",
            "export const X = {\n// --- scaffold:routes:start ---\n// --- scaffold:routes:end ---\n};\n",
        ),
        (
            "src/frontend/src/config/scaffoldedMediaGroups.ts",
            "export const X = [\n// --- scaffold:media-groups:start ---\n// --- scaffold:media-groups:end ---\n];\n",
        ),
        (
            "src/backend/core/scaffolded_artifact_mappings.py",
            "# --- scaffold:artifact-mappings:start ---\n"
            "SCAFFOLDED_ARTIFACT_MAPPINGS: list[tuple[str, str]] = []\n"
            "# --- scaffold:artifact-mappings:end ---\n",
        ),
    ]:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    papers_ts.parent.mkdir(parents=True, exist_ok=True)
    papers_ts.write_text(
        "export const SCAFFOLDED_TECHNIQUE_PAPER_IDS = new Set([\n"
        "// --- scaffold:papers:start ---\n"
        "// --- scaffold:papers:end ---\n"
        "]);\n",
        encoding="utf-8",
    )
    papers_json.parent.mkdir(parents=True, exist_ok=True)
    papers_json.write_text('{"techniques": {}}\n', encoding="utf-8")

    m = {
        "id": "paper_demo_tech",
        "template": "simple",
        "media": "imagem",
        "title": "Paper Demo",
        "citation": "AUTOR. Titulo.\n\nSegundo paragrafo.",
        "card": {"mode": "none"},
        "artifacts": [{"key": "heatmap_path", "filename": "heatmap.png", "role": "heatmap"}],
        "paper": {
            "title": "Demo Paper",
            "venue": "Demo 2024",
            "sources": ["https://doi.org/10.0/demo"],
            "local_file": "paper_demo_tech/demo.pdf",
        },
    }
    scaffold.apply_scaffold(m, dry_run=False, force=True)
    ts = papers_ts.read_text(encoding="utf-8")
    assert '"paper_demo_tech"' in ts
    data = json.loads(papers_json.read_text(encoding="utf-8"))
    assert "paper_demo_tech" in data["techniques"]
    assert data["techniques"]["paper_demo_tech"]["local_file"] == "paper_demo_tech/demo.pdf"
    readme = tmp_path / "docs/references/papers/imdl/paper_demo_tech/README.md"
    assert readme.is_file()
