"""Extração e validação de manifests C2PA (Content Credentials)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_C2PA_FAMILY_PREFIXES = frozenset({"JUMBF", "C2PA"})


def c2pa_runtime_status() -> tuple[bool, str]:
    """Disponibilidade da biblioteca c2pa-python."""
    try:
        import c2pa  # noqa: F401
    except ImportError:
        return False, "Pacote c2pa-python nao instalado"
    return True, ""


def _safe_str(value: Any, max_len: int = 2048) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = str(value)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _claim_generator_label(manifest: dict[str, Any]) -> str:
    gen = manifest.get("claim_generator")
    if isinstance(gen, str) and gen.strip():
        return gen.strip()
    info = manifest.get("claim_generator_info")
    if isinstance(info, list) and info:
        first = info[0] if isinstance(info[0], dict) else {}
        name = first.get("name") or first.get("product") or ""
        version = first.get("version") or ""
        label = f"{name} {version}".strip()
        if label:
            return label
    if isinstance(info, dict):
        return _safe_str(info.get("name") or info)
    return ""


def _extract_actions(manifest: dict[str, Any]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for assertion in manifest.get("assertions") or []:
        if not isinstance(assertion, dict):
            continue
        label = str(assertion.get("label") or "")
        if "c2pa.actions" not in label:
            continue
        data = assertion.get("data") or {}
        raw_actions = data.get("actions") if isinstance(data, dict) else None
        if not isinstance(raw_actions, list):
            continue
        for item in raw_actions:
            if not isinstance(item, dict):
                continue
            actions.append(
                {
                    "action": _safe_str(item.get("action")),
                    "software_agent": _safe_str(
                        item.get("softwareAgent") or item.get("software_agent")
                    ),
                    "digital_source_type": _safe_str(
                        item.get("digitalSourceType") or item.get("digital_source_type")
                    ),
                    "when": _safe_str(item.get("when")),
                }
            )
    return actions


def _validation_issue_codes(store: dict[str, Any], results: Any) -> list[str]:
    codes: list[str] = []
    status = store.get("validation_status")
    if isinstance(status, list):
        for item in status:
            if isinstance(item, dict) and item.get("code"):
                codes.append(str(item["code"]))
    if isinstance(results, dict):
        active = results.get("activeManifest") or results.get("active_manifest") or {}
        if isinstance(active, dict):
            for bucket in ("failure", "failures", "informational", "warning", "warnings"):
                for item in active.get(bucket) or []:
                    if isinstance(item, dict) and item.get("code"):
                        codes.append(str(item["code"]))
    seen: set[str] = set()
    out: list[str] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def _tag_entries_from_structured(structured: dict[str, Any]) -> list[dict[str, str]]:
    """Campos resumidos para a família UI `c2pa`."""
    entries: list[dict[str, str]] = []

    def add(tag: str, value: Any) -> None:
        text = _safe_str(value)
        if not text:
            return
        entries.append(
            {
                "tag": tag,
                "value": text,
                "group": "c2pa",
                "source": "c2pa-python",
            }
        )

    add("C2PA:Present", "true" if structured.get("present") else "false")
    add("C2PA:ValidationState", structured.get("validation_state"))
    if structured.get("is_valid") is not None:
        add("C2PA:Valid", structured.get("is_valid"))
    add("C2PA:ClaimGenerator", structured.get("claim_generator"))
    add("C2PA:Title", structured.get("title"))
    add("C2PA:Format", structured.get("format"))
    add("C2PA:ActiveManifest", structured.get("active_manifest"))
    if structured.get("manifest_count") is not None:
        add("C2PA:ManifestCount", structured.get("manifest_count"))
    if structured.get("ingredient_count") is not None:
        add("C2PA:IngredientCount", structured.get("ingredient_count"))
    sig = structured.get("signature_info") or {}
    if isinstance(sig, dict):
        add("C2PA:SignatureIssuer", sig.get("issuer"))
        add("C2PA:SignatureAlg", sig.get("alg"))
        add("C2PA:SignatureTime", sig.get("time"))
    for idx, action in enumerate(structured.get("actions") or [], start=1):
        if not isinstance(action, dict):
            continue
        add(f"C2PA:Action[{idx}]", action.get("action"))
        add(f"C2PA:Action[{idx}].SoftwareAgent", action.get("software_agent"))
        add(f"C2PA:Action[{idx}].DigitalSourceType", action.get("digital_source_type"))
    for code in structured.get("validation_codes") or []:
        add("C2PA:ValidationCode", code)
    if structured.get("error"):
        add("C2PA:Error", structured.get("error"))
    if structured.get("reason"):
        add("C2PA:Reason", structured.get("reason"))
    return entries


def is_c2pa_exiftool_tag(tag: str) -> bool:
    """Classifica tags ExifTool relacionadas a JUMBF/C2PA."""
    if ":" in tag:
        prefix, local = tag.split(":", 1)
        if prefix in _C2PA_FAMILY_PREFIXES:
            return True
        if prefix == "Jpeg2000" and "c2pa" in local.lower():
            return True
        if "c2pa" in local.lower() or local.upper().startswith("JUMD"):
            return True
    tag_l = tag.lower()
    return "c2pa" in tag_l or tag_l.startswith("jumd")


def _build_settings_from_anchors(anchors_pem: str):
    from c2pa import Settings

    return Settings.from_dict(
        {
            "verify": {"verify_cert_anchors": True},
            "trust": {"trust_anchors": anchors_pem},
        }
    )


def _read_with_reader(path: str, context=None) -> dict[str, Any]:
    from c2pa import C2paError, Reader

    try:
        reader_kwargs = {"context": context} if context is not None else {}
        with Reader(path, **reader_kwargs) as reader:
            raw_json = reader.json() or "{}"
            try:
                store = json.loads(raw_json)
            except json.JSONDecodeError:
                store = {}

            is_valid = bool(getattr(reader, "is_valid", False))
            validation_state = reader.get_validation_state()
            validation_results = reader.get_validation_results()
            active = reader.get_active_manifest()
            if not isinstance(active, dict):
                active = {}

            active_label = store.get("active_manifest")
            manifests = store.get("manifests") if isinstance(store.get("manifests"), dict) else {}
            ingredients = active.get("ingredients") if isinstance(active.get("ingredients"), list) else []
            actions = _extract_actions(active)
            signature_info = (
                active.get("signature_info") if isinstance(active.get("signature_info"), dict) else {}
            )
            codes = _validation_issue_codes(store, validation_results)

            structured: dict[str, Any] = {
                "available": True,
                "present": True,
                "engine": "c2pa-python",
                "sdk_version": None,
                "is_valid": is_valid,
                "validation_state": validation_state,
                "validation_codes": codes,
                "active_manifest": active_label,
                "manifest_count": len(manifests),
                "claim_generator": _claim_generator_label(active),
                "title": active.get("title"),
                "format": active.get("format"),
                "instance_id": active.get("instance_id"),
                "ingredient_count": len(ingredients),
                "actions": actions,
                "signature_info": {
                    "alg": signature_info.get("alg"),
                    "issuer": signature_info.get("issuer"),
                    "common_name": signature_info.get("common_name"),
                    "time": signature_info.get("time"),
                },
                "store": store,
                "trust_anchors_configured": context is not None,
            }
            try:
                from c2pa import sdk_version

                structured["sdk_version"] = str(sdk_version())
            except Exception:
                pass

            structured["families"] = {"c2pa": _tag_entries_from_structured(structured)}
            return structured
    except Exception as exc:
        name = type(exc).__name__
        message = str(exc)
        missing = (
            "ManifestNotFound" in name
            or "ManifestNotFound" in message
            or "no JUMBF" in message
            or (isinstance(exc, C2paError) and "JUMBF" in message)
        )
        if missing:
            structured = {
                "available": True,
                "present": False,
                "engine": "c2pa-python",
                "is_valid": None,
                "validation_state": None,
                "validation_codes": [],
                "actions": [],
                "claim_generator": None,
                "title": None,
                "format": None,
                "manifest_count": 0,
                "ingredient_count": 0,
                "signature_info": {},
                "store": None,
                "trust_anchors_configured": context is not None,
            }
            structured["families"] = {"c2pa": _tag_entries_from_structured(structured)}
            return structured

        return {
            "available": False,
            "present": False,
            "engine": "c2pa-python",
            "error": f"{name}: {message}",
            "is_valid": None,
            "validation_state": None,
            "validation_codes": [],
            "actions": [],
            "families": {"c2pa": []},
            "trust_anchors_configured": context is not None,
        }


def extract_c2pa_manifest(path: str) -> dict[str, Any]:
    """Lê e valida manifesto C2PA embutido; nunca levanta exceção ao chamador.

    Campos principais:
    - available: motor c2pa-python utilizável
    - present: manifesto JUMBF encontrado
    - is_valid / validation_state: resultado criptográfico do SDK
    - actions / claim_generator / signature_info: resumo forense
    - store: manifesto completo (para artefato JSON)

    Trust anchors opcionais via env ``C2PA_TRUST_ANCHORS_PATH`` (PEM).
    """
    ok, reason = c2pa_runtime_status()
    if not ok:
        return {
            "available": False,
            "present": False,
            "engine": None,
            "reason": reason,
            "is_valid": None,
            "validation_state": None,
            "actions": [],
            "validation_codes": [],
            "families": {"c2pa": []},
        }

    anchors_path = os.environ.get("C2PA_TRUST_ANCHORS_PATH", "").strip()
    if anchors_path and Path(anchors_path).is_file():
        try:
            from c2pa import Context

            anchors = Path(anchors_path).read_text(encoding="utf-8")
            settings = _build_settings_from_anchors(anchors)
            with Context(settings) as ctx:
                return _read_with_reader(path, context=ctx)
        except Exception:
            # Fail-open: valida sem anchors se o Context falhar.
            pass

    return _read_with_reader(path, context=None)
