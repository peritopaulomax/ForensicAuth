#!/usr/bin/env python3
"""Scaffold a simple/medium/comparison/ensemble forensic technique (plugin + UI wiring).

Usage:
  python scripts/technique/scaffold_technique.py path/to/manifest.yaml
  python scripts/technique/scaffold_technique.py --example simple
  python scripts/technique/scaffold_technique.py --example ensemble
  python scripts/technique/scaffold_technique.py path/to/manifest.yaml --dry-run

Author implements only ``src/backend/forensics/<id>/pipeline.py`` after scaffold.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = Path(__file__).resolve().parent / "examples"

ALLOWED_TEMPLATES = {"simple", "medium", "comparison", "ensemble"}
ALLOWED_MEDIA = {"imagem", "audio", "video", "pdf"}
ALLOWED_PARAM_TYPES = frozenset({"int", "float", "boolean", "string", "enum"})
ALLOWED_PARAM_WIDGETS = frozenset({"number", "slider", "select", "radio", "checkbox", "text"})
ALLOWED_COMPARISON_MODES = frozenset({"with_reference", "all_pairs"})
ALLOWED_REFERENCE_SOURCES = frozenset({"case_evidences", "case_references"})
# Roles com renderização na UI genérica (ver docs/developer/03-scaffold-technique.md).
ALLOWED_ARTIFACT_ROLES = frozenset(
    {
        "original",
        "input",
        "heatmap",
        "overlay",
        "mask",
        "score_map",
        "confidence",
        "detection",
        "interactive",
        "report",
        "plot_data",
        "plot",
        "matrix",
        "json",
        "txt",
        "download",
        "other",
    }
)
# Catálogo canônico de group_id por mídia (espelha imageAnalysisGroups / mediaAnalysisGroups).
KNOWN_GROUP_IDS: dict[str, frozenset[str]] = {
    "imagem": frozenset(
        {
            "estrutura-arquivo",
            "classicas-compressao",
            "classicas-correlacao",
            "classicas-aquisicao",
            "dl-manipulacao",
            "dl-sintetico",
            "dl-facial-spoofing",
        }
    ),
    "audio": frozenset({"audio-espectral", "audio-niveis", "audio-spoofing"}),
    "video": frozenset({"video-estrutura", "video-manipulacao"}),
    "pdf": frozenset({"pdf-estrutura", "pdf-conteudo"}),
}
ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
GROUP_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


def _load_manifest(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        if yaml is None:
            raise SystemExit("PyYAML é necessário para manifests .yaml (pip/conda install pyyaml)")
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise SystemExit("Manifest deve ser um objeto/mapping")
    return data


def validate_manifest(m: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    tid = m.get("id")
    if not isinstance(tid, str) or not ID_RE.match(tid):
        errors.append("id: snake_case [a-z][a-z0-9_]{1,63}")
    template = m.get("template")
    if template not in ALLOWED_TEMPLATES:
        errors.append(f"template: deve ser um de {sorted(ALLOWED_TEMPLATES)}")
    media = m.get("media")
    if media not in ALLOWED_MEDIA:
        errors.append(f"media: deve ser um de {sorted(ALLOWED_MEDIA)}")
    title = (m.get("title") or "").strip()
    if not title:
        errors.append("title: obrigatório")
    card = m.get("card") or {}
    if not isinstance(card, dict):
        errors.append("card: objeto esperado")
    else:
        mode = card.get("mode", "existing")
        if mode not in {"existing", "new", "none"}:
            errors.append("card.mode: existing | new | none")
        if mode == "existing":
            gid = card.get("group_id")
            if not gid:
                errors.append(
                    "card.group_id: obrigatório quando card.mode=existing "
                    f"(media={media!r}; ver catálogo em docs/developer/03-scaffold-technique.md §5)"
                )
            elif media in KNOWN_GROUP_IDS and gid not in KNOWN_GROUP_IDS[media]:
                known = ", ".join(sorted(KNOWN_GROUP_IDS[media]))
                errors.append(
                    f"card.group_id: {gid!r} não existe para media={media!r}. "
                    f"Use um de: {known} — ou card.mode=new"
                )
        if mode == "new":
            if not (card.get("title") and card.get("description")):
                errors.append(
                    "card.title e card.description: obrigatórios quando card.mode=new "
                    f"(vale para media={media!r})"
                )
            gid = card.get("group_id")
            if gid is not None and not (isinstance(gid, str) and GROUP_ID_RE.match(gid)):
                errors.append(
                    "card.group_id: kebab-case [a-z][a-z0-9_-]{1,63} quando informado com mode=new"
                )
    arts = m.get("artifacts") or []
    if not isinstance(arts, list):
        errors.append("artifacts: lista esperada")
    else:
        for i, a in enumerate(arts):
            if not isinstance(a, dict) or not a.get("filename") or not a.get("key"):
                errors.append(f"artifacts[{i}]: precisa de key e filename")
                continue
            role = a.get("role", "other")
            if role not in ALLOWED_ARTIFACT_ROLES:
                errors.append(
                    f"artifacts[{i}].role: inválido {role!r} "
                    f"(use um de {sorted(ALLOWED_ARTIFACT_ROLES)})"
                )
    params = m.get("parameters") or []
    if not isinstance(params, list):
        errors.append("parameters: lista esperada")
    else:
        for i, p in enumerate(params):
            if not isinstance(p, dict) or not p.get("name"):
                errors.append(f"parameters[{i}]: precisa de name")
                continue
            ptype = p.get("type", "string")
            if ptype not in ALLOWED_PARAM_TYPES:
                errors.append(f"parameters[{i}].type: deve ser um de {sorted(ALLOWED_PARAM_TYPES)}")
            widget = p.get("widget")
            if widget is not None and widget not in ALLOWED_PARAM_WIDGETS:
                errors.append(
                    f"parameters[{i}].widget: deve ser um de {sorted(ALLOWED_PARAM_WIDGETS)}"
                )
            if widget == "slider" and ptype not in {"int", "float"}:
                errors.append(f"parameters[{i}]: widget=slider exige type int ou float")
            if widget == "slider" and ("min" not in p or "max" not in p):
                errors.append(f"parameters[{i}]: widget=slider exige min e max")
            if widget == "radio" and ptype != "enum":
                errors.append(f"parameters[{i}]: widget=radio exige type enum")
            if ptype == "enum" and not p.get("options"):
                errors.append(f"parameters[{i}]: type enum exige options[]")
    if template == "comparison":
        cmp = m.get("comparison") or {}
        if not isinstance(cmp, dict):
            errors.append("comparison: objeto esperado")
        else:
            modes = cmp.get("modes") or ["with_reference", "all_pairs"]
            if not isinstance(modes, list) or not modes:
                errors.append("comparison.modes: lista não vazia")
            else:
                for mode in modes:
                    if mode not in ALLOWED_COMPARISON_MODES:
                        errors.append(
                            f"comparison.modes: inválido {mode!r} "
                            f"(use {sorted(ALLOWED_COMPARISON_MODES)})"
                        )
            ref_src = cmp.get("reference_source", "case_evidences")
            if ref_src not in ALLOWED_REFERENCE_SOURCES:
                errors.append(
                    f"comparison.reference_source: deve ser um de "
                    f"{sorted(ALLOWED_REFERENCE_SOURCES)}"
                )
    if template == "ensemble":
        ens = m.get("ensemble") or {}
        if not isinstance(ens, dict):
            errors.append("ensemble: objeto esperado")
        else:
            dets = ens.get("detectors") or []
            if not isinstance(dets, list) or not dets:
                errors.append("ensemble.detectors: lista não vazia obrigatória")
            else:
                for i, d in enumerate(dets):
                    if not isinstance(d, dict) or not d.get("id") or not d.get("label"):
                        errors.append(f"ensemble.detectors[{i}]: precisa de id e label")
            headers = ens.get("result_headers")
            if headers is not None and (not isinstance(headers, list) or not headers):
                errors.append("ensemble.result_headers: lista não vazia se presente")
            lr = ens.get("reference_lr")
            if isinstance(lr, dict):
                mode = str(lr.get("mode") or "result_only").strip()
                if mode not in {"result_only", "calibrated"}:
                    errors.append("ensemble.reference_lr.mode: result_only | calibrated")
                if mode == "calibrated" and lr.get("enabled", True):
                    if not str(lr.get("domain") or "").strip():
                        errors.append("ensemble.reference_lr.domain: obrigatório quando mode=calibrated")
                    fmap = lr.get("feature_map")
                    if not isinstance(fmap, dict) or not fmap:
                        errors.append(
                            "ensemble.reference_lr.feature_map: dict detector→coluna "
                            "obrigatório quando mode=calibrated"
                        )
                    scores = str(lr.get("scores_path") or "").strip()
                    if not scores:
                        errors.append(
                            "ensemble.reference_lr.scores_path: obrigatório quando mode=calibrated"
                        )
                    has_macros = bool(lr.get("macros"))
                    has_endpoint = bool(str(lr.get("catalog_endpoint") or "").strip())
                    if not has_macros and not has_endpoint:
                        errors.append(
                            "ensemble.reference_lr: mode=calibrated exige macros inline "
                            "ou catalog_endpoint"
                        )
    return errors


def _macros_yaml_to_catalog(macros_raw: Any) -> list[dict[str, Any]]:
    """Convert macros dict (catalog style) or list into MacroCategory[] for the UI."""
    catalog: list[dict[str, Any]] = []
    if isinstance(macros_raw, list):
        for row in macros_raw:
            if isinstance(row, dict) and row.get("id") and isinstance(row.get("bases"), list):
                catalog.append(row)
        return catalog
    if not isinstance(macros_raw, dict):
        return catalog
    for macro_id, raw in macros_raw.items():
        if not isinstance(raw, dict):
            continue
        bases: dict[str, dict[str, Any]] = {}
        for item in raw.get("items") or []:
            if not isinstance(item, dict):
                continue
            base_id = str(item.get("base_group") or item.get("base") or "").strip()
            sub = str(item.get("subgroup") or item.get("generator") or "").strip()
            if not base_id or not sub:
                continue
            base = bases.setdefault(
                base_id,
                {"id": base_id, "label": base_id, "generators": []},
            )
            base["generators"].append({"id": sub, "label": sub})
        catalog.append(
            {
                "id": str(macro_id),
                "label": str(raw.get("label") or macro_id),
                "year_range": raw.get("year_range"),
                "description": str(raw.get("description") or ""),
                "bases": list(bases.values()),
            }
        )
    return catalog


def _comparison_config(m: dict[str, Any]) -> dict[str, Any]:
    cmp = m.get("comparison") or {}
    if not isinstance(cmp, dict):
        cmp = {}
    modes = cmp.get("modes") or ["with_reference", "all_pairs"]
    return {
        "modes": list(modes),
        "referenceSource": cmp.get("reference_source", "case_evidences"),
        "minQuestioned": int(cmp.get("min_questioned", 1)),
        "minReferences": int(cmp.get("min_references", 1)),
    }


def _ensemble_config(m: dict[str, Any]) -> dict[str, Any]:
    ens = m.get("ensemble") or {}
    if not isinstance(ens, dict):
        ens = {}
    detectors = []
    for d in ens.get("detectors") or []:
        if isinstance(d, dict) and d.get("id"):
            detectors.append({"id": str(d["id"]), "label": str(d.get("label") or d["id"])})
    out: dict[str, Any] = {
        "detectors": detectors,
        "selectedParam": str(ens.get("selected_param") or "selected_analyses"),
    }
    headers = ens.get("result_headers")
    if isinstance(headers, list) and headers:
        out["resultHeaders"] = [str(h) for h in headers]
    score = ens.get("score_display") or {}
    if isinstance(score, dict) and score:
        sd: dict[str, str] = {}
        if score.get("positive_key"):
            sd["positiveKey"] = str(score["positive_key"])
        if score.get("negative_key"):
            sd["negativeKey"] = str(score["negative_key"])
        if score.get("label_key"):
            sd["labelKey"] = str(score["label_key"])
        if sd:
            out["scoreDisplay"] = sd
    lr = ens.get("reference_lr")
    if isinstance(lr, dict):
        mode = str(lr.get("mode") or "result_only").strip()
        if mode not in {"result_only", "calibrated"}:
            mode = "result_only"
        ref: dict[str, Any] = {
            "enabled": bool(lr.get("enabled", True)),
            "mode": mode,
            "populationUnitLabel": str(lr.get("population_unit_label") or "amostras"),
            "lrPositiveLabel": str(lr.get("lr_positive_label") or "real"),
        }
        if lr.get("domain"):
            ref["domain"] = str(lr["domain"]).strip()
        if lr.get("catalog_endpoint"):
            ref["catalogEndpoint"] = str(lr["catalog_endpoint"]).strip()
        if lr.get("scores_path"):
            ref["scoresPath"] = str(lr["scores_path"]).strip()
        if lr.get("embeddings_path"):
            ref["embeddingsPath"] = str(lr["embeddings_path"]).strip()
        fmap = lr.get("feature_map")
        if isinstance(fmap, dict) and fmap:
            ref["featureMap"] = {str(k): str(v) for k, v in fmap.items()}
        emap = lr.get("embedding_map")
        if isinstance(emap, dict) and emap:
            ref["embeddingMap"] = {str(k): str(v) for k, v in emap.items()}
        ref["allowAugmented"] = bool(lr.get("allow_augmented", False))
        ref["allowTypicality"] = bool(lr.get("allow_typicality", False))
        ref["allowMetaClassifier"] = bool(lr.get("allow_meta_classifier", mode == "calibrated"))
        ref["enableSplitRoles"] = bool(lr.get("enable_split_roles", mode == "calibrated"))
        if lr.get("default_meta_classifier"):
            raw_clf = str(lr["default_meta_classifier"]).strip().lower()
            # Canonical ids: logistic | xgboost (legacy logistic_regression → logistic)
            if raw_clf in ("logistic_regression", "logreg"):
                raw_clf = "logistic"
            elif raw_clf in ("xgb",):
                raw_clf = "xgboost"
            if raw_clf not in ("logistic", "xgboost"):
                raise ValueError(
                    f"default_meta_classifier inválido: {lr['default_meta_classifier']!r} "
                    "(use logistic ou xgboost)"
                )
            ref["defaultMetaClassifier"] = raw_clf
        else:
            ref["defaultMetaClassifier"] = "logistic"
        if lr.get("subgroup_unit_label"):
            ref["subgroupUnitLabel"] = str(lr["subgroup_unit_label"])
        if lr.get("hypothesis_hint"):
            ref["hypothesisHint"] = str(lr["hypothesis_hint"])
        macros_cat = _macros_yaml_to_catalog(lr.get("macros"))
        if macros_cat:
            ref["macros"] = macros_cat
        defaults = lr.get("default_reference_items") or []
        if isinstance(defaults, list) and defaults:
            items = []
            for it in defaults:
                if isinstance(it, dict) and it.get("base_group") and it.get("subgroup"):
                    items.append(
                        {
                            "base_group": str(it["base_group"]),
                            "subgroup": str(it["subgroup"]),
                        }
                    )
            if items:
                ref["defaultReferenceItems"] = items
        out["referenceLr"] = ref
    else:
        out["referenceLr"] = {
            "enabled": True,
            "mode": "result_only",
            "populationUnitLabel": "amostras",
            "lrPositiveLabel": "real",
        }
    return out


def _class_name(technique_id: str) -> str:
    return "".join(p.capitalize() for p in technique_id.split("_")) + "Plugin"


def _normalize_text(value: Any) -> str:
    """Collapse YAML folded newlines / odd whitespace into a single-line string."""
    if value is None:
        return ""
    return " ".join(str(value).split())


def _render_plugin(m: dict[str, Any]) -> str:
    tid = m["id"]
    cls = _class_name(tid)
    media = m["media"]
    desc = _normalize_text(m.get("description") or m.get("subtitle") or m["title"])
    params = m.get("parameters") or []
    arts = m.get("artifacts") or []
    is_comparison = m.get("template") == "comparison"
    is_ensemble = m.get("template") == "ensemble"

    schema_props: dict[str, Any] = {}
    for p in params:
        name = p["name"]
        ptype = p.get("type", "string")
        prop: dict[str, Any] = {}
        if ptype == "int":
            prop["type"] = "integer"
        elif ptype == "float":
            prop["type"] = "number"
        elif ptype == "boolean":
            prop["type"] = "boolean"
        else:
            prop["type"] = "string"
        if "default" in p:
            prop["default"] = p["default"]
        if "min" in p:
            prop["minimum"] = p["min"]
        if "max" in p:
            prop["maximum"] = p["max"]
        if ptype == "enum" and p.get("options"):
            prop["type"] = "string"
            prop["enum"] = list(p["options"])
        schema_props[name] = prop

    if is_comparison:
        schema_props["mode"] = {
            "type": "string",
            "enum": ["with_reference", "all_pairs"],
            "default": "with_reference",
        }
        schema_props["case_id"] = {"type": "string", "format": "uuid"}
        schema_props["questioned_evidence_ids"] = {
            "type": "array",
            "items": {"type": "string", "format": "uuid"},
            "x-forensic-role": "questioned",
            "x-forensic-media": media,
            "x-forensic-multiple": True,
        }
        schema_props["reference_evidence_ids"] = {
            "type": "array",
            "items": {"type": "string", "format": "uuid"},
            "x-forensic-role": "reference",
            "x-forensic-media": media,
            "x-forensic-multiple": True,
        }

    if is_ensemble:
        ens = m.get("ensemble") or {}
        selected_param = str(ens.get("selected_param") or "selected_analyses")
        schema_props[selected_param] = {
            "type": "array",
            "items": {"type": "string"},
            "description": "Ids dos detectores/análises selecionados na UI",
        }
        lr = ens.get("reference_lr") if isinstance(ens.get("reference_lr"), dict) else {}
        lr_mode = str((lr or {}).get("mode") or "result_only")
        if lr_mode == "calibrated" and (lr or {}).get("enabled", True):
            schema_props["reference_lr_enabled"] = {
                "type": "boolean",
                "default": True,
                "description": "Calcular LR de referência (população)",
            }
            schema_props["reference_population"] = {
                "type": "object",
                "description": (
                    "Seleção de população: items / fit_items / test_items "
                    "(base_group + subgroup), espelho áudio spoofing"
                ),
            }
            _raw_meta = str((lr or {}).get("default_meta_classifier") or "logistic").strip().lower()
            _meta_aliases = {
                "logistic_regression": "logistic",
                "logreg": "logistic",
                "xgb": "xgboost",
            }
            _meta_default = _meta_aliases.get(_raw_meta, _raw_meta)
            if _meta_default not in ("logistic", "xgboost"):
                _meta_default = "logistic"
            schema_props["meta_classifier"] = {
                "type": "string",
                "enum": ["logistic", "xgboost"],
                "default": _meta_default,
                "description": "Meta-classificador LR: logistic | xgboost",
            }
            schema_props["use_augmented_reference"] = {
                "type": "boolean",
                "default": False,
            }
            schema_props["use_latent_typicality"] = {
                "type": "boolean",
                "default": False,
            }
            if (lr or {}).get("domain"):
                schema_props["reference_lr_domain"] = {
                    "type": "string",
                    "default": str(lr["domain"]),
                    "description": "Domínio reference_data/<domain>/",
                }

    result_arts = [
        {
            "key": a["key"],
            "filename": a["filename"],
            "role": a.get("role", "other"),
        }
        for a in arts
    ]
    savable = [a["key"] for a in arts if a.get("savable", True)]
    parent_roles = ["questioned", "reference"] if is_comparison else ["questioned"]

    validate_lines = ["        return True, \"\""]
    body_validate: list[str] = []
    if is_comparison:
        body_validate.extend(
            [
                "        mode = parameters.get(\"mode\", \"with_reference\")",
                "        if mode not in (\"with_reference\", \"all_pairs\"):",
                "            return False, \"mode inválido\"",
                "        q_ids = parameters.get(\"questioned_evidence_ids\") or []",
                "        if not isinstance(q_ids, list) or not q_ids:",
                "            return False, \"questioned_evidence_ids obrigatório\"",
                "        if mode == \"all_pairs\" and len(q_ids) < 2:",
                "            return False, \"all_pairs exige ao menos 2 questionados\"",
                "        if mode == \"with_reference\":",
                "            r_ids = parameters.get(\"reference_evidence_ids\") or []",
                "            if not isinstance(r_ids, list) or not r_ids:",
                "                return False, \"reference_evidence_ids obrigatório no modo com referência\"",
            ]
        )
    if is_ensemble:
        ens = m.get("ensemble") or {}
        selected_param = str(ens.get("selected_param") or "selected_analyses")
        body_validate.extend(
            [
                f"        sel = parameters.get({selected_param!r}) or []",
                "        if not isinstance(sel, list) or not sel:",
                f"            return False, {selected_param!r} + \" deve ser lista não vazia\"",
            ]
        )
        lr = ens.get("reference_lr") if isinstance(ens.get("reference_lr"), dict) else {}
        if str((lr or {}).get("mode") or "result_only") == "calibrated" and (lr or {}).get("enabled", True):
            body_validate.extend(
                [
                    "        if parameters.get(\"reference_lr_enabled\", True):",
                    "            pop = parameters.get(\"reference_population\")",
                    "            if not isinstance(pop, dict):",
                    "                return False, \"reference_population deve ser objeto\"",
                    "            fit = pop.get(\"fit_items\") or pop.get(\"items\") or []",
                    "            test = pop.get(\"test_items\") or pop.get(\"items\") or []",
                    "            if not fit or not test:",
                    "                return False, \"reference_population exige fit e test (ou items)\"",
                ]
            )
    for p in params:
        name = p["name"]
        ptype = p.get("type", "string")
        default = p.get("default")
        if ptype == "int":
            body_validate.append(f"        {name} = parameters.get({name!r}, {default!r})")
            body_validate.append(f"        if not isinstance({name}, int):")
            body_validate.append(f"            return False, {name!r} + \" deve ser int\"")
            if "min" in p and "max" in p:
                body_validate.append(
                    f"        if not ({p['min']} <= {name} <= {p['max']}):"
                )
                body_validate.append(
                    f"            return False, \"{name} fora do intervalo\""
                )
        elif ptype == "float":
            body_validate.append(f"        {name} = parameters.get({name!r}, {default!r})")
            body_validate.append(f"        if not isinstance({name}, (int, float)):")
            body_validate.append(f"            return False, {name!r} + \" deve ser número\"")
        elif ptype == "boolean":
            body_validate.append(f"        if {name!r} in parameters and not isinstance(parameters[{name!r}], bool):")
            body_validate.append(f"            return False, {name!r} + \" deve ser bool\"")
        elif ptype == "enum":
            opts = p.get("options") or []
            body_validate.append(f"        {name} = parameters.get({name!r}, {default!r})")
            body_validate.append(f"        if {name} not in {opts!r}:")
            body_validate.append(f"            return False, \"{name} inválido\"")

    if body_validate:
        validate_lines = body_validate + ["        return True, \"\""]

    parameters_schema = {"type": "object", "properties": schema_props}
    result_schema = {"artifacts": result_arts}

    return f'''"""Auto-generated adapter for technique ``{tid}``.

Implement the analysis in ``forensics/{tid}/pipeline.py`` (``run``).
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from core.forensic_plugin import ForensicPlugin
from core.job_staging import job_artifact_dir
from core.progress import pop_progress_callback, report_progress
from forensics.{tid}.pipeline import run as run_pipeline


class {cls}(ForensicPlugin):
    @property
    def name(self) -> str:
        return "{tid}"

    @property
    def supported_types(self) -> list[str]:
        return ["{media}"]

    @property
    def description(self) -> str | None:
        return {desc!r}

    @property
    def parameters_schema(self) -> dict[str, Any] | None:
        return {parameters_schema!r}

    @property
    def result_schema(self) -> dict[str, Any] | None:
        return {result_schema!r}

    @property
    def provenance_contract(self) -> dict[str, Any] | None:
        return {{
            "parent_roles": {parent_roles!r},
            "savable_artifacts": {savable!r},
        }}

    def validate_parameters(self, parameters: Dict[str, Any]) -> Tuple[bool, str]:
{chr(10).join(validate_lines)}

    def analyze(self, evidence_path: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        on_progress = pop_progress_callback(parameters)
        report_progress(on_progress, 5, "Iniciando {tid}")
        out_dir = job_artifact_dir(parameters, fallback_subdir="{tid}")
        result = run_pipeline(evidence_path, dict(parameters), out_dir, on_progress=on_progress)
        if not isinstance(result, dict):
            return {{"success": False, "error": "pipeline retornou tipo inválido", "adapter": "{tid}"}}
        result.setdefault("adapter", "{tid}")
        return result
'''


def _render_pipeline(m: dict[str, Any]) -> str:
    tid = m["id"]
    arts = m.get("artifacts") or []
    is_comparison = m.get("template") == "comparison"
    is_ensemble = m.get("template") == "ensemble"
    art_comments = "\n".join(
        f"    #   - {a['key']} → out_dir / {a['filename']!r}  (role={a.get('role', 'other')})"
        for a in arts
    ) or "    #   (nenhum artefato declarado no manifesto)"
    comparison_notes = ""
    if is_comparison:
        comparison_notes = """
    # Comparison — parâmetros relevantes (após resolve do JobService):
    #   mode: \"with_reference\" | \"all_pairs\"
    #   questioned_evidence_ids / reference_evidence_ids
    #   questioned_paths / reference_paths (+ *_labels)
    # Devolva ao menos: success, mode, reference_count, questioned_count
    # e paths dos artefatos (heatmaps PNG e/ou metrics.*.matrix no JSON).
"""
    elif is_ensemble:
        comparison_notes = """
    # Ensemble — parâmetros relevantes:
    #   selected_analyses: list[str] (ids dos detectores escolhidos na UI)
    # Devolva ao menos: success, individual_results (lista de linhas, tipicamente 6 cols),
    # e opcionalmente reference_lr + scores agregados + artefatos do manifesto.
    #
    # Se reference_lr.mode=calibrated (Wave 2), também chegam:
    #   reference_lr_enabled, reference_population {fit_items,test_items|items},
    #   meta_classifier (logistic | xgboost), use_augmented_reference,
    #   use_latent_typicality, reference_lr_domain (opcional)
    # Features da população vêm de reference_data/<domain>/ (scores_path / embeddings_path
    # do manifesto) — já publicadas offline; o pipeline NÃO extrai a base inteira aqui.
    # Calibração esperada (espelho áudio/imagem): meta (logistic|xgboost) no train →
    # bigaussianização → Tippett/Cllr/EER no test + LR do questionado.
    # OBRIGATÓRIO: treinar o meta via
    #   core.synthetic_lr_reference.train_meta_classifier
    # (logistic = StandardScaler/z-score + LogisticRegression). NÃO use
    # LogisticRegression cru — escalas de logit entre detectores não são comparáveis.
    # Em reference_lr inclua feature_weights (+ feature_values, logreg_coefficients/
    # logreg_intercept se logistic) para o painel colapsado de coeficientes/importâncias.
"""
    return f'''"""Pipeline forense — técnica ``{tid}``.

Preencha ``run``: leia a evidência, grave derivados em ``out_dir`` e devolva
o dicionário de resultado (success, métricas e chaves *_path dos artefatos).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


ProgressCb = Callable[[int, str], None] | None


def run(
    evidence_path: str,
    parameters: dict[str, Any],
    out_dir: Path,
    *,
    on_progress: ProgressCb = None,
) -> dict[str, Any]:
    """Executa a análise.

    Artefatos esperados (gravar sob ``out_dir`` e retornar os paths):
{art_comments}
{comparison_notes}    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if on_progress:
        on_progress(10, "TODO: carregar evidência")

    # TODO: implementar a técnica. Exemplo mínimo (falha explícita até preencher):
    _ = evidence_path, parameters
    if on_progress:
        on_progress(100, "Pipeline ainda não implementado")
    return {{
        "success": False,
        "error": "Implemente forensics/{tid}/pipeline.py (função run)",
        "adapter": "{tid}",
    }}
'''


def _render_init() -> str:
    return '"""Forensic pipeline package (scaffolded)."""\n'


def _render_unit_test(m: dict[str, Any]) -> str:
    tid = m["id"]
    cls = _class_name(tid)
    return f'''"""Smoke tests for scaffolded technique ``{tid}``."""

from __future__ import annotations

from core.plugin_registry import get_plugin_registry
from core.plugins.{tid}_plugin import {cls}


def test_{tid}_plugin_registered():
    registry = get_plugin_registry(rediscover=True)
    assert "{tid}" in registry.list_plugins()


def test_{tid}_validate_defaults():
    plugin = {cls}()
    ok, msg = plugin.validate_parameters({{}})
    assert ok, msg


def test_{tid}_pipeline_stub_returns_dict(tmp_path):
    from forensics.{tid}.pipeline import run

    result = run(str(tmp_path / "missing.bin"), {{}}, tmp_path)
    assert isinstance(result, dict)
    assert "success" in result
'''


def _ts_parameter_defs(params: list[dict[str, Any]]) -> str:
    if not params:
        return "[]"
    parts: list[str] = ["["]
    for p in params:
        fields = [f'name: "{p["name"]}"', f'type: "{p.get("type", "string")}"']
        if p.get("widget"):
            fields.append(f'widget: "{p["widget"]}"')
        if p.get("label"):
            fields.append(f'label: {json.dumps(p["label"], ensure_ascii=False)}')
        if "default" in p:
            fields.append(f"default: {json.dumps(p['default'])}")
        if "min" in p:
            fields.append(f"min: {p['min']}")
        if "max" in p:
            fields.append(f"max: {p['max']}")
        if p.get("step") is not None:
            fields.append(f"step: {p['step']}")
        if p.get("options"):
            fields.append(f"options: {json.dumps(p['options'])}")
        if p.get("description"):
            fields.append(f'description: {json.dumps(p["description"], ensure_ascii=False)}')
        parts.append(f"    {{ {', '.join(fields)} }},")
    parts.append("  ]")
    return "\n".join(parts)


def _ts_artifact_manifest(arts: list[dict[str, Any]]) -> str:
    if not arts:
        return "[]"
    lines = ["["]
    for a in arts:
        role = a.get("role", "other")
        label = a.get("label") or a["filename"]
        lines.append(
            f'    {{ filename: "{a["filename"]}", label: {json.dumps(label, ensure_ascii=False)}, role: "{role}" }},'
        )
    lines.append("  ]")
    return "\n".join(lines)


def _default_parameters(params: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for p in params:
        if "default" in p:
            out[p["name"]] = p["default"]
    return out


def _upsert_entry_between_markers(
    text: str,
    start: str,
    end: str,
    entry_id: str,
    entry_block: str,
) -> str:
    """Replace existing entry for entry_id or append inside markers."""
    m = re.search(re.escape(start) + r"(.*?)" + re.escape(end), text, re.DOTALL)
    if not m:
        raise SystemExit(f"Marcadores não encontrados: {start}")
    body = m.group(1)
    # Remove previous block tagged with id comment
    body = re.sub(
        rf"\n?[ \t]*// scaffold-entry:{re.escape(entry_id)}\n.*?// scaffold-entry-end:{re.escape(entry_id)}\n?",
        "\n",
        body,
        flags=re.DOTALL,
    )
    new_body = body.rstrip() + "\n" + entry_block.rstrip() + "\n"
    return text[: m.start()] + start + new_body + end + text[m.end() :]


def _py_upsert_mapping_list(text: str, start: str, end: str, pairs: list[tuple[str, str]]) -> str:
    m = re.search(re.escape(start) + r"(.*?)" + re.escape(end), text, re.DOTALL)
    if not m:
        raise SystemExit("Marcadores de artifact mappings não encontrados")
    body = m.group(1)
    # Keep existing list assignment structure
    existing: list[tuple[str, str]] = []
    for match in re.finditer(r'\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)', body):
        existing.append((match.group(1), match.group(2)))
    by_key = {k: v for k, v in existing}
    for k, v in pairs:
        by_key[k] = v
    lines = ["SCAFFOLDED_ARTIFACT_MAPPINGS: list[tuple[str, str]] = ["]
    for k, v in sorted(by_key.items()):
        lines.append(f'    ("{k}", "{v}"),')
    lines.append("]")
    inner = "\n".join(lines) + "\n"
    return text[: m.start()] + start + "\n" + inner + end + text[m.end() :]


def plan_files(m: dict[str, Any]) -> dict[str, Path]:
    tid = m["id"]
    return {
        "plugin": ROOT / "src/backend/core/plugins" / f"{tid}_plugin.py",
        "pipeline": ROOT / "src/backend/forensics" / tid / "pipeline.py",
        "init": ROOT / "src/backend/forensics" / tid / "__init__.py",
        "test": ROOT / "tests/unit" / f"test_{tid}_plugin.py",
        "manifest_copy": ROOT / "config/techniques" / f"{tid}.yaml",
        "meta": ROOT / "src/frontend/src/config/scaffoldedTechniqueMeta.ts",
        "techniques": ROOT / "src/frontend/src/config/scaffoldedTechniques.tsx",
        "routes": ROOT / "src/frontend/src/config/scaffoldedRouteMeta.ts",
        "groups": ROOT / "src/frontend/src/config/scaffoldedMediaGroups.ts",
        "papers_ts": ROOT / "src/frontend/src/config/scaffoldedTechniquePapers.ts",
        "papers_json": ROOT / "docs/references/papers/imdl/scaffolded_manifest.json",
        "artifacts": ROOT / "src/backend/core/scaffolded_artifact_mappings.py",
    }


def _upsert_scaffolded_paper_json(
    path: Path,
    tid: str,
    paper: dict[str, Any],
    *,
    dry_run: bool,
) -> str:
    """Merge technique paper entry into scaffolded_manifest.json."""
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"description": "PDFs de técnicas geradas pelo scaffold.", "techniques": {}}
    if not isinstance(data, dict):
        data = {"techniques": {}}
    techniques = data.setdefault("techniques", {})
    if not isinstance(techniques, dict):
        techniques = {}
        data["techniques"] = techniques

    local_file = paper.get("local_file") or f"{tid}/{tid}_paper.pdf"
    entry: dict[str, Any] = {
        "title": paper.get("title") or tid,
        "venue": paper.get("venue") or "",
        "local_file": local_file,
    }
    sources = paper.get("sources")
    if isinstance(sources, list) and sources:
        entry["sources"] = [str(s) for s in sources]
    if paper.get("repo"):
        entry["repo"] = str(paper["repo"])
    techniques[tid] = entry

    action = f"{'DRY ' if dry_run else 'PATCH'} {path.relative_to(ROOT)}"
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Pasta para o PDF + README
        pdf_rel = Path(str(local_file))
        paper_dir = path.parent / pdf_rel.parent
        paper_dir.mkdir(parents=True, exist_ok=True)
        readme = paper_dir / "README.md"
        if not readme.is_file():
            readme.write_text(
                f"# Paper — `{tid}`\n\n"
                f"Coloque o PDF em:\n\n"
                f"`docs/references/papers/imdl/{local_file}`\n\n"
                f"Após copiar o arquivo (>1KB), o botão de download na UI fica disponível.\n",
                encoding="utf-8",
            )
    return action


def apply_scaffold(m: dict[str, Any], *, dry_run: bool = False, force: bool = False) -> list[str]:
    errors = validate_manifest(m)
    if errors:
        raise SystemExit("Manifest inválido:\n- " + "\n- ".join(errors))

    # Canonicalize text fields so YAML folded blocks don't break generated Python.
    m = dict(m)
    if "title" in m:
        m["title"] = _normalize_text(m["title"])
    if m.get("subtitle") is not None:
        m["subtitle"] = _normalize_text(m.get("subtitle"))
    if m.get("description") is not None:
        m["description"] = _normalize_text(m.get("description"))

    tid = m["id"]
    paths = plan_files(m)
    actions: list[str] = []

    # --- backend files ---
    writes: list[tuple[Path, str, bool]] = [
        (paths["plugin"], _render_plugin(m), force),
        (paths["pipeline"], _render_pipeline(m), False),  # never overwrite author code unless force
        (paths["init"], _render_init(), force),
        (paths["test"], _render_unit_test(m), force),
    ]

    for path, content, allow_overwrite in writes:
        if path.exists() and not allow_overwrite and path.name == "pipeline.py" and not force:
            actions.append(f"SKIP  {path.relative_to(ROOT)} (já existe — preserve a implementação)")
            continue
        if path.exists() and not force and path.name != "pipeline.py":
            # allow regenerating adapter/test with --force; without force skip if exists
            if path.suffix == ".py" and path.name.endswith("_plugin.py"):
                actions.append(f"SKIP  {path.relative_to(ROOT)} (use --force para sobrescrever)")
                continue
        actions.append(f"{'DRY ' if dry_run else 'WRITE'} {path.relative_to(ROOT)}")
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.name == "pipeline.py" and path.exists() and not force:
                continue
            path.write_text(content, encoding="utf-8")

    # manifest copy
    if yaml is not None:
        actions.append(f"{'DRY ' if dry_run else 'WRITE'} {paths['manifest_copy'].relative_to(ROOT)}")
        if not dry_run:
            paths["manifest_copy"].parent.mkdir(parents=True, exist_ok=True)
            paths["manifest_copy"].write_text(
                yaml.safe_dump(m, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

    # --- frontend marker patches ---
    title = _normalize_text(m["title"])
    subtitle = _normalize_text(m.get("subtitle") or "")
    detail = _normalize_text(m.get("description") or subtitle or title)
    citation = m.get("citation") or ""
    if isinstance(citation, str):
        # Preserva parágrafos ABNT (\n\n); só normaliza espaços dentro de cada bloco.
        citation = "\n\n".join(
            _normalize_text(block) for block in re.split(r"\n\s*\n", citation) if block.strip()
        )
    license_s = _normalize_text(m.get("license") or "") if m.get("license") else ""
    repo_url = (m.get("repo_url") or m.get("repo") or "").strip() if (m.get("repo_url") or m.get("repo")) else ""

    meta_extra = ""
    if license_s:
        meta_extra += f",\n    license: {json.dumps(license_s, ensure_ascii=False)}"
    if repo_url:
        meta_extra += f",\n    repoUrl: {json.dumps(repo_url, ensure_ascii=False)}"

    meta_entry = f'''  // scaffold-entry:{tid}
  {tid}: {{
    title: {json.dumps(title, ensure_ascii=False)},
    citation: {json.dumps(citation, ensure_ascii=False)},
    cardSubtitle: {json.dumps(subtitle, ensure_ascii=False)},
    detail: {json.dumps(detail, ensure_ascii=False)}{meta_extra},
  }},
  // scaffold-entry-end:{tid}
'''

    params = m.get("parameters") or []
    arts = m.get("artifacts") or []
    defaults = _default_parameters(params)
    gpu = bool(m.get("gpu", False))
    disabled = bool(m.get("disabled", False))
    admin_only = bool(m.get("admin_only", False))
    is_comparison = m.get("template") == "comparison"
    is_ensemble = m.get("template") == "ensemble"
    if is_comparison:
        component_name = "GenericComparisonAnalysis"
    elif is_ensemble:
        component_name = "GenericEnsembleAnalysis"
    else:
        component_name = "GenericTechniqueAnalysis"
    comparison_field = ""
    if is_comparison:
        comparison_field = (
            f",\n    comparisonConfig: {json.dumps(_comparison_config(m), ensure_ascii=False)}"
        )
    if is_ensemble:
        comparison_field += (
            f",\n    ensembleConfig: {json.dumps(_ensemble_config(m), ensure_ascii=False)}"
        )

    tech_entry = f'''  // scaffold-entry:{tid}
  {{
    id: "{tid}",
    mediaType: "{m["media"]}",
    template: "{m["template"]}",
    component: {component_name},
    meta: scaffoldMeta("{tid}")!,
    gpu: {str(gpu).lower()},
    disabled: {str(disabled).lower()},
    adminOnly: {str(admin_only).lower()},
    defaultParameters: {json.dumps(defaults)},
    parameterDefs: {_ts_parameter_defs(params)},
    artifactManifest: {_ts_artifact_manifest(arts)}{comparison_field},
  }},
  // scaffold-entry-end:{tid}
'''

    route_entry = f'''  // scaffold-entry:{tid}
  {tid}: {{ technique: "{tid}", media: "{m["media"]}", title: {json.dumps(title, ensure_ascii=False)} }},
  // scaffold-entry-end:{tid}
'''

    card = m.get("card") or {}
    group_entry = ""
    if card.get("mode") in {"existing", "new"}:
        group_id = card.get("group_id") or f"scaffold-{tid}"
        new_group_ts = ""
        if card.get("mode") == "new":
            new_group_ts = (
                f', newGroup: {{ title: {json.dumps(card.get("title") or title, ensure_ascii=False)}, '
                f'description: {json.dumps(card.get("description") or detail, ensure_ascii=False)} }}'
            )
        flags = ""
        if admin_only:
            flags += ", adminOnly: true"
        if disabled:
            flags += ", disabled: true"
        media_js = m["media"]
        group_entry = f'''  // scaffold-entry:{tid}
  {{ media: "{media_js}", groupId: "{group_id}"{new_group_ts}, entry: {{ kind: "plugin", id: "{tid}"{flags} }} }},
  // scaffold-entry-end:{tid}
'''

    # artifact mappings for unknown keys
    STANDARD_KEYS = {
        "heatmap_path": "heatmap.png",
        "overlay_image_path": "overlay.png",
        "mask_image_path": "mask.png",
        "original_crop_path": "original.png",
        "interactive_html_path": "interactive.html",
        "input_image_path": "input_image.png",
    }
    new_pairs: list[tuple[str, str]] = []
    for a in arts:
        key = a["key"]
        filename = a["filename"]
        if STANDARD_KEYS.get(key) == filename:
            continue
        new_pairs.append((key, filename))

    patch_specs = [
        (paths["meta"], "// --- scaffold:meta:start ---", "// --- scaffold:meta:end ---", meta_entry),
        (
            paths["techniques"],
            "// --- scaffold:techniques:start ---",
            "// --- scaffold:techniques:end ---",
            tech_entry,
        ),
        (
            paths["routes"],
            "// --- scaffold:routes:start ---",
            "// --- scaffold:routes:end ---",
            route_entry,
        ),
    ]
    if group_entry:
        patch_specs.append(
            (
                paths["groups"],
                "// --- scaffold:media-groups:start ---",
                "// --- scaffold:media-groups:end ---",
                group_entry,
            )
        )

    for path, start, end, entry in patch_specs:
        original = path.read_text(encoding="utf-8")
        updated = _upsert_entry_between_markers(original, start, end, tid, entry)
        if updated != original:
            actions.append(f"{'DRY ' if dry_run else 'PATCH'} {path.relative_to(ROOT)}")
            if not dry_run:
                path.write_text(updated, encoding="utf-8")
        else:
            actions.append(f"OK    {path.relative_to(ROOT)} (sem mudança)")

    # Bibliografia / PDF (opcional via bloco ``paper:`` no manifesto)
    paper = m.get("paper")
    if isinstance(paper, dict) and paper:
        paper_ts_entry = f'''  // scaffold-entry:{tid}
  "{tid}",
  // scaffold-entry-end:{tid}
'''
        papers_ts = paths["papers_ts"]
        if papers_ts.is_file():
            original_p = papers_ts.read_text(encoding="utf-8")
            updated_p = _upsert_entry_between_markers(
                original_p,
                "// --- scaffold:papers:start ---",
                "// --- scaffold:papers:end ---",
                tid,
                paper_ts_entry,
            )
            actions.append(f"{'DRY ' if dry_run else 'PATCH'} {papers_ts.relative_to(ROOT)}")
            if not dry_run and updated_p != original_p:
                papers_ts.write_text(updated_p, encoding="utf-8")
        actions.append(
            _upsert_scaffolded_paper_json(paths["papers_json"], tid, paper, dry_run=dry_run)
        )

    # artifact mappings file
    art_path = paths["artifacts"]
    art_text = art_path.read_text(encoding="utf-8")
    # Always ensure list form; merge new_pairs if any
    if new_pairs:
        updated_art = _py_upsert_mapping_list(
            art_text,
            "# --- scaffold:artifact-mappings:start ---",
            "# --- scaffold:artifact-mappings:end ---",
            new_pairs,
        )
        actions.append(f"{'DRY ' if dry_run else 'PATCH'} {art_path.relative_to(ROOT)}")
        if not dry_run:
            art_path.write_text(updated_art, encoding="utf-8")

    return actions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scaffold simple/medium/comparison/ensemble forensic technique"
    )
    parser.add_argument("manifest", nargs="?", help="Caminho do manifesto YAML/JSON")
    parser.add_argument(
        "--example",
        choices=["simple", "medium", "comparison", "ensemble"],
        help="Usar exemplo embutido em scripts/technique/examples/",
    )
    parser.add_argument("--dry-run", action="store_true", help="Só mostra o que seria feito")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Sobrescreve plugin/test/pipeline gerados",
    )
    args = parser.parse_args(argv)

    if args.example:
        manifest_path = EXAMPLES / f"{args.example}.yaml"
    elif args.manifest:
        manifest_path = Path(args.manifest)
    else:
        parser.print_help()
        return 2

    if not manifest_path.is_file():
        print(f"Manifest não encontrado: {manifest_path}", file=sys.stderr)
        return 1

    manifest = _load_manifest(manifest_path)
    actions = apply_scaffold(manifest, dry_run=args.dry_run, force=args.force)
    print(f"Scaffold técnica «{manifest.get('id')}» ({manifest.get('template')})")
    for line in actions:
        print(" ", line)
    if not args.dry_run:
        print(
            "\nPróximo passo: edite "
            f"src/backend/forensics/{manifest['id']}/pipeline.py "
            "(função run)."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
