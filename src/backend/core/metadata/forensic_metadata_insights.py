"""Alertas forenses automáticos a partir de metadados extraídos."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

_EDIT_SOFTWARE_KEYWORDS = (
    "photoshop",
    "lightroom",
    "gimp",
    "affinity",
    "capture one",
    "paint.net",
    "paint shop",
    "pixelmator",
    "acorn",
    "snapseed",
    "canva",
    "fotor",
    "photoscape",
)

_CAPTURE_TAG_HINTS = (
    "datetimeoriginal",
    "createdate",
    "created",
    "datacriacao",
)
_CAPTURE_TAG_EXCLUDE = ("modify", "metadata", "digitized")

_MODIFY_TAG_HINTS = (
    "modifydate",
    "metadatadate",
)

# Famílias com datas embutidas no arquivo (não sistema de arquivos).
_EMBEDDED_DATE_FAMILIES = frozenset({"exif", "xmp", "adobe", "iptc", "makernotes"})

# Prefixos ExifTool de metadados de volume/sistema — não usar em alertas de edição.
_FILESYSTEM_TAG_PREFIXES = ("File:", "System:", "Composite:", "QuickTime:")

_FILESYSTEM_DATE_TAG_KEYS = frozenset({
    "filemodifydate",
    "fileaccessdate",
    "filecreatedate",
    "fileinodechangedate",
    "filechangetime",
    "filemodificationdatetime",
    "filecreationdatetime",
})

_SOFTWARE_TAG_HINTS = (
    "software",
    "creatortool",
    "readername",
    "writername",
    "softwareagent",
    "producer",
)


def _normalize_tag_key(tag: str) -> str:
    local = tag.split(":", 1)[-1].lower()
    return re.sub(r"[^a-z0-9]", "", local)


def _parse_metadata_datetime(value: str) -> datetime | None:
    if not value or value.startswith("(Binary"):
        return None
    text = re.sub(r"\.\d+", "", value.strip())
    if not text:
        return None
    text = re.sub(r"[+-]\d{2}:?\d{2}$", "", text).replace("Z", "").strip()
    text = text.replace("T", " ")
    if re.match(r"^\d{4}:\d{2}:\d{2}", text):
        text = text.replace(":", "-", 2)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def _is_embedded_metadata_tag(tag: str, family: str) -> bool:
    """Ignora datas de sistema de arquivos (upload, cópia, inode, etc.)."""
    if family not in _EMBEDDED_DATE_FAMILIES:
        return False
    if any(tag.startswith(prefix) for prefix in _FILESYSTEM_TAG_PREFIXES):
        return False
    norm = _normalize_tag_key(tag)
    if norm in _FILESYSTEM_DATE_TAG_KEYS:
        return False
    return True


def _is_capture_date_tag(norm: str) -> bool:
    if any(ex in norm for ex in _CAPTURE_TAG_EXCLUDE):
        return False
    return any(h in norm for h in _CAPTURE_TAG_HINTS)


def _is_modify_date_tag(norm: str) -> bool:
    if any(h in norm for h in _MODIFY_TAG_HINTS):
        return True
    # TIFF tag 306 — DateTime (última modificação embutida no EXIF)
    return norm == "datetime"


def _collect_embedded_date_entries(
    families: dict[str, list[dict[str, str]]],
    *,
    kind: str,
) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    for group, entries in families.items():
        for entry in entries:
            tag = entry.get("tag", "")
            if not _is_embedded_metadata_tag(tag, group):
                continue
            norm = _normalize_tag_key(tag)
            if kind == "capture" and _is_capture_date_tag(norm):
                found.append({**entry, "family": group})
            elif kind == "modify" and _is_modify_date_tag(norm):
                found.append({**entry, "family": group})
    return found


def _collect_xmp_embedded_dates(xmp_structured: dict[str, Any]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Datas do pacote XMP estruturado (namespace xap / EXIF espelhado no XMP)."""
    capture: list[dict[str, str]] = []
    modify: list[dict[str, str]] = []
    for group in xmp_structured.get("semantic_groups") or []:
        for prop in group.get("properties", []):
            name = prop.get("name", "")
            value = (prop.get("value") or "").strip()
            if not value:
                continue
            norm = _normalize_tag_key(name.split(":")[-1])
            entry = {"tag": name, "value": value, "family": "xmp"}
            if _is_capture_date_tag(norm):
                capture.append(entry)
            elif _is_modify_date_tag(norm):
                modify.append(entry)
    return capture, modify


def _find_software_entries(families: dict[str, list[dict[str, str]]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for group, entries in families.items():
        for entry in entries:
            norm = _normalize_tag_key(entry.get("tag", ""))
            if not any(h in norm for h in _SOFTWARE_TAG_HINTS):
                continue
            val = (entry.get("value") or "").strip()
            if not val:
                continue
            key = (entry.get("tag", ""), val)
            if key in seen:
                continue
            seen.add(key)
            out.append({**entry, "family": group})
    return out


def _xmp_history_events(xmp_structured: dict[str, Any]) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for group in xmp_structured.get("semantic_groups") or []:
        props = {p["name"].split(":")[-1].split(".")[-1]: p["value"] for p in group.get("properties", [])}
        if "action" in props or "softwareAgent" in props:
            events.append(
                {
                    "action": props.get("action", ""),
                    "softwareAgent": props.get("softwareAgent", ""),
                    "when": props.get("when", ""),
                    "instanceID": props.get("instanceID", ""),
                }
            )
    # também varre árvore estrutural por History
    tree = xmp_structured.get("structural_tree")
    if tree:
        _walk_history_tree(tree, events)
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for ev in events:
        key = (ev.get("action", ""), ev.get("when", ""), ev.get("softwareAgent", ""))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ev)
    return deduped


def _walk_history_tree(node: dict[str, Any], events: list[dict[str, str]]) -> None:
    name = (node.get("name") or "").lower()
    children = node.get("children") or []
    if name == "history" or "resourceevent" in (node.get("namespace_label") or "").lower():
        props: dict[str, str] = {}
        for child in children:
            cname = child.get("name") or ""
            if child.get("value"):
                props[cname] = str(child["value"])
            _walk_history_tree(child, events)
        if props.get("action") or props.get("softwareAgent"):
            events.append(
                {
                    "action": props.get("action", ""),
                    "softwareAgent": props.get("softwareAgent", ""),
                    "when": props.get("when", ""),
                    "instanceID": props.get("instanceID", ""),
                }
            )
        return
    for child in children:
        _walk_history_tree(child, events)


def _alert(
    severity: str,
    title: str,
    detail: str,
    *,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "title": title,
        "detail": detail,
        "tags": tags or [],
    }


def build_forensic_insights(
    families: dict[str, list[dict[str, str]]],
    xmp_structured: dict[str, Any] | None,
    summary: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Gera alertas forenses ordenados por severidade (high → medium → info)."""
    alerts: list[dict[str, Any]] = []
    xmp_structured = xmp_structured or {}
    summary = summary or {}

    capture_entries = _collect_embedded_date_entries(families, kind="capture")
    modify_entries = _collect_embedded_date_entries(families, kind="modify")
    if xmp_structured.get("available"):
        xmp_capture, xmp_modify = _collect_xmp_embedded_dates(xmp_structured)
        capture_entries.extend(xmp_capture)
        modify_entries.extend(xmp_modify)

    capture_dates = [
        (e["tag"], e["value"], _parse_metadata_datetime(e["value"]))
        for e in capture_entries
    ]
    modify_dates = [
        (e["tag"], e["value"], _parse_metadata_datetime(e["value"]))
        for e in modify_entries
    ]
    capture_parsed = [d for _, _, d in capture_dates if d]
    modify_parsed = [d for _, _, d in modify_dates if d]

    if capture_parsed and modify_parsed:
        earliest_capture = min(capture_parsed)
        latest_modify = max(modify_parsed)
        if latest_modify > earliest_capture:
            delta = latest_modify - earliest_capture
            mins = int(delta.total_seconds() // 60)
            cap_tags = [t for t, v, d in capture_dates if d == earliest_capture]
            mod_tags = [t for t, v, d in modify_dates if d == latest_modify]
            alerts.append(
                _alert(
                    "high",
                    "Arquivo modificado após a captura",
                    f"Captura mais antiga: {earliest_capture.strftime('%Y-%m-%d %H:%M:%S')}. "
                    f"Última modificação: {latest_modify.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"({mins} min depois, se mesmo fuso).",
                    tags=cap_tags + mod_tags,
                )
            )

    software_entries = _find_software_entries(families)
    edit_software = [
        e for e in software_entries
        if any(kw in (e.get("value") or "").lower() for kw in _EDIT_SOFTWARE_KEYWORDS)
    ]
    if edit_software:
        names = ", ".join(f"{e['tag']}={e['value']}" for e in edit_software[:4])
        alerts.append(
            _alert(
                "high",
                "Software de edição detectado",
                f"Indício de pós-processamento em aplicativo gráfico: {names}.",
                tags=[e["tag"] for e in edit_software],
            )
        )

    history = _xmp_history_events(xmp_structured)
    if history:
        lines = []
        for ev in history[:5]:
            parts = [p for p in (ev.get("action"), ev.get("softwareAgent"), ev.get("when")) if p]
            if parts:
                lines.append(" · ".join(parts))
        alerts.append(
            _alert(
                "high",
                "Histórico de edição XMP (Photoshop/Camera Raw)",
                "Eventos registrados: " + ("; ".join(lines) if lines else "ação de edição presente."),
                tags=["XMP:History", "stEvt:action", "stEvt:softwareAgent"],
            )
        )

    if summary.get("has_gps"):
        gps_entries = [
            e for fam in families.values() for e in fam if "gps" in e.get("tag", "").lower()
        ]
        coords = [
            e for e in gps_entries
            if "latitude" in e["tag"].lower() or "longitude" in e["tag"].lower()
        ]
        detail = "Coordenadas presentes nos metadados."
        if coords:
            detail = "; ".join(f"{e['tag']}={e['value']}" for e in coords[:4])
        alerts.append(
            _alert("medium", "Dados GPS presentes", detail, tags=[e["tag"] for e in gps_entries[:6]])
        )

    shutter_entries = [
        e for fam in families.values() for e in fam if "shuttercount" in _normalize_tag_key(e.get("tag", ""))
    ]
    if shutter_entries:
        e = shutter_entries[0]
        alerts.append(
            _alert(
                "info",
                "Contagem de obturador disponível",
                f"{e['tag']} = {e['value']} (útil para estimar uso da câmera).",
                tags=[e["tag"]],
            )
        )

    if xmp_structured.get("available") and xmp_structured.get("packet_sha256"):
        alerts.append(
            _alert(
                "info",
                "Pacote XMP íntegro e identificável",
                f"SHA-256 do pacote: {xmp_structured['packet_sha256'][:16]}… "
                f"({xmp_structured.get('property_count', 0)} propriedades).",
                tags=["XMP:Packet"],
            )
        )

    if summary.get("has_makernotes"):
        count = summary.get("tag_counts", {}).get("makernotes", 0)
        alerts.append(
            _alert(
                "info",
                "MakerNotes decodificados",
                f"{count} campo(s) proprietário(s) do fabricante — ver aba MakerNotes.",
                tags=["MakerNotes"],
            )
        )

    if not alerts:
        alerts.append(
            _alert(
                "info",
                "Nenhum alerta automático",
                "Não foram encontrados alertas padronizados nas abas EXIF, XMP e Adobe. Verifique mais profundamente os metadados.",
            )
        )

    order = {"high": 0, "medium": 1, "info": 2}
    alerts.sort(key=lambda a: order.get(a["severity"], 9))
    return alerts
