"""Extracao forense de PDF: imagens, metadados e versoes incrementais (%%EOF)."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import fitz
from pypdf import PdfReader

ProgressFn = Optional[Callable[[int, str], None]]

EOF_MARKER = b"%%EOF"
JPEG2000_EXTS = frozenset({"jpx", "jp2", "jpx2"})
JPEG2000_FILTER = "JPXDecode"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def is_linearized(pdf_bytes: bytes) -> bool:
    """Heuristica: dicionario /Linearized nos primeiros 64 KiB."""
    head = pdf_bytes[:65536]
    return b"/Linearized" in head and re.search(rb"/Linearized\s+\d", head) is not None


def find_eof_end_positions(pdf_bytes: bytes) -> List[int]:
    """Indices do fim de cada marcador %%EOF (posicao apos o marcador)."""
    ends: List[int] = []
    start = 0
    while True:
        idx = pdf_bytes.find(EOF_MARKER, start)
        if idx < 0:
            break
        ends.append(idx + len(EOF_MARKER))
        start = idx + len(EOF_MARKER)
    return ends


def analyze_incremental_versions(pdf_path: str) -> Dict[str, Any]:
    """
    Detecta versoes cumulativas por marcadores %%EOF.
    Retorna status, mensagem e lista de fatias (bytes) para salvar como PDF.
    """
    data = Path(pdf_path).read_bytes()
    linearized = is_linearized(data)
    eof_ends = find_eof_end_positions(data)

    def trailing_after(pos: int) -> bytes:
        return data[pos:].strip(b"\x00\r\n\t ")

    result: Dict[str, Any] = {
        "linearized": linearized,
        "eof_count": len(eof_ends),
        "version_count": 0,
        "versions": [],
        "message": "",
        "status": "ok",
    }

    if not eof_ends:
        result["status"] = "no_eof"
        result["message"] = "Nenhum marcador %%EOF encontrado no arquivo."
        return result

    if linearized:
        if len(eof_ends) < 2:
            after_first = trailing_after(eof_ends[0])
            if not after_first:
                result["status"] = "no_updates"
                result["message"] = (
                    "PDF linearizado: nao foram encontradas outras versoes apos o primeiro %%EOF."
                )
            else:
                result["status"] = "orphan_data"
                result["message"] = (
                    "PDF linearizado: dados encontrados apos o primeiro %%EOF, "
                    "mas sem estrutura de atualizacao incremental (sem segundo %%EOF)."
                )
            return result

        version_eof_indices = eof_ends[1:]
        labels_start = 1
    else:
        if len(eof_ends) == 1:
            after_first = trailing_after(eof_ends[0])
            if not after_first:
                result["status"] = "no_updates"
                result["message"] = "Nao foram encontradas outras versoes (nada apos o primeiro %%EOF)."
            else:
                result["status"] = "orphan_data"
                result["message"] = (
                    "Dados encontrados apos o primeiro %%EOF, "
                    "mas sem estrutura de atualizacao incremental (sem segundo %%EOF)."
                )
            return result

        version_eof_indices = eof_ends
        labels_start = 1

    for i, end_pos in enumerate(version_eof_indices, start=labels_start):
        slice_bytes = data[0:end_pos]
        result["versions"].append(
            {
                "version_index": i,
                "end_eof_index": i if not linearized else i + 1,
                "byte_length": len(slice_bytes),
                "sha256": _sha256_bytes(slice_bytes),
            }
        )

    result["version_count"] = len(result["versions"])
    result["message"] = (
        f"{result['version_count']} versao(oes) cumulativa(s) identificada(s)"
        f"{' (PDF linearizado; primeiro %%EOF ignorado)' if linearized else ''}."
    )
    return result


def save_incremental_version_files(
    pdf_path: str, out_dir: Path, analysis: Dict[str, Any]
) -> List[Dict[str, str]]:
    """Grava version_NNN.pdf para cada fatia cumulativa."""
    if not analysis.get("versions"):
        return []

    data = Path(pdf_path).read_bytes()
    eof_ends = find_eof_end_positions(data)
    linearized = analysis.get("linearized", False)
    version_eof_indices = eof_ends[1:] if linearized else eof_ends

    saved: List[Dict[str, str]] = []
    versions_dir = out_dir / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    for i, end_pos in enumerate(version_eof_indices, start=1):
        fname = f"version_{i:03d}.pdf"
        fpath = versions_dir / fname
        fpath.write_bytes(data[0:end_pos])
        saved.append(
            {
                "filename": f"versions/{fname}",
                "version_index": str(i),
                "sha256": _sha256_file(fpath),
                "byte_length": str(fpath.stat().st_size),
            }
        )
    return saved


def _normalize_filter_name(filters: Any) -> List[str]:
    if filters is None:
        return []
    if isinstance(filters, list):
        return [str(f).strip("/") for f in filters]
    return [str(filters).strip("/")]


def _is_valid_jpeg2000_stream(raw: bytes) -> bool:
    """True when raw bytes look like encapsulated JP2/JPX codestream or file format."""
    if len(raw) < 4:
        return False
    if len(raw) >= 8 and raw[4:8] in (b"jP  ", b"jPX "):
        return True
    return raw[:2] == b"\xff\x4f"


def _save_rendered_png(doc: fitz.Document, xref: int, out_path: Path) -> None:
    pix = fitz.Pixmap(doc, xref)
    if pix.n - pix.alpha > 3:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    pix.save(str(out_path))


def _collect_image_xrefs(doc: fitz.Document) -> List[int]:
    xrefs: List[int] = []
    seen: set[int] = set()
    for page in doc:
        for item in page.get_images(full=True):
            xref = int(item[0])
            if xref not in seen:
                seen.add(xref)
                xrefs.append(xref)
    return sorted(xrefs)


def extract_images(
    pdf_path: str, out_dir: Path, reporter: ProgressFn = None
) -> List[Dict[str, Any]]:
    """Extrai imagens: JPEG/JPX stream bruto via extract_image; demais como PNG."""
    images_dir = out_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    manifest: List[Dict[str, Any]] = []

    doc = fitz.open(pdf_path)
    try:
        xrefs = _collect_image_xrefs(doc)
        total = len(xrefs)
        for idx, xref in enumerate(xrefs):
            if reporter:
                pct = 10 + int(35 * idx / max(total, 1))
                reporter(pct, f"Imagem {idx + 1}/{total} (xref {xref})")

            out_path: Optional[Path] = None
            entry: Dict[str, Any] = {
                "xref": xref,
                "extraction": "unknown",
                "filter": None,
                "width": None,
                "height": None,
            }

            try:
                img_info = doc.extract_image(xref)
            except Exception as exc:
                entry["error"] = str(exc)
                manifest.append(entry)
                continue

            ext = (img_info.get("ext") or "png").lower()
            raw = img_info.get("image") or b""
            entry["width"] = img_info.get("width")
            entry["height"] = img_info.get("height")
            entry["colorspace"] = img_info.get("colorspace")
            entry["bpc"] = img_info.get("bpc")

            try:
                obj = doc.xref_object(xref)
                if "/Filter" in obj:
                    m = re.search(r"/Filter\s*/([^\s\]]+)", obj)
                    if m:
                        entry["filter"] = m.group(1)
            except Exception:
                pass

            if ext in ("jpeg", "jpg") or raw[:2] == b"\xff\xd8":
                fname = f"image_{xref:05d}.jpg"
                out_path = images_dir / fname
                out_path.write_bytes(raw)
                entry["extraction"] = "jpeg_raw_stream"
                entry["filename"] = f"images/{fname}"
                entry["mime"] = "image/jpeg"
            elif ext in JPEG2000_EXTS or entry.get("filter") == JPEG2000_FILTER:
                j2k_ext = ext if ext in JPEG2000_EXTS else "jp2"
                if _is_valid_jpeg2000_stream(raw):
                    fname = f"image_{xref:05d}.{j2k_ext}"
                    out_path = images_dir / fname
                    out_path.write_bytes(raw)
                    entry["extraction"] = "jpeg2000_raw_stream"
                    entry["filename"] = f"images/{fname}"
                    entry["mime"] = "image/jpx" if j2k_ext == "jpx" else f"image/{j2k_ext}"
                else:
                    fname = f"image_{xref:05d}.png"
                    out_path = images_dir / fname
                    try:
                        _save_rendered_png(doc, xref, out_path)
                        entry["extraction"] = "jpeg2000_rendered_png"
                        entry["filename"] = f"images/{fname}"
                        entry["mime"] = "image/png"
                    except Exception as exc:
                        entry["error"] = str(exc)
            elif ext == "png" and raw[:8] == b"\x89PNG\r\n\x1a\n":
                fname = f"image_{xref:05d}.png"
                out_path = images_dir / fname
                out_path.write_bytes(raw)
                entry["extraction"] = "png_native"
                entry["filename"] = f"images/{fname}"
                entry["mime"] = "image/png"
            else:
                fname = f"image_{xref:05d}.png"
                out_path = images_dir / fname
                try:
                    _save_rendered_png(doc, xref, out_path)
                    entry["extraction"] = "rendered_png"
                    entry["filename"] = f"images/{fname}"
                    entry["mime"] = "image/png"
                except Exception as exc:
                    if raw:
                        fname = f"image_{xref:05d}.{ext or 'bin'}"
                        out_path = images_dir / fname
                        out_path.write_bytes(raw)
                        entry["extraction"] = "raw_fallback"
                        entry["filename"] = f"images/{fname}"
                        entry["error_render"] = str(exc)
                    else:
                        entry["error"] = str(exc)

            if entry.get("filename") and out_path.exists():
                entry["sha256"] = _sha256_file(out_path)
                entry["size_bytes"] = out_path.stat().st_size
            manifest.append(entry)
    finally:
        doc.close()

    return manifest


def collect_metadata_text(pdf_path: str) -> Tuple[str, Dict[str, Any]]:
    """Coleta /Info, XMP, trailer e propriedades em texto + dict."""
    lines: List[str] = []
    structured: Dict[str, Any] = {"sources": []}
    lines.append("=" * 72)
    lines.append("RELATORIO DE METADADOS PDF")
    lines.append(f"Arquivo: {Path(pdf_path).name}")
    lines.append(f"Gerado em: {datetime.now(timezone.utc).isoformat()}")
    lines.append("=" * 72)

    doc = fitz.open(pdf_path)
    try:
        lines.append("\n--- Documento (PyMuPDF /Info) ---\n")
        meta = doc.metadata or {}
        structured["fitz_metadata"] = dict(meta)
        for k, v in sorted(meta.items()):
            lines.append(f"{k}: {v}")

        lines.append("\n--- Contagem ---\n")
        lines.append(f"Paginas: {doc.page_count}")
        lines.append(f"Criptografado: {doc.is_encrypted}")
        lines.append(f"Requer senha: {doc.needs_pass}")
        structured["page_count"] = doc.page_count
        structured["is_encrypted"] = doc.is_encrypted

        xmp = doc.get_xml_metadata() or ""
        structured["has_xmp"] = bool(xmp.strip())
        lines.append("\n--- XMP (XML) ---\n")
        lines.append(xmp if xmp else "(vazio)")

        lines.append("\n--- Catalogo / trailer (pypdf) ---\n")
        try:
            reader = PdfReader(pdf_path)
            structured["pypdf_is_encrypted"] = reader.is_encrypted
            if reader.metadata:
                structured["pypdf_metadata"] = {
                    k: str(v) for k, v in reader.metadata.items() if v
                }
                for k, v in reader.metadata.items():
                    if v:
                        lines.append(f"{k}: {v}")
            if reader.trailer:
                for key in ("/Root", "/Info", "/ID", "/Size", "/Prev", "/Encrypt"):
                    if key in reader.trailer:
                        lines.append(f"Trailer {key}: {reader.trailer[key]}")
                structured["trailer_keys"] = list(reader.trailer.keys())
            if reader.xmp_metadata:
                lines.append("\n--- XMP (pypdf) ---\n")
                try:
                    xmp_pypdf = reader.xmp_metadata
                    structured["pypdf_xmp"] = str(xmp_pypdf)
                    lines.append(str(xmp_pypdf))
                except Exception as exc:
                    lines.append(f"(erro ao ler XMP pypdf: {exc})")
        except Exception as exc:
            lines.append(f"Erro pypdf: {exc}")

        lines.append("\n--- Objetos embutidos (nomes) ---\n")
        try:
            names = doc.pdf_catalog()
            lines.append(str(names)[:8000])
        except Exception:
            lines.append("(nao disponivel)")
    finally:
        doc.close()

    text = "\n".join(lines)
    return text, structured


def run_pdf_forensic_extract(
    pdf_path: str,
    out_dir: Path,
    reporter: ProgressFn = None,
) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    if reporter:
        reporter(5, "Extraindo imagens")

    images = extract_images(pdf_path, out_dir, reporter=reporter)

    if reporter:
        reporter(50, "Coletando metadados")

    meta_text, meta_struct = collect_metadata_text(pdf_path)
    meta_txt_path = out_dir / "metadata_report.txt"
    meta_txt_path.write_text(meta_text, encoding="utf-8")
    meta_json_path = out_dir / "metadata.json"
    meta_json_path.write_text(
        json.dumps(meta_struct, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if reporter:
        reporter(65, "Analisando versoes incrementais")

    inc_analysis = analyze_incremental_versions(pdf_path)
    inc_report_path = out_dir / "incremental_report.txt"
    inc_lines = [
        "RELATORIO — VERSOES INCREMENTAIS (%%EOF)",
        f"Linearizado: {inc_analysis.get('linearized')}",
        f"Marcadores %%EOF: {inc_analysis.get('eof_count')}",
        f"Status: {inc_analysis.get('status')}",
        f"Mensagem: {inc_analysis.get('message')}",
        "",
    ]
    for v in inc_analysis.get("versions") or []:
        inc_lines.append(
            f"Versao {v.get('version_index')}: {v.get('byte_length')} bytes, "
            f"SHA-256 {v.get('sha256', '')[:16]}…"
        )
    inc_report_path.write_text("\n".join(inc_lines), encoding="utf-8")

    version_files: List[Dict[str, str]] = []
    if inc_analysis.get("versions"):
        version_files = save_incremental_version_files(pdf_path, out_dir, inc_analysis)

    manifest = {
        "images": images,
        "incremental": inc_analysis,
        "version_files": version_files,
        "metadata_txt": "metadata_report.txt",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path = out_dir / "extract_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if reporter:
        reporter(90, "Extracao concluida")

    return {
        "image_count": len([i for i in images if i.get("filename")]),
        "images_manifest": images,
        "metadata_report_path": str(meta_txt_path),
        "metadata_json_path": str(meta_json_path),
        "incremental_report_path": str(inc_report_path),
        "incremental_analysis": inc_analysis,
        "version_files": version_files,
        "extract_manifest_path": str(manifest_path),
        "extract_bundle_dir": str(out_dir),
    }
