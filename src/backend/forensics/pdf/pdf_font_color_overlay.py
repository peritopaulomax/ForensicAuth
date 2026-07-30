#!/usr/bin/env python3
"""
Per-page semi-transparent rectangles over vector text spans, colored by PDF
font resource. Default: distinct color per /BaseFont (including subset tag
XXXXXX+Name). Use --by-family for one color per logical family name only.

Writes a copy PDF and a TXT legend mapping color (RGB + HEX) to each font.

Limitations:
- Only text visible to get_text("dict") (not raster images or exotic paths).
- Subset mode matches spans to content-stream glyph boxes (Form XObjects included).
- Embedding/subset lines in the legend use heuristics (extract_font + BaseFont).
"""

from __future__ import annotations

import argparse
import colorsys
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz

from .pdf_forensic_scanner import (
    ContentInterpreter,
    resolve_page_resources,
)

# Subset fonts usually use a 6-character tag + original name in /BaseFont.
_SUBSET_PREFIX = re.compile(r"^[A-Za-z0-9]{6}\+")

# Okabe–Ito (colorblind-friendly) + extra hand-picked hues for more fonts.
_BASE_RGB255: List[Tuple[int, int, int]] = [
    (230, 159, 0),
    (86, 180, 233),
    (0, 158, 115),
    (240, 228, 66),
    (0, 114, 178),
    (213, 94, 0),
    (204, 121, 167),
    (153, 112, 61),
    (128, 62, 117),
    (0, 137, 108),
    (255, 105, 180),
    (60, 180, 75),
    (145, 30, 180),
    (0, 128, 128),
    (210, 105, 30),
]

# Helvetica (PDF standard) — cinza para não confundir com azul-céu do Arial Narrow.
_HELVETICA_NEUTRAL_RGB255: Tuple[int, int, int] = (78, 78, 78)

_NOOP_EMIT = lambda _r, _k, _t: None


def _norm255(rgb: Tuple[int, int, int]) -> Tuple[float, float, float]:
    return (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0)


def distinct_rgb255(index: int) -> Tuple[int, int, int]:
    """Return a visually separated RGB (0–255) for the given font index."""
    if index < len(_BASE_RGB255):
        return _BASE_RGB255[index]
    n = index - len(_BASE_RGB255)
    hue = (n * 0.618033988749895) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.78, 0.94)
    return (int(r * 255), int(g * 255), int(b * 255))


def _hex(rgb: Tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def norm_basefont(basefont: str) -> str:
    """Strip PDF subset tag (XXXXXX+Name) -> Name."""
    bf = basefont or ""
    if _SUBSET_PREFIX.match(bf):
        return bf[7:]
    return bf


def subset_tag(basefont: str) -> str:
    m = _SUBSET_PREFIX.match(basefont or "")
    return m.group(0)[:6] if m else ""


def is_subset_basefont(basefont: str) -> bool:
    return bool(_SUBSET_PREFIX.match(basefont or ""))


def span_family_name(span: dict) -> str:
    return (span.get("font") or "").strip() or "(sem nome)"


def xref_is_embedded(doc: fitz.Document, xref: int) -> bool:
    try:
        t = doc.extract_font(xref)
        return bool(
            t
            and len(t) >= 4
            and isinstance(t[3], (bytes, bytearray))
            and len(t[3]) > 0
        )
    except Exception:
        return False


def collect_xref_to_basefont(doc: fitz.Document) -> Dict[int, str]:
    out: Dict[int, str] = {}
    for pno in range(len(doc)):
        for row in doc.get_page_fonts(pno, full=True):
            xref = int(row[0])
            basefont = str(row[3] or "")
            out.setdefault(xref, basefont)
    return out


def _xrefs_for_font_key(doc: fitz.Document, key: str) -> List[int]:
    xref_bf = collect_xref_to_basefont(doc)
    if _SUBSET_PREFIX.match(key or ""):
        return [xr for xr, bf in xref_bf.items() if bf == key]
    return [xr for xr, bf in xref_bf.items() if norm_basefont(bf) == key]


def build_font_embed_report(
    doc: fitz.Document, font_keys: List[str]
) -> Dict[str, Tuple[str, str]]:
    xref_bf = collect_xref_to_basefont(doc)
    report: Dict[str, Tuple[str, str]] = {}
    for key in font_keys:
        match_xrefs = _xrefs_for_font_key(doc, key)
        if not match_xrefs:
            report[key] = (
                "desconhecido",
                "desconhecido (sem entrada em get_page_fonts)",
            )
            continue
        emb_xrefs = [xr for xr in match_xrefs if xref_is_embedded(doc, xr)]
        if not emb_xrefs:
            report[key] = ("não", "não aplicável (fonte não embutida)")
            continue
        subs = any(is_subset_basefont(xref_bf[xr]) for xr in emb_xrefs)
        fulls = any(not is_subset_basefont(xref_bf[xr]) for xr in emb_xrefs)
        if subs and fulls:
            report[key] = ("sim", "misto (há instâncias subset e completas)")
        elif subs:
            report[key] = ("sim", "subconjunto (subset)")
        else:
            report[key] = ("sim", "completa (embedding completo)")
    return report


def _page_basefont_by_xref(page: fitz.Page) -> Dict[int, str]:
    return {int(row[0]): str(row[3] or "") for row in page.get_fonts(full=True)}


class FontRunCollector(ContentInterpreter):
    """Content stream walk: record (glyph rect, full BaseFont) per visible glyph."""

    def __init__(
        self,
        doc: fitz.Document,
        resources_xref: int,
        font_metrics_cache: Dict,
        font_name_to_xref: Dict[str, int],
        xobject_map: Dict[str, int],
        emit_rect,
        *,
        mediabox: Optional[fitz.Rect] = None,
        basefont_by_xref: Dict[int, str],
    ) -> None:
        self.basefont_by_xref = basefont_by_xref
        self.glyph_runs: List[Tuple[fitz.Rect, str]] = []
        self._current_basefont = "(sem nome)"
        super().__init__(
            doc,
            resources_xref,
            font_metrics_cache,
            font_name_to_xref,
            xobject_map,
            emit_rect,
            mediabox=mediabox,
        )

    def _handle_operator(self, op: bytes) -> None:
        stack = self.operand_stack
        if op == b"Tf" and len(stack) >= 2:
            name_tok = stack[-2]
            if isinstance(name_tok, tuple) and name_tok[0] == "name":
                fname = name_tok[1]
                fxref = self.font_name_to_xref.get(fname)
                if fxref is not None:
                    self._current_basefont = self.basefont_by_xref.get(
                        fxref, f"{fname}?"
                    )
                else:
                    self._current_basefont = f"{fname}?"
            else:
                self._current_basefont = "(sem nome)"
        ContentInterpreter._handle_operator(self, op)

    def _add_text_rect(self, r: fitz.Rect) -> None:
        if self.text_render_mode != 3 and r.get_area() > 1e-6:
            self.glyph_runs.append((r, self._current_basefont))
        ContentInterpreter._add_text_rect(self, r)


def collect_page_glyph_runs(
    doc: fitz.Document, page: fitz.Page, font_metrics_cache: Dict
) -> List[Tuple[fitz.Rect, str]]:
    res_xref, fonts, xobjects = resolve_page_resources(doc, page)
    if res_xref is None:
        return []
    data = page.read_contents()
    if not data:
        return []
    collector = FontRunCollector(
        doc,
        res_xref,
        font_metrics_cache,
        fonts,
        xobjects,
        _NOOP_EMIT,
        mediabox=page.rect,
        basefont_by_xref=_page_basefont_by_xref(page),
    )
    collector.run(data)
    return collector.glyph_runs


def match_span_basefont(
    span_rect: fitz.Rect,
    glyph_runs: List[Tuple[fitz.Rect, str]],
    fallback: str,
) -> str:
    best_bf: Optional[str] = None
    best_area = 0.0
    cx = (span_rect.x0 + span_rect.x1) * 0.5
    cy = (span_rect.y0 + span_rect.y1) * 0.5
    for gr, bf in glyph_runs:
        inter = span_rect & gr
        a = inter.get_area()
        if a > best_area:
            best_area = a
            best_bf = bf
    if best_bf is not None and best_area > 1e-4:
        return best_bf
    # centro dentro de um glifo (spans muito pequenos)
    for gr, bf in glyph_runs:
        if gr.contains(fitz.Point(cx, cy)):
            return bf
    return fallback


def resolve_font_key(
    span: dict,
    glyph_runs: Optional[List[Tuple[fitz.Rect, str]]],
    by_subset: bool,
) -> str:
    family = span_family_name(span)
    if not by_subset or not glyph_runs:
        return family
    bbox = span.get("bbox")
    if not bbox or len(bbox) != 4:
        return family
    rect = fitz.Rect(bbox)
    if rect.is_empty:
        return family
    return match_span_basefont(rect, glyph_runs, family)


def build_glyph_runs_cache(
    doc: fitz.Document, font_metrics_cache: Dict
) -> Dict[int, List[Tuple[fitz.Rect, str]]]:
    cache: Dict[int, List[Tuple[fitz.Rect, str]]] = {}
    for page in doc:
        cache[page.number] = collect_page_glyph_runs(doc, page, font_metrics_cache)
    return cache


def collect_font_order(
    doc: fitz.Document,
    by_subset: bool,
    font_metrics_cache: Dict,
    glyph_cache: Optional[Dict[int, List[Tuple[fitz.Rect, str]]]] = None,
) -> List[str]:
    seen: Dict[str, None] = {}
    order: List[str] = []
    for page in doc:
        glyph_runs: Optional[List[Tuple[fitz.Rect, str]]] = None
        if by_subset and glyph_cache is not None:
            glyph_runs = glyph_cache.get(page.number)
        elif by_subset:
            glyph_runs = collect_page_glyph_runs(doc, page, font_metrics_cache)
        td = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        for block in td.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    key = resolve_font_key(span, glyph_runs, by_subset)
                    if key not in seen:
                        seen[key] = None
                        order.append(key)
    return order


def _color_for_key(name: str, index: int) -> Tuple[int, int, int]:
    if name == "Helvetica" or norm_basefont(name) == "Helvetica":
        return _HELVETICA_NEUTRAL_RGB255
    return distinct_rgb255(index)


def build_font_key_to_legend_num(fonts_in_order: List[str]) -> Dict[str, int]:
    return {name: i for i, name in enumerate(fonts_in_order, start=1)}


# ---------------------------------------------------------------------------
# Overlay por tamanho de fonte
# ---------------------------------------------------------------------------


def span_font_size(span: dict) -> float:
    """Return the font size (points) reported by PyMuPDF for a span."""
    size = span.get("size")
    if size is None:
        return 0.0
    try:
        return float(size)
    except (TypeError, ValueError):
        return 0.0


def collect_font_sizes(doc: fitz.Document) -> List[float]:
    """Return sorted unique font sizes seen in the document."""
    seen: set[float] = set()
    for page in doc:
        td = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        for block in td.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    size = span_font_size(span)
                    if size > 0:
                        seen.add(round(size, 2))
    return sorted(seen)


def _color_for_size(size: float, min_size: float, max_size: float) -> Tuple[int, int, int]:
    """Map a font size to an RGB heatmap color (blue -> green -> yellow -> red)."""
    if max_size <= min_size:
        return (128, 128, 128)
    # Normalize to 0..1
    t = (size - min_size) / (max_size - min_size)
    # Use HSV: blue (0.66) -> red (0.0)
    hue = 0.66 * (1.0 - t)
    r, g, b = colorsys.hsv_to_rgb(hue, 0.82, 0.95)
    return (int(r * 255), int(g * 255), int(b * 255))


def build_size_to_rgb255(sizes: List[float]) -> Dict[float, Tuple[int, int, int]]:
    if not sizes:
        return {}
    min_size, max_size = sizes[0], sizes[-1]
    return {size: _color_for_size(size, min_size, max_size) for size in sizes}


def apply_size_overlays(
    doc: fitz.Document,
    size_to_rgb255: Dict[float, Tuple[int, int, int]],
    fill_opacity: float,
) -> int:
    """Draw rectangles colored by font size over every text span."""
    count = 0
    sizes = sorted(size_to_rgb255.keys())
    if not sizes:
        return 0
    min_size, max_size = sizes[0], sizes[-1]
    for page in doc:
        td = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        for block in td.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    size = span_font_size(span)
                    if size <= 0:
                        continue
                    bbox = span.get("bbox")
                    if not bbox or len(bbox) != 4:
                        continue
                    text = str(span.get("text") or "")
                    if not text.strip():
                        continue
                    rgb = _color_for_size(size, min_size, max_size)
                    rect = fitz.Rect(bbox)
                    if rect.is_empty or rect.width < 4 or rect.height < 4:
                        continue
                    annot = page.add_rect_annot(rect)
                    fr, fg, fb = _norm255(rgb)
                    annot.set_colors(stroke=(fr, fg, fb), fill=(fr, fg, fb))
                    annot.set_border(width=0)
                    annot.set_opacity(fill_opacity)
                    try:
                        annot.set_blendmode(fitz.PDF_BM_Multiply)
                    except Exception:
                        pass
                    annot.update()
                    count += 1
    return count


def write_size_legend(
    path: Path,
    sizes: List[float],
    size_to_rgb255: Dict[float, Tuple[int, int, int]],
    fill_opacity: float,
    n_rects: int,
) -> None:
    lines = [
        "# Legenda: tamanho da fonte (pt) → cor do realce",
        f"# Modo: uma cor por tamanho de fonte",
        f"# Opacidade do preenchimento: {fill_opacity:.2f}",
        f"# Retângulos desenhados: {n_rects}",
        f"# Tamanhos distintos: {len(sizes)}",
        "# Escala: azul (menor) → verde → amarelo → vermelho (maior)",
        "",
    ]
    for size in sizes:
        rgb = size_to_rgb255[size]
        lines.append(f"{size:.2f} pt")
        lines.append(f"   RGB: {rgb[0]}, {rgb[1]}, {rgb[2]}")
        lines.append(f"   HEX: {_hex(rgb)}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _legend_badge_rect(page: fitz.Page, anchor: fitz.Rect, label: str) -> Optional[fitz.Rect]:
    """Caixa fixa legível para o número da legenda (independente da altura do span)."""
    fs = 8.0
    pad = 2.0
    badge_w = max(12.0, fs * 0.58 * len(label) + 2 * pad)
    badge_h = max(11.0, fs + 2 * pad)
    box = fitz.Rect(anchor.x0, anchor.y0, anchor.x0 + badge_w, anchor.y0 + badge_h)
    box &= page.rect
    if box.width < 9 or box.height < 9:
        return None
    return box


def _draw_legend_number(page: fitz.Page, rect: fitz.Rect, legend_num: int) -> None:
    """Desenha o número da legenda TXT no canto superior-esquerdo do realce."""
    label = str(legend_num)
    box = _legend_badge_rect(page, rect, label)
    if box is None:
        return

    fs = 8.0
    pad = 2.0
    shape = page.new_shape()
    shape.draw_rect(box)
    shape.finish(fill=(1, 1, 1), color=(0.12, 0.12, 0.12), width=0.45, fill_opacity=0.96)
    shape.commit(overlay=True)

    # insert_textbox falha em caixas pequenas; insert_text é mais confiável.
    baseline_y = box.y1 - pad - fs * 0.2
    page.insert_text(
        fitz.Point(box.x0 + pad, baseline_y),
        label,
        fontsize=fs,
        fontname="helv",
        color=(0, 0, 0),
    )


def apply_overlays(
    doc: fitz.Document,
    font_to_rgb255: Dict[str, Tuple[int, int, int]],
    font_key_to_num: Dict[str, int],
    fill_opacity: float,
    by_subset: bool,
    font_metrics_cache: Dict,
    glyph_cache: Optional[Dict[int, List[Tuple[fitz.Rect, str]]]] = None,
) -> int:
    count = 0
    for page in doc:
        glyph_runs: Optional[List[Tuple[fitz.Rect, str]]] = None
        if by_subset and glyph_cache is not None:
            glyph_runs = glyph_cache.get(page.number)
        elif by_subset:
            glyph_runs = collect_page_glyph_runs(doc, page, font_metrics_cache)
        td = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        for block in td.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    key = resolve_font_key(span, glyph_runs, by_subset)
                    bbox = span.get("bbox")
                    if not bbox or len(bbox) != 4:
                        continue
                    text = str(span.get("text") or "")
                    if not text.strip():
                        continue
                    r, g, b = font_to_rgb255.get(key, (128, 128, 128))
                    rect = fitz.Rect(bbox)
                    if rect.is_empty or rect.width < 4 or rect.height < 4:
                        continue
                    annot = page.add_rect_annot(rect)
                    fr, fg, fb = _norm255((r, g, b))
                    annot.set_colors(stroke=(fr, fg, fb), fill=(fr, fg, fb))
                    annot.set_border(width=0)
                    annot.set_opacity(fill_opacity)
                    try:
                        annot.set_blendmode(fitz.PDF_BM_Multiply)
                    except Exception:
                        pass
                    annot.update()
                    legend_num = font_key_to_num.get(key)
                    if legend_num is not None:
                        _draw_legend_number(page, rect, legend_num)
                    count += 1
    return count


def write_legend(
    path: Path,
    fonts_in_order: List[str],
    font_to_rgb255: Dict[str, Tuple[int, int, int]],
    font_embed: Dict[str, Tuple[str, str]],
    fill_opacity: float,
    n_rects: int,
    by_subset: bool,
) -> None:
    mode = (
        "uma cor por /BaseFont (subset distinto = cor distinta)"
        if by_subset
        else "uma cor por nome de família (span font)"
    )
    lines = [
        "# Legenda: fonte do PDF → cor do realce",
        f"# Modo: {mode}",
        "# Embutida / subset: heurística via PyMuPDF (extract_font + prefixo 6+ em BaseFont).",
        f"# Opacidade do preenchimento: {fill_opacity:.2f}",
        f"# Retângulos desenhados: {n_rects}",
        f"# Chaves distintas: {len(fonts_in_order)}",
        "# No PDF, cada realce mostra o número (1, 2, 3…) igual ao da lista abaixo.",
        "",
    ]
    for i, font in enumerate(fonts_in_order, start=1):
        rgb = font_to_rgb255[font]
        emb, sub = font_embed.get(font, ("desconhecido", "desconhecido"))
        lines.append(f"{i}. {font}")
        if by_subset:
            fam = norm_basefont(font)
            if fam != font:
                lines.append(f"   Família: {fam}")
            tag = subset_tag(font)
            if tag:
                lines.append(f"   Tag subset: {tag}")
        lines.append(f"   RGB: {rgb[0]}, {rgb[1]}, {rgb[2]}")
        lines.append(f"   HEX: {_hex(rgb)}")
        lines.append(f"   Fonte embutida: {emb}")
        lines.append(f"   Subconjunto ou completa: {sub}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def run_font_color_overlay(
    input_pdf: str | Path,
    output_pdf: str | Path,
    legend_txt: str | Path,
    opacity: float = 0.42,
    by_subset: bool = True,
    mode: str = "font",
) -> Dict[str, object]:
    """Gera PDF com overlay de fontes ou tamanhos e ficheiro de legenda (API para plugin)."""
    src = Path(input_pdf).expanduser().resolve()
    out_pdf = Path(output_pdf).expanduser().resolve()
    out_txt = Path(legend_txt).expanduser().resolve()
    op = max(0.05, min(1.0, float(opacity)))
    mode = (mode or "font").lower()

    doc = fitz.open(src)
    font_metrics_cache: Dict = {}
    fonts_in_order: List[str] = []
    sizes_in_order: List[float] = []
    n_rects = 0
    try:
        if mode == "size":
            sizes_in_order = collect_font_sizes(doc)
            size_to_rgb255 = build_size_to_rgb255(sizes_in_order)
            n_rects = apply_size_overlays(doc, size_to_rgb255, op)
        else:
            glyph_cache: Optional[Dict[int, List[Tuple[fitz.Rect, str]]]] = None
            if by_subset:
                glyph_cache = build_glyph_runs_cache(doc, font_metrics_cache)
            fonts_in_order = collect_font_order(doc, by_subset, font_metrics_cache, glyph_cache)
            font_embed = build_font_embed_report(doc, fonts_in_order)
            font_to_rgb255 = {name: _color_for_key(name, i) for i, name in enumerate(fonts_in_order)}
            font_key_to_num = build_font_key_to_legend_num(fonts_in_order)
            n_rects = apply_overlays(
                doc,
                font_to_rgb255,
                font_key_to_num,
                op,
                by_subset,
                font_metrics_cache,
                glyph_cache,
            )
        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        doc.save(out_pdf, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()

    if mode == "size":
        size_to_rgb255 = build_size_to_rgb255(sizes_in_order)
        write_size_legend(out_txt, sizes_in_order, size_to_rgb255, op, n_rects)
    else:
        write_legend(out_txt, fonts_in_order, font_to_rgb255, font_embed, op, n_rects, by_subset)

    return {
        "fonts_count": len(fonts_in_order),
        "sizes_count": len(sizes_in_order),
        "rectangles": n_rects,
        "fonts": fonts_in_order,
        "sizes": sizes_in_order,
        "mode": "size" if mode == "size" else ("subset" if by_subset else "family"),
    }


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Sobrepõe retângulos coloridos por fonte (texto vetorial), página a página."
    )
    p.add_argument("input_pdf", type=Path, help="PDF de entrada")
    p.add_argument(
        "-o",
        "--output-pdf",
        type=Path,
        default=None,
        help="PDF de saída (default: <entrada>_FONTMAP.pdf)",
    )
    p.add_argument(
        "-t",
        "--legend-txt",
        type=Path,
        default=None,
        help="TXT da legenda (default: <entrada>_FONTMAP.txt)",
    )
    p.add_argument(
        "--opacity",
        type=float,
        default=0.42,
        help="Opacidade do preenchimento (0–1), default 0.42",
    )
    p.add_argument(
        "--by-family",
        action="store_true",
        help="Cor só pelo nome da família (span font); predefinido é --by-subset",
    )
    args = p.parse_args(argv)

    by_subset = not args.by_family

    src = args.input_pdf.expanduser().resolve()
    if not src.is_file():
        print(f"Ficheiro não encontrado: {src}", file=sys.stderr)
        return 1

    stem = src.stem
    parent = src.parent
    out_pdf = args.output_pdf or (parent / f"{stem}_FONTMAP.pdf")
    out_txt = args.legend_txt or (parent / f"{stem}_FONTMAP.txt")

    op = max(0.05, min(1.0, args.opacity))

    doc = fitz.open(src)
    font_metrics_cache: Dict = {}
    try:
        glyph_cache: Optional[Dict[int, List[Tuple[fitz.Rect, str]]]] = None
        if by_subset:
            print("A analisar content streams (subset por página)...", file=sys.stderr)
            glyph_cache = build_glyph_runs_cache(doc, font_metrics_cache)
        fonts_in_order = collect_font_order(
            doc, by_subset, font_metrics_cache, glyph_cache
        )
        font_embed = build_font_embed_report(doc, fonts_in_order)
        font_to_rgb255 = {}
        for i, name in enumerate(fonts_in_order):
            font_to_rgb255[name] = _color_for_key(name, i)
        font_key_to_num = build_font_key_to_legend_num(fonts_in_order)
        n_rects = apply_overlays(
            doc,
            font_to_rgb255,
            font_key_to_num,
            op,
            by_subset,
            font_metrics_cache,
            glyph_cache,
        )
        doc.save(out_pdf, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()

    write_legend(
        out_txt, fonts_in_order, font_to_rgb255, font_embed, op, n_rects, by_subset
    )
    modo = "subset" if by_subset else "família"
    print(f"Escrito: {out_pdf}")
    print(
        f"Legenda: {out_txt} ({len(fonts_in_order)} chaves [{modo}], {n_rects} realces)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
