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

from pdf_forensic_scanner import (
    ContentInterpreter,
    _build_font_name_to_xref,
    _build_xobject_name_to_xref,
    _merge_name_maps,
    _parse_xref_ref,
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


def _page_resources_xref(doc: fitz.Document, page: fitz.Page) -> int:
    rk = doc.xref_get_key(page.xref, "Resources")
    if rk[0] == "xref":
        xr = _parse_xref_ref(rk[1])
        if xr is not None:
            return xr
    raise ValueError(f"Página {page.number} sem Resources xref válido")


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
    res_xref = _page_resources_xref(doc, page)
    fonts = _build_font_name_to_xref(doc, res_xref)
    xobjects = _build_xobject_name_to_xref(doc, res_xref)
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


def _legend_label_fontsize(rect: fitz.Rect, label: str) -> float:
    base = max(4.0, min(8.0, rect.height * 0.55))
    if len(label) >= 3:
        base = min(base, 6.0)
    return base


def _draw_legend_number(page: fitz.Page, rect: fitz.Rect, legend_num: int) -> None:
    """Desenha o número da legenda TXT no canto superior-esquerdo do realce."""
    label = str(legend_num)
    fs = _legend_label_fontsize(rect, label)
    if rect.height < 3.5 and len(label) > 1:
        return
    pad = 0.5
    lw = fs * 0.62 * len(label) + 2 * pad
    lh = fs + 2 * pad
    box = fitz.Rect(rect.x0, rect.y0, rect.x0 + lw, rect.y0 + lh)
    box &= page.rect
    if box.is_empty or box.width < 2 or box.height < 2:
        return
    shape = page.new_shape()
    shape.draw_rect(box)
    shape.finish(fill=(1, 1, 1), color=(0.2, 0.2, 0.2), width=0.25, fill_opacity=0.92)
    shape.commit(overlay=True)
    page.insert_textbox(
        box,
        label,
        fontsize=fs,
        fontname="helv",
        color=(0, 0, 0),
        align=fitz.TEXT_ALIGN_CENTER,
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
                    r, g, b = font_to_rgb255.get(key, (128, 128, 128))
                    rect = fitz.Rect(bbox)
                    if rect.is_empty or rect.width <= 0 or rect.height <= 0:
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
