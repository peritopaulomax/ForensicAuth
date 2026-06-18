"""Extração do pacote XMP bruto e construção de árvore hierárquica/semântica."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from typing import Any

from core.metadata.xmp_property_hints import property_hint

# URIs conhecidos → prefixo legível para agrupamento semântico.
NAMESPACE_LABELS: dict[str, str] = {
    "http://ns.adobe.com/xap/1.0/": "XMP (xap)",
    "http://purl.org/dc/elements/1.1/": "Dublin Core (dc)",
    "http://ns.adobe.com/photoshop/1.0/": "Photoshop",
    "http://ns.adobe.com/tiff/1.0/": "TIFF",
    "http://ns.adobe.com/exif/1.0/": "EXIF (Adobe)",
    "http://ns.adobe.com/camera-raw-settings/1.0/": "Camera Raw",
    "http://ns.adobe.com/xmp/1.0/mm/": "XMP Media Management",
    "http://ns.adobe.com/xap/1.0/mm/": "XMP Media Management (xap)",
    "http://ns.adobe.com/xap/1.0/sType/ResourceRef#": "ResourceRef",
    "http://ns.adobe.com/xap/1.0/sType/Version#": "Version",
    "http://www.aiim.org/pdfa/ns/id/": "PDF/A",
    "http://ns.adobe.com/pdf/1.3/": "PDF (Adobe)",
    "http://ns.adobe.com/crs/": "Camera Raw Settings",
    "http://ns.adobe.com/xap/1.0/sType/ResourceEvent#": "ResourceEvent",
    "adobe:ns:meta/": "Adobe XMP Meta",
}


def _local_name(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _namespace_uri(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag[1 : tag.index("}")]
    return ""


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pretty_xml(xml_text: str) -> str:
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
        ET.indent(root, space="  ")
        return ET.tostring(root, encoding="unicode")
    except ET.ParseError:
        return xml_text


def _exiftool_available() -> bool:
    return shutil.which("exiftool") is not None or shutil.which("exiftool.exe") is not None


def _read_xmp_packet_bytes(path: str) -> bytes | None:
    """Extrai o pacote XMP embutido no arquivo (binário/texto) via ExifTool."""
    if not _exiftool_available():
        return None
    try:
        proc = subprocess.run(
            ["exiftool", "-b", "-XMP", path],
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return proc.stdout


def _sniff_xmp_packet_bytes(data: bytes) -> bytes | None:
    """Fallback: localiza x:xmpmeta / xpacket no binário do arquivo."""
    for pattern in (rb"<x:xmpmeta", rb"<?xpacket"):
        start = data.find(pattern)
        if start < 0:
            continue
        end = data.find(b"<?xpacket end", start)
        if end >= 0:
            end = data.find(b"?>", end)
            if end >= 0:
                return data[start : end + 2]
        end = data.find(b"</x:xmpmeta>", start)
        if end >= 0:
            return data[start : end + len(b"</x:xmpmeta>")]
    return None


RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDF_CONTAINER_TAGS = {"Seq", "Bag", "Alt", "li"}


def _attr_qname(attr_key: str) -> tuple[str, str]:
    if attr_key.startswith("{") and "}" in attr_key:
        uri, local = attr_key[1 : attr_key.index("}")], attr_key.split("}", 1)[1]
        return uri, local
    return "", attr_key


def _is_meta_attribute(attr_key: str) -> bool:
    if attr_key in ("xmlns", "xmlns:rdf"):
        return True
    if attr_key.startswith("xmlns:"):
        return True
    _, local = _attr_qname(attr_key)
    return local in ("about", "ID", "nodeID", "datatype", "parseType", "resource")


def _update_ns_map(elem: ET.Element, ns_map: dict[str, str]) -> dict[str, str]:
    updated = dict(ns_map)
    for key, val in elem.attrib.items():
        if key == "xmlns":
            updated["default"] = val
        elif key.startswith("xmlns:"):
            updated[key.split(":", 1)[1]] = val
    return updated


def _prefix_for_uri(ns_uri: str, ns_map: dict[str, str]) -> str:
    if not ns_uri:
        return ""
    for prefix, uri in ns_map.items():
        if uri == ns_uri and prefix != "default":
            return prefix
    return NAMESPACE_LABELS.get(ns_uri, ns_uri.rstrip("/").split("/")[-1])


def _display_qname(ns_uri: str, local: str, ns_map: dict[str, str]) -> str:
    prefix = _prefix_for_uri(ns_uri, ns_map)
    return f"{prefix}:{local}" if prefix else local


def _build_structural_node(
    elem: ET.Element,
    path: str,
    ns_map: dict[str, str] | None = None,
    *,
    li_index: int | None = None,
) -> dict[str, Any]:
    """Constrói árvore expandindo atributos RDF como nós filhos (não inline)."""
    ns_map = _update_ns_map(elem, ns_map or {})
    ns_uri = _namespace_uri(elem.tag)
    local_name = _local_name(elem.tag)
    display_name = _display_qname(ns_uri, local_name, ns_map)
    if li_index is not None:
        display_name = f"{display_name} [{li_index}]"

    meta_attributes: dict[str, str] = {}
    property_children: list[dict[str, Any]] = []
    attr_idx = 0

    for attr_key, attr_val in elem.attrib.items():
        if _is_meta_attribute(attr_key):
            attr_ns, attr_local = _attr_qname(attr_key)
            label = _display_qname(attr_ns, attr_local, ns_map) if attr_ns else attr_local
            meta_attributes[label] = attr_val
            continue
        attr_ns, attr_local = _attr_qname(attr_key)
        property_children.append(
            {
                "name": attr_local,
                "display_name": _display_qname(attr_ns, attr_local, ns_map),
                "node_type": "property",
                "namespace_uri": attr_ns,
                "namespace_label": NAMESPACE_LABELS.get(attr_ns, attr_ns or "(atributo)"),
                "value": attr_val,
                "hint": property_hint(attr_local),
                "path": f"{path}/@{attr_idx}",
                "children": [],
            }
        )
        attr_idx += 1

    property_children.sort(key=lambda n: n["display_name"].lower())

    element_children: list[dict[str, Any]] = []
    li_counter = 0
    for idx, child in enumerate(elem):
        child_local = _local_name(child.tag)
        li_num = None
        if child_local == "li":
            li_counter += 1
            li_num = li_counter
        element_children.append(
            _build_structural_node(child, f"{path}/{idx}", ns_map, li_index=li_num)
        )

    text = (elem.text or "").strip()
    direct_value = text if text and not element_children and not property_children else None

    node_type = "element"
    if local_name in RDF_CONTAINER_TAGS:
        node_type = "container"

    children = property_children + element_children
    return {
        "name": local_name,
        "display_name": display_name,
        "node_type": node_type,
        "namespace_uri": ns_uri,
        "namespace_label": NAMESPACE_LABELS.get(ns_uri, ns_uri or "default"),
        "meta_attributes": meta_attributes,
        "value": direct_value,
        "hint": property_hint(local_name, element_name=local_name),
        "path": path,
        "children": children,
    }


def _add_semantic_property(
    groups: dict[str, dict[str, Any]],
    ns_uri: str,
    name: str,
    value: str,
    ns_map: dict[str, str],
) -> None:
    if not value:
        return
    group_key = ns_uri or "sem_namespace"
    if group_key not in groups:
        groups[group_key] = {
            "namespace_uri": ns_uri,
            "namespace_label": NAMESPACE_LABELS.get(ns_uri, ns_uri or "(sem namespace)"),
            "properties": [],
        }
    display = _display_qname(ns_uri, name, ns_map)
    groups[group_key]["properties"].append(
        {
            "name": display,
            "value": value,
            "hint": property_hint(name),
        }
    )


def _collect_semantic_groups(root: ET.Element) -> list[dict[str, Any]]:
    """Agrupa propriedades (atributos e elementos folha) por namespace."""
    groups: dict[str, dict[str, Any]] = {}

    def walk(elem: ET.Element, inherited_ns: dict[str, str]) -> None:
        ns_map = _update_ns_map(elem, inherited_ns)

        for attr_key, attr_val in elem.attrib.items():
            if _is_meta_attribute(attr_key):
                continue
            attr_ns, attr_name = _attr_qname(attr_key)
            _add_semantic_property(groups, attr_ns, attr_name, str(attr_val), ns_map)

        for child in elem:
            child_ns_uri = _namespace_uri(child.tag)
            child_name = _local_name(child.tag)
            child_subelements = list(child)

            if not child_subelements:
                child_attrs = {
                    k: v
                    for k, v in child.attrib.items()
                    if not _is_meta_attribute(k)
                }
                if child_attrs:
                    for attr_key, attr_val in child_attrs.items():
                        attr_ns, attr_name = _attr_qname(attr_key)
                        label = f"{_display_qname(child_ns_uri, child_name, ns_map)}.{attr_name}"
                        _add_semantic_property(groups, attr_ns or child_ns_uri, label, str(attr_val), ns_map)
                text = (child.text or "").strip()
                if text:
                    _add_semantic_property(groups, child_ns_uri, child_name, text, ns_map)
            walk(child, ns_map)

    walk(root, {})
    for group in groups.values():
        seen: set[tuple[str, str]] = set()
        deduped = []
        for prop in group["properties"]:
            key = (prop["name"], prop["value"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(prop)
        group["properties"] = sorted(deduped, key=lambda p: p["name"].lower())
    return sorted(groups.values(), key=lambda g: g["namespace_label"])


def _parse_xmp_packet(packet_bytes: bytes) -> dict[str, Any]:
    warnings: list[str] = []
    try:
        text = packet_bytes.decode("utf-8", errors="replace")
    except Exception as exc:
        return {"available": False, "warnings": [f"Falha ao decodificar pacote XMP: {exc}"]}

    # Remove padding do xpacket end se presente no final
    text = re.sub(r"<\?xpacket end=.*?\?>\s*$", "", text, flags=re.DOTALL).strip()

    try:
        root = ET.fromstring(packet_bytes)
    except ET.ParseError as exc:
        # Alguns pacotes incluem xpacket wrapper — tenta extrair xmpmeta interno
        match = re.search(r"<x:xmpmeta[\s\S]*?</x:xmpmeta>", text)
        if not match:
            return {"available": False, "warnings": [f"XML XMP inválido: {exc}"]}
        try:
            root = ET.fromstring(match.group(0).encode("utf-8"))
        except ET.ParseError as exc2:
            return {"available": False, "warnings": [f"XML XMP inválido: {exc2}"]}

    structural_tree = _build_structural_node(root, "0")
    semantic_groups = _collect_semantic_groups(root)
    pretty = _pretty_xml(ET.tostring(root, encoding="unicode"))

    return {
        "available": True,
        "packet_xml": pretty,
        "packet_sha256": _sha256_text(pretty),
        "structural_tree": structural_tree,
        "semantic_groups": semantic_groups,
        "property_count": sum(len(g["properties"]) for g in semantic_groups),
        "warnings": warnings,
    }


def extract_xmp_packet(path: str) -> dict[str, Any]:
    """
    Extrai pacote XMP embutido e produz vistas estrutural + semântica.

    Retorna dict com packet_xml, packet_sha256, structural_tree, semantic_groups.
    """
    packet_bytes = _read_xmp_packet_bytes(path)
    source = "exiftool"

    if not packet_bytes:
        try:
            raw = open(path, "rb").read()
            packet_bytes = _sniff_xmp_packet_bytes(raw)
            source = "xmp_sniff"
        except OSError:
            packet_bytes = None

    if not packet_bytes:
        return {
            "available": False,
            "source": None,
            "packet_xml": None,
            "packet_sha256": None,
            "structural_tree": None,
            "semantic_groups": [],
            "property_count": 0,
            "warnings": ["Nenhum pacote XMP encontrado neste arquivo."],
        }

    parsed = _parse_xmp_packet(packet_bytes)
    parsed["source"] = source
    if not _exiftool_available() and source == "xmp_sniff":
        parsed.setdefault("warnings", []).append(
            "Pacote XMP obtido por varredura binária (ExifTool ausente no PATH)."
        )
    return parsed
