#!/usr/bin/env python3
"""
Forensic PDF scanner: detect Adobe Acrobat TouchUp_TextEdit marked content
in page and Form XObject content streams, estimate geometry in user space,
and write highlights to a copy of the document.

Also writes ``<nome>_FORENSIC_TOUCHUP.txt`` next to the source PDF with the
text extracted from each TouchUp_TextEdit region (stream order).

Supports:
  - MP TouchUp_TextEdit (common Acrobat pattern) with optional clip ``re``
    before BT/ET and/or visible text spans
  - q/Q graphics stack, cm concatenation, BT/ET text objects, Tj/'/"/TJ
  - Form XObject recursion on Do
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import fitz

EmitTouchupFn = Callable[[fitz.Rect, str, str], None]

LOG = logging.getLogger("pdf_forensic")

# ---------------------------------------------------------------------------
# PDF content stream tokenization
# ---------------------------------------------------------------------------

PDF_OPERATORS = frozenset(
    {
        b"w",
        b"W",
        b"W*",
        b"J",
        b"j",
        b"M",
        b"d",
        b"ri",
        b"i",
        b"gs",
        b"q",
        b"Q",
        b"cm",
        b"m",
        b"l",
        b"c",
        b"v",
        b"y",
        b"h",
        b"re",
        b"S",
        b"s",
        b"f",
        b"f*",
        b"B",
        b"B*",
        b"b",
        b"b*",
        b"n",
        b"BT",
        b"ET",
        b"BMC",
        b"BDC",
        b"EMC",
        b"MP",
        b"DP",
        b"BX",
        b"EX",
        b"Tc",
        b"Tw",
        b"Tz",
        b"TL",
        b"Tf",
        b"Tr",
        b"Ts",
        b"Td",
        b"TD",
        b"TL",
        b"Tm",
        b"T*",
        b"Tj",
        b"TJ",
        b"'",
        b'"',
        b"d0",
        b"d1",
        b"CS",
        b"cs",
        b"SC",
        b"SCN",
        b"sc",
        b"scn",
        b"G",
        b"g",
        b"RG",
        b"rg",
        b"K",
        b"k",
        b"sh",
        b"BI",
        b"ID",
        b"EI",
        b"Do",
        b"BX",
        b"EX",
    }
)


def _skip_ws_comments(data: bytes, i: int) -> int:
    n = len(data)
    while i < n:
        c = data[i]
        if c in b" \t\r\n\f\x00":
            i += 1
            continue
        if c == ord("%"):
            i += 1
            while i < n and data[i] not in (10, 13):
                i += 1
            if i < n:
                i += 1
            continue
        break
    return i


def _read_string_paren(data: bytes, i: int) -> Tuple[bytes, int]:
    """Read a (...) PDF string starting at position i (i points to '(')."""
    assert data[i] == ord("(")
    depth = 0
    out = bytearray()
    i += 1
    n = len(data)
    while i < n:
        c = data[i]
        if c == ord("\\"):
            i += 1
            if i >= n:
                break
            esc = data[i]
            i += 1
            if esc in b"01234567":
                octal = [esc]
                for _ in range(2):
                    if i < n and data[i] in b"01234567":
                        octal.append(data[i])
                        i += 1
                    else:
                        break
                out.append(int(bytes(octal), 8) & 0xFF)
                continue
            out.extend(
                {
                    ord("n"): b"\n",
                    ord("r"): b"\r",
                    ord("t"): b"\t",
                    ord("b"): b"\b",
                    ord("f"): b"\f",
                    ord("("): b"(",
                    ord(")"): b")",
                    ord("\\"): b"\\",
                }.get(esc, bytes([esc]))
            )
            continue
        if c == ord("("):
            depth += 1
            out.append(c)
            i += 1
            continue
        if c == ord(")"):
            if depth:
                depth -= 1
                out.append(c)
                i += 1
                continue
            i += 1
            break
        out.append(c)
        i += 1
    return bytes(out), i


def _read_hex_string(data: bytes, i: int) -> Tuple[bytes, int]:
    """Read <...> hex string; i points to '<' (not '<<')."""
    assert data[i] == ord("<")
    i += 1
    n = len(data)
    buf = bytearray()
    while i < n:
        c = data[i]
        if c == ord(">"):
            i += 1
            break
        if c in b" \t\r\n\f\x00":
            i += 1
            continue
        hi = c
        i += 1
        if i >= n:
            break
        lo = data[i]
        i += 1
        if hi in b"0123456789abcdefABCDEF" and lo in b"0123456789abcdefABCDEF":
            buf.append(int(chr(hi) + chr(lo), 16))
    return bytes(buf), i


def _read_dict(data: bytes, i: int) -> Tuple[dict, int]:
    """Read << ... >> into a shallow dict of name -> raw token subtree."""
    assert data[i : i + 2] == b"<<"
    i += 2
    d: Dict[str, Any] = {}
    n = len(data)
    while i < n:
        i = _skip_ws_comments(data, i)
        if i + 1 < n and data[i : i + 2] == b">>":
            return d, i + 2
        if i >= n or data[i] != ord("/"):
            # skip unknown token
            tok, i = _read_token(data, i)
            if isinstance(tok, tuple) and tok[0] == "enddict":
                return d, tok[1]
            continue
        name, i = _read_name(data, i)
        obj, i = _read_token(data, i)
        d[name] = obj
    return d, i


def _read_name(data: bytes, i: int) -> Tuple[str, int]:
    assert data[i] == ord("/")
    i += 1
    start = i
    n = len(data)
    while i < n:
        c = data[i]
        if c in b" \t\r\n\f\x00()<>[]{}/%":
            break
        if c == ord("#") and i + 2 < n:
            hx = data[i + 1 : i + 3]
            if all(x in b"0123456789abcdefABCDEF" for x in hx):
                i += 3
                continue
        i += 1
    raw = data[start:i].decode("latin-1", "replace")
    raw = raw.replace("#20", " ").replace("#2F", "/")
    return raw, i


def _read_number(data: bytes, i: int) -> Tuple[Union[int, float], int]:
    n = len(data)
    start = i
    if i < n and data[i] in b"+-":
        i += 1
    while i < n and data[i] in b"0123456789.":
        i += 1
    s = data[start:i].decode("ascii")
    if "." in s:
        return float(s), i
    return int(s), i


def _read_array(data: bytes, i: int) -> Tuple[list, int]:
    assert data[i] == ord("[")
    i += 1
    items: List[Any] = []
    n = len(data)
    while i < n:
        i = _skip_ws_comments(data, i)
        if i >= n:
            break
        if data[i] == ord("]"):
            return items, i + 1
        obj, i = _read_token(data, i)
        items.append(obj)
    return items, i


def _read_token(data: bytes, i: int) -> Tuple[Any, int]:
    i = _skip_ws_comments(data, i)
    n = len(data)
    if i >= n:
        return None, i
    c = data[i]
    if c == ord("("):
        return _read_string_paren(data, i)
    if c == ord("<"):
        if i + 1 < n and data[i + 1] == ord("<"):
            return _read_dict(data, i)
        return _read_hex_string(data, i)
    if c == ord("["):
        return _read_array(data, i)
    if c == ord("/"):
        name, j = _read_name(data, i)
        return ("name", name), j
    if c in b"+-" or c in b"0123456789" or (c == ord(".") and i + 1 < n and data[i + 1] in b"0123456789"):
        return _read_number(data, i)
    # operator or unknown word
    start = i
    while i < n and data[i] not in b" \t\r\n\f\x00()<>[]{}/%":
        i += 1
    word = data[start:i]
    return word, i


def _skip_inline_image(data: bytes, i: int) -> int:
    """After 'BI', skip until an ``EI`` token (end of inline image)."""
    for pat in (b"\nEI\n", b"\r\nEI\r\n", b"\nEI\r", b"\rEI\n"):
        j = data.find(pat, i)
        if j >= 0:
            return j + len(pat)
    j = data.find(b"EI", i)
    return j + 2 if j >= 0 else len(data)


def tokenize_content_stream(data: bytes):
    """Yield (token, pos) where token is number, str, bytes (operator), tuple."""
    i = 0
    n = len(data)
    while i < n:
        i0 = i
        i = _skip_ws_comments(data, i)
        if i >= n:
            break
        if data[i : i + 2] == b"BI":
            yield (b"BI", i0)
            i = _skip_inline_image(data, i + 2)
            continue
        tok, j = _read_token(data, i)
        if tok is None:
            break
        yield (tok, i)
        i = j


# ---------------------------------------------------------------------------
# Font metrics (Widths / DW / CID heuristics)
# ---------------------------------------------------------------------------


@dataclass
class FontMetrics:
    font_xref: int
    subtype: str = "/TrueType"
    encoding: str = ""
    first_char: int = 32
    last_char: int = 255
    widths: Optional[List[float]] = None
    dw: float = 1000.0  # default width units (1/1000 em space)


def _parse_xref_ref(val: str) -> Optional[int]:
    m = re.match(r"(\d+)\s+0\s+R", val.strip())
    return int(m.group(1)) if m else None


def _parse_numeric_array_brackets(s: str) -> List[float]:
    s = s.strip()
    if s.startswith("["):
        s = s[1:]
    if s.endswith("]"):
        s = s[:-1]
    nums: List[float] = []
    for m in re.finditer(r"[-+]?\d*\.?\d+", s):
        v = m.group(0)
        nums.append(float(v) if "." in v else int(v))
    return nums


def _load_font_metrics(doc: fitz.Document, font_xref: int) -> FontMetrics:
    fm = FontMetrics(font_xref=font_xref)
    try:
        st = doc.xref_get_key(font_xref, "Subtype")
        if st[0] == "name":
            fm.subtype = st[1]
        enc = doc.xref_get_key(font_xref, "Encoding")
        if enc[0] == "name":
            fm.encoding = enc[1]
        fc = doc.xref_get_key(font_xref, "FirstChar")
        if fc[0] == "int":
            fm.first_char = int(fc[1])
        lc = doc.xref_get_key(font_xref, "LastChar")
        if lc[0] == "int":
            fm.last_char = int(lc[1])
        w = doc.xref_get_key(font_xref, "Widths")
        if w[0] == "array":
            fm.widths = _parse_numeric_array_brackets(w[1])
        dw = doc.xref_get_key(font_xref, "DW")
        if dw[0] in ("int", "float", "real"):
            fm.dw = float(dw[1])
    except Exception as ex:  # noqa: BLE001
        LOG.debug("Font xref %s partial load: %s", font_xref, ex)
    return fm


def _parse_name_to_xref_from_pdf_dict(body: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for m in re.finditer(r"/([A-Za-z0-9.#_\-]+)\s+(\d+)\s+0\s+R", body):
        out[m.group(1)] = int(m.group(2))
    return out


_MAX_XOBJECT_DEPTH = 40


def _read_subresource_map(
    doc: fitz.Document,
    container_xref: int,
    key: str,
    visited: Optional[set[int]] = None,
) -> Dict[str, int]:
    """Font ou XObject: direto no container, xref ou inline em Resources."""
    if visited is None:
        visited = set()
    if container_xref in visited:
        return {}
    visited.add(container_xref)

    out: Dict[str, int] = {}
    try:
        entry = doc.xref_get_key(container_xref, key)
        if entry[0] == "xref":
            dict_xref = _parse_xref_ref(entry[1])
            if dict_xref is not None and dict_xref not in visited:
                out = _parse_name_to_xref_from_pdf_dict(doc.xref_object(dict_xref))
        elif entry[0] == "dict":
            out = _parse_name_to_xref_from_pdf_dict(entry[1])
    except Exception as ex:  # noqa: BLE001
        LOG.debug("_read_subresource_map %s direct: %s", key, ex)
    if out:
        return out

    try:
        res = doc.xref_get_key(container_xref, "Resources")
        if res[0] == "xref":
            res_xref = _parse_xref_ref(res[1])
            if res_xref is not None and res_xref not in visited:
                return _read_subresource_map(doc, res_xref, key, visited)
        elif res[0] == "dict":
            sub = re.search(rf"/{re.escape(key)}\s*<<(.*?)>>", res[1], re.DOTALL)
            if sub:
                out = _parse_name_to_xref_from_pdf_dict(sub.group(0))
    except Exception as ex:  # noqa: BLE001
        LOG.debug("_read_subresource_map %s via Resources: %s", key, ex)
    return out


def resolve_page_resources_xref(doc: fitz.Document, page_xref: int) -> Optional[int]:
    """
    Resolve o container de Resources de uma pagina:
    xref indirecto, Resources inline no proprio objeto, ou herdado de /Pages.
    """
    visited: set[int] = set()
    current = page_xref
    while current and current not in visited:
        visited.add(current)
        rk = doc.xref_get_key(current, "Resources")
        if rk[0] == "xref":
            xr = _parse_xref_ref(rk[1])
            if xr is not None:
                return xr
        if rk[0] == "dict":
            return current
        pk = doc.xref_get_key(current, "Parent")
        if pk[0] != "xref":
            break
        parent = _parse_xref_ref(pk[1])
        if parent is None:
            break
        current = parent
    return None


def resolve_page_resources(
    doc: fitz.Document, page: fitz.Page
) -> Tuple[Optional[int], Dict[str, int], Dict[str, int]]:
    """
    Resolve Resources da pagina e mapas Font / XObject (sem recursao infinita em ciclos).
    Retorna (resources_xref, font_name_to_xref, xobject_name_to_xref); xref None se ausente.
    """
    res_xref = resolve_page_resources_xref(doc, page.xref)
    if res_xref is None:
        return None, {}, {}
    visited: set[int] = set()
    fonts = _read_subresource_map(doc, res_xref, "Font", visited)
    xobjects = _read_subresource_map(doc, res_xref, "XObject", visited)
    return res_xref, fonts, xobjects


def _build_font_name_to_xref(doc: fitz.Document, resources_xref: int) -> Dict[str, int]:
    try:
        return _read_subresource_map(doc, resources_xref, "Font")
    except Exception as ex:  # noqa: BLE001
        LOG.debug("build_font_name_to_xref: %s", ex)
        return {}


def _build_xobject_name_to_xref(doc: fitz.Document, resources_xref: int) -> Dict[str, int]:
    try:
        return _read_subresource_map(doc, resources_xref, "XObject")
    except Exception as ex:  # noqa: BLE001
        LOG.debug("build_xobject_name_to_xref: %s", ex)
        return {}


def _merge_name_maps(
    parent: Dict[str, int], child: Dict[str, int]
) -> Dict[str, int]:
    merged = dict(parent)
    merged.update(child)
    return merged


def _glyph_width(
    fm: Optional[FontMetrics], char_code: int, is_cid_hex: bool
) -> float:
    if fm is None:
        return 500.0
    if is_cid_hex or fm.subtype in ("/Type0", "/CIDFontType0", "/CIDFontType2"):
        return float(fm.dw)
    if fm.widths:
        idx = char_code - fm.first_char
        if 0 <= idx < len(fm.widths):
            w = fm.widths[idx]
            if w:
                return float(w)
    return float(fm.dw)


def _decode_pdf_text_for_report(s: bytes, hex_cid: bool) -> str:
    """Decode PDF string operand for human-readable forensic export."""
    if not s:
        return ""
    if hex_cid and len(s) >= 2:
        return s.decode("utf-16-be", errors="replace")
    return s.decode("latin-1", errors="replace")


def _decode_pdf_string(s: bytes, hex_cid: bool) -> List[int]:
    """Return list of character codes (single-byte or CID as 16-bit)."""
    if hex_cid:
        if len(s) % 2:
            s = s + b"\0"
        return [s[i] * 256 + s[i + 1] for i in range(0, len(s), 2)]
    return list(s)


# ---------------------------------------------------------------------------
# Interpreter
# ---------------------------------------------------------------------------


# Fraction of page area above which a pre-BT ``re`` clip is treated as Acrobat
# background/template (ignored for TouchUp MP highlights).
MAX_TOUCHUP_CLIP_AREA_FRAC = 0.14
# If union of all glyph rects in one MP session exceeds this fraction of the
# page, split into per-line unions (baseline clustering) instead of one slab.
MAX_TOUCHUP_TEXT_UNION_FRAC = 0.32


def _union_rects(rects: List[fitz.Rect]) -> fitz.Rect:
    u = rects[0]
    for r in rects[1:]:
        u |= r
    return u


def _cluster_rects_by_baseline(
    rects: List[fitz.Rect], band: float, max_out: int = 120
) -> List[fitz.Rect]:
    """Merge rects that share similar vertical center (same text line)."""
    if not rects:
        return []
    keyed = sorted(rects, key=lambda r: ((r.y0 + r.y1) * 0.5, r.x0))
    lines: List[List[fitz.Rect]] = []
    cur: List[fitz.Rect] = []
    last_cy: Optional[float] = None
    for r in keyed:
        cy = (r.y0 + r.y1) * 0.5
        if last_cy is None or abs(cy - last_cy) <= band:
            cur.append(r)
            last_cy = cy if last_cy is None else (last_cy * (len(cur) - 1) + cy) / len(cur)
        else:
            lines.append(cur)
            cur = [r]
            last_cy = cy
    if cur:
        lines.append(cur)
    out: List[fitz.Rect] = []
    for line in lines:
        out.append(_union_rects(line))
        if len(out) >= max_out:
            break
    return out


def _text_for_highlight_rect(
    runs: List[Tuple[str, List[fitz.Rect]]],
    highlight_rect: fitz.Rect,
    min_frac: float = 0.22,
) -> str:
    """Junta fragmentos cujos glifos intersectam de forma relevante o realce."""
    parts: List[str] = []
    for frag, grs in runs:
        if not grs or not frag:
            continue
        n_hit = 0
        for gr in grs:
            if gr.intersects(highlight_rect):
                inter = gr & highlight_rect
                if inter.get_area() > 1e-5:
                    n_hit += 1
        if n_hit and (n_hit / len(grs)) >= min_frac:
            parts.append(frag)
    return "".join(parts).strip()


@dataclass
class MPTouchSession:
    pre_bt_rects: List[fitz.Rect] = field(default_factory=list)
    text_rects: List[fitz.Rect] = field(default_factory=list)
    # (texto decodificado do operando Tj/TJ, retângulos de glifo desse operando)
    runs: List[Tuple[str, List[fitz.Rect]]] = field(default_factory=list)
    saw_bt: bool = False
    max_font_size: float = 1.0


@dataclass
class TouchUpBucket:
    rects: List[fitz.Rect] = field(default_factory=list)
    runs: List[Tuple[str, List[fitz.Rect]]] = field(default_factory=list)


def _clone_mc_stack(
    mc_stack: List[Tuple[str, Optional[TouchUpBucket]]],
) -> List[Tuple[str, Optional[TouchUpBucket]]]:
    out: List[Tuple[str, Optional[TouchUpBucket]]] = []
    for tag, bucket in mc_stack:
        if bucket is None:
            out.append((tag, None))
        else:
            out.append(
                (
                    tag,
                    TouchUpBucket(
                        rects=list(bucket.rects),
                        runs=[(t, list(rs)) for t, rs in bucket.runs],
                    ),
                )
            )
    return out


class ContentInterpreter:
    def __init__(
        self,
        doc: fitz.Document,
        resources_xref: int,
        font_metrics_cache: Dict[int, FontMetrics],
        font_name_to_xref: Dict[str, int],
        xobject_map: Dict[str, int],
        emit_rect: EmitTouchupFn,
        mediabox: Optional[fitz.Rect] = None,
        xobject_depth: int = 0,
    ):
        self.doc = doc
        self.resources_xref = resources_xref
        self.font_metrics_cache = font_metrics_cache
        self.font_name_to_xref = font_name_to_xref
        self.xobject_map = xobject_map
        self.emit_touchup = emit_rect
        self.mediabox = mediabox
        self.xobject_depth = xobject_depth
        if mediabox is not None and mediabox.get_area() > 0:
            self._max_clip_area = mediabox.get_area() * MAX_TOUCHUP_CLIP_AREA_FRAC
        else:
            self._max_clip_area = None  # no filter

        self.ctm_stack: List[fitz.Matrix] = [fitz.Matrix(1, 0, 0, 1, 0, 0)]
        self.tm = fitz.Matrix(1, 0, 0, 1, 0, 0)
        self.tlm = fitz.Matrix(1, 0, 0, 1, 0, 0)
        self.font_size = 12.0
        self.font_metrics: Optional[FontMetrics] = None
        self.text_render_mode = 0
        self.hex_cid_string = False
        self.leading = 0.0

        # Marked content stack: list of (tag, TouchUpBucket or None)
        self.mc_stack: List[Tuple[str, Optional[TouchUpBucket]]] = []

        self.mp_session: Optional[MPTouchSession] = None

        self.operand_stack: List[Any] = []

    @property
    def ctm(self) -> fitz.Matrix:
        return self.ctm_stack[-1]

    def _transform_rect(self, r: fitz.Rect) -> fitz.Rect:
        return r * self.ctm

    def _transform_point(self, p: fitz.Point) -> fitz.Point:
        return p * self.tm * self.ctm

    def _char_bbox(self, dx: float) -> fitz.Rect:
        """Axis-aligned bbox for next glyph of width dx in text space (approx)."""
        fs = self.font_size
        # conservative ascent/descent in text space units (Widths are 1/1000 em)
        asc = 0.8 * fs
        desc = 0.2 * fs
        r = fitz.Rect(0, -desc, dx, asc)
        m = self.tm * self.ctm
        # transform rect by affine matrix
        return r * m

    def _add_text_rect(self, r: fitz.Rect) -> None:
        if self.text_render_mode == 3:
            LOG.debug("Invisible text (Tr=3) skipped for highlight: %s", r)
            return
        visible = r.get_area() > 1e-6
        if self.mp_session and self.mp_session.saw_bt:
            self.mp_session.text_rects.append(r)
        for tag, bucket in self.mc_stack:
            if bucket is not None and tag == "TouchUp_TextEdit":
                bucket.rects.append(r)
        if not visible:
            LOG.debug("Near-zero text geometry: %s", r)

    def _advance_tm(self, dx_text_space: float, dy_text_space: float = 0.0) -> None:
        tr = fitz.Matrix(1, 0, 0, 1, dx_text_space, dy_text_space)
        self.tm = self.tm * tr

    def _show_string(self, s: bytes) -> None:
        frag = ""
        mp_idx: Optional[int] = None
        bucket_starts: List[Tuple[TouchUpBucket, int]] = []
        if self.text_render_mode != 3:
            frag = _decode_pdf_text_for_report(s, self.hex_cid_string)
            if self.mp_session and self.mp_session.saw_bt:
                mp_idx = len(self.mp_session.text_rects)
            for tag, bucket in self.mc_stack:
                if bucket is not None and tag == "TouchUp_TextEdit":
                    bucket_starts.append((bucket, len(bucket.rects)))
        codes = _decode_pdf_string(s, self.hex_cid_string)
        fm = self.font_metrics
        for code in codes:
            w = _glyph_width(fm, code, self.hex_cid_string)
            dx = (w / 1000.0) * self.font_size
            r = self._char_bbox(dx)
            self._add_text_rect(r)
            self._advance_tm(dx)
        if frag.strip() and self.text_render_mode != 3:
            if mp_idx is not None and self.mp_session:
                chunk = self.mp_session.text_rects[mp_idx:]
                self.mp_session.runs.append((frag, chunk))
            for bucket, start in bucket_starts:
                chunk = bucket.rects[start:]
                bucket.runs.append((frag, chunk))

    def _show_tj(self, arr: list) -> None:
        fs = self.font_size
        for item in arr:
            if isinstance(item, (int, float)):
                adj = float(item) / 1000.0 * fs
                self._advance_tm(adj, 0)
            elif isinstance(item, bytes):
                self._show_string(item)

    def _flush_mp_session(self, reason: str) -> None:
        sess = self.mp_session
        if sess is None:
            return
        text = sess.text_rects
        max_a = self._max_clip_area
        small_clips = (
            [r for r in sess.pre_bt_rects if max_a is None or r.get_area() <= max_a]
            if sess.pre_bt_rects
            else []
        )

        if text:
            u_all = _union_rects(text)
            page_a = (
                self.mediabox.get_area()
                if self.mediabox is not None
                else u_all.get_area()
            )
            band = max(5.0, 0.45 * max(sess.max_font_size, 8.0))
            runs = sess.runs
            full_txt = "".join(t for t, _ in runs).strip()
            if (
                self.mediabox is not None
                and page_a > 0
                and u_all.get_area() > MAX_TOUCHUP_TEXT_UNION_FRAC * page_a
            ):
                line_rects = _cluster_rects_by_baseline(text, band)
                for lr in line_rects:
                    u2 = lr & self.mediabox
                    if u2.is_empty or u2.get_area() < 1e-6:
                        continue
                    line_txt = _text_for_highlight_rect(runs, u2)
                    self.emit_touchup(
                        u2,
                        f"TouchUp_TextEdit MP linha ({reason})",
                        line_txt,
                    )
            else:
                u = u_all & self.mediabox if self.mediabox is not None else u_all
                if u.is_empty or u.get_area() < 1e-6:
                    LOG.warning("TouchUp_TextEdit MP: união de texto vazia após crop")
                    self.mp_session = None
                    return
                self.emit_touchup(u, f"TouchUp_TextEdit MP ({reason})", full_txt)
            self.mp_session = None
            return

        if small_clips:
            u = _union_rects(small_clips)
            if self.mediabox is not None:
                u &= self.mediabox
            if u.is_empty or u.get_area() < 1e-6:
                LOG.warning("TouchUp_TextEdit MP: clips pequenos somam vazio após crop")
                self.mp_session = None
                return
            LOG.debug(
                "TouchUp MP: só clips pequenos (sem texto visível); áreas=%s",
                [round(r.get_area(), 1) for r in small_clips[:5]],
            )
            self.emit_touchup(u, f"TouchUp_TextEdit MP clip ({reason})", "")
            self.mp_session = None
            return

        if sess.pre_bt_rects:
            LOG.warning(
                "TouchUp_TextEdit MP: só clip(s) grande(s) ignorado(s) e sem texto "
                "(%s); pre_bt=%s text=%s",
                reason,
                len(sess.pre_bt_rects),
                len(sess.text_rects),
            )
        else:
            LOG.warning(
                "TouchUp_TextEdit MP sem geometria útil (%s); pre_bt=%s text=%s",
                reason,
                len(sess.pre_bt_rects),
                len(sess.text_rects),
            )
        self.mp_session = None

    def _handle_operator(self, op: bytes) -> None:
        stack = self.operand_stack
        op = op.strip()

        if op == b"q":
            self.ctm_stack.append(self.ctm)
            stack.clear()
            return
        if op == b"Q":
            if len(self.ctm_stack) > 1:
                self.ctm_stack.pop()
            stack.clear()
            return
        if op == b"cm" and len(stack) >= 6:
            a, b, c, d, e, f = (float(stack[-6]), float(stack[-5]), float(stack[-4]), float(stack[-3]), float(stack[-2]), float(stack[-1]))
            m = fitz.Matrix(a, b, c, d, e, f)
            self.ctm_stack[-1] = self.ctm * m
            stack.clear()
            return

        if op == b"re" and len(stack) >= 4:
            x, y, w, h = (float(stack[-4]), float(stack[-3]), float(stack[-2]), float(stack[-1]))
            r = fitz.Rect(x, y, x + w, y + h)
            tr = self._transform_rect(r)
            if self.mp_session and not self.mp_session.saw_bt:
                if self._max_clip_area is None or tr.get_area() <= self._max_clip_area:
                    self.mp_session.pre_bt_rects.append(tr)
                else:
                    LOG.debug(
                        "Ignorado ``re`` de clipagem grande (%.0f pts²) em TouchUp MP",
                        tr.get_area(),
                    )
            stack.clear()
            return

        if op == b"BT":
            self.tm = fitz.Matrix(1, 0, 0, 1, 0, 0)
            self.tlm = fitz.Matrix(1, 0, 0, 1, 0, 0)
            if self.mp_session and not self.mp_session.saw_bt:
                self.mp_session.saw_bt = True
            stack.clear()
            return
        if op == b"ET":
            if self.mp_session and self.mp_session.saw_bt:
                self._flush_mp_session("ET")
            stack.clear()
            return

        if op == b"Tf" and len(stack) >= 2:
            self.font_size = float(stack[-1])
            if self.mp_session:
                self.mp_session.max_font_size = max(
                    self.mp_session.max_font_size, self.font_size
                )
            name_tok = stack[-2]
            if isinstance(name_tok, tuple) and name_tok[0] == "name":
                fname = name_tok[1]
                fxref = self.font_name_to_xref.get(fname)
                if fxref is not None:
                    if fxref not in self.font_metrics_cache:
                        self.font_metrics_cache[fxref] = _load_font_metrics(self.doc, fxref)
                    self.font_metrics = self.font_metrics_cache[fxref]
                    st = self.font_metrics.subtype
                    self.hex_cid_string = st in ("/Type0", "/CIDFontType0", "/CIDFontType2")
                else:
                    self.font_metrics = None
                    self.hex_cid_string = False
            stack.clear()
            return

        if op == b"Tr" and stack:
            self.text_render_mode = int(stack[-1])
            stack.clear()
            return

        if op == b"Tm" and len(stack) >= 6:
            a, b, c, d, e, f = (float(stack[-6]), float(stack[-5]), float(stack[-4]), float(stack[-3]), float(stack[-2]), float(stack[-1]))
            self.tm = fitz.Matrix(a, b, c, d, e, f)
            self.tlm = self.tm
            stack.clear()
            return

        if op == b"Td" and len(stack) >= 2:
            tx, ty = float(stack[-2]), float(stack[-1])
            self.tlm = self.tlm * fitz.Matrix(1, 0, 0, 1, tx, ty)
            self.tm = self.tlm
            stack.clear()
            return

        if op == b"TD" and len(stack) >= 2:
            tx, ty = float(stack[-2]), float(stack[-1])
            self.leading = -ty
            self.tlm = self.tlm * fitz.Matrix(1, 0, 0, 1, tx, ty)
            self.tm = self.tlm
            stack.clear()
            return

        if op == b"TL" and stack:
            self.leading = float(stack[-1])
            stack.clear()
            return

        if op == b"T*" and not stack:
            tl = self.leading if self.leading else self.font_size
            self.tlm = self.tlm * fitz.Matrix(1, 0, 0, 1, 0, -tl)
            self.tm = self.tlm
            stack.clear()
            return

        if op == b"Tj" and stack and isinstance(stack[-1], bytes):
            self._show_string(stack[-1])
            stack.clear()
            return

        if op == b"TJ" and stack:
            arg = stack[-1]
            if isinstance(arg, list):
                self._show_tj(arg)
            stack.clear()
            return

        if op == b"'" and len(stack) >= 1:
            tl = self.leading if self.leading else self.font_size
            self.tlm = self.tlm * fitz.Matrix(1, 0, 0, 1, 0, -tl)
            self.tm = self.tlm
            if isinstance(stack[-1], bytes):
                self._show_string(stack[-1])
            stack.clear()
            return

        if op == b'"' and len(stack) >= 3:
            aw, ac = float(stack[-3]), float(stack[-2])
            self.tlm = self.tlm * fitz.Matrix(1, 0, 0, 1, aw, ac)
            self.tm = self.tlm
            if isinstance(stack[-1], bytes):
                self._show_string(stack[-1])
            stack.clear()
            return

        # Marked content
        if op == b"BDC" and len(stack) >= 2:
            tag_tok, _props = stack[-2], stack[-1]
            tag = self._tag_name(tag_tok)
            bucket: Optional[TouchUpBucket] = (
                TouchUpBucket() if tag == "TouchUp_TextEdit" else None
            )
            self.mc_stack.append((tag or "", bucket))
            stack.clear()
            return

        if op == b"BMC" and stack:
            tag = self._tag_name(stack[-1])
            bucket = TouchUpBucket() if tag == "TouchUp_TextEdit" else None
            self.mc_stack.append((tag or "", bucket))
            stack.clear()
            return

        if op == b"EMC" and not stack:
            if not self.mc_stack:
                stack.clear()
                return
            tag, bucket = self.mc_stack.pop()
            if bucket is not None and tag == "TouchUp_TextEdit":
                if bucket.rects:
                    u = _union_rects(bucket.rects)
                    if self.mediabox is not None:
                        u &= self.mediabox
                    if u.get_area() < 1e-6:
                        LOG.warning(
                            "TouchUp_TextEdit BDC/BMC..EMC sem área após crop (tag=%r)",
                            tag,
                        )
                    else:
                        txt = _text_for_highlight_rect(bucket.runs, u)
                        if not txt:
                            txt = "".join(t for t, _ in bucket.runs).strip()
                        self.emit_touchup(u, "TouchUp_TextEdit BDC/BMC..EMC", txt)
                else:
                    LOG.warning(
                        "TouchUp_TextEdit BDC/BMC..EMC sem geometria (tag=%r)", tag
                    )
            stack.clear()
            return

        if op == b"MP" and stack:
            tag = self._tag_name(stack[-1])
            if tag == "TouchUp_TextEdit":
                if self.mp_session and not self.mp_session.saw_bt:
                    # Acrobat often emits duplicate /TouchUp_TextEdit MP before BT
                    pass
                else:
                    if self.mp_session and self.mp_session.saw_bt:
                        self._flush_mp_session("novo_MP")
                    self.mp_session = MPTouchSession()
            stack.clear()
            return

        if op == b"Do" and stack:
            name_tok = stack[-1]
            if isinstance(name_tok, tuple) and name_tok[0] == "name":
                self._invoke_xobject(name_tok[1])
            stack.clear()
            return

        # default: clear operands for unknown op
        stack.clear()

    @staticmethod
    def _tag_name(tok: Any) -> Optional[str]:
        if isinstance(tok, tuple) and tok[0] == "name":
            return tok[1]
        return None

    def _invoke_xobject(self, name: str) -> None:
        if self.xobject_depth >= _MAX_XOBJECT_DEPTH:
            return
        xref = self.xobject_map.get(name)
        if xref is None:
            return
        try:
            st = self.doc.xref_get_key(xref, "Subtype")
            if st[0] != "name" or st[1] != "/Form":
                return
        except Exception:
            return
        # Form matrix and resources
        form_matrix = fitz.Matrix(1, 0, 0, 1, 0, 0)
        try:
            mk = self.doc.xref_get_key(xref, "Matrix")
            if mk[0] == "array":
                arr = _parse_numeric_array_brackets(mk[1])
                if len(arr) == 6:
                    a, b, c, d, e, f = arr
                    form_matrix = fitz.Matrix(a, b, c, d, e, f)
        except Exception:
            pass
        res_xref = self.resources_xref
        try:
            rk = self.doc.xref_get_key(xref, "Resources")
            if rk[0] == "xref":
                rx = _parse_xref_ref(rk[1])
                if rx is not None:
                    res_xref = rx
        except Exception:
            pass

        fonts_parent = _build_font_name_to_xref(self.doc, self.resources_xref)
        fonts_child = _build_font_name_to_xref(self.doc, res_xref)
        fonts = _merge_name_maps(fonts_parent, fonts_child)
        xo_parent = _build_xobject_name_to_xref(self.doc, self.resources_xref)
        xo_child = _build_xobject_name_to_xref(self.doc, res_xref)
        xobjects = _merge_name_maps(xo_parent, xo_child)

        data = self.doc.xref_stream(xref)
        # PDF: save graphics, concat form matrix, run stream, restore
        self.ctm_stack.append(self.ctm)
        self.ctm_stack[-1] = self.ctm * form_matrix

        child = ContentInterpreter(
            self.doc,
            res_xref,
            self.font_metrics_cache,
            fonts,
            xobjects,
            self.emit_touchup,
            mediabox=self.mediabox,
            xobject_depth=self.xobject_depth + 1,
        )
        child.ctm_stack[-1] = self.ctm_stack[-1]
        child.tm = self.tm
        child.tlm = self.tlm
        child.font_size = self.font_size
        child.font_metrics = self.font_metrics
        child.hex_cid_string = self.hex_cid_string
        child.text_render_mode = self.text_render_mode
        child.leading = self.leading
        child.mc_stack = _clone_mc_stack(self.mc_stack)
        child.mp_session = self.mp_session

        child.run(data)

        self.ctm_stack.pop()
        self.mp_session = child.mp_session
        self.mc_stack = child.mc_stack

    def run(self, data: bytes) -> None:
        for tok, _pos in tokenize_content_stream(data):
            if isinstance(tok, bytes):
                if tok in PDF_OPERATORS or (
                    tok.startswith(b"T") and tok in (b"T*", b"Tj", b"TJ", b"Tc", b"Tw", b"Tz", b"Tr", b"Ts", b"Td", b"TD", b"Tm", b"Tf", b"TL")
                ):
                    self._handle_operator(tok)
                else:
                    # might be unknown operator
                    if re.fullmatch(rb"[A-Za-z0-9'*]+", tok):
                        self._handle_operator(tok)
                    else:
                        self.operand_stack.append(tok)
            elif isinstance(tok, tuple) and tok[0] == "name":
                self.operand_stack.append(tok)
            elif isinstance(tok, (int, float)):
                self.operand_stack.append(tok)
            elif isinstance(tok, (bytes, list)):
                self.operand_stack.append(tok)
            # dict from << >> rarely as operand alone before op - handled as part of BDC props

        # end of stream: flush dangling MP session
        if self.mp_session:
            self._flush_mp_session("fim_stream")


class PDFForensicScanner:
    """High-level API: find TouchUp_TextEdit regions and write highlighted PDF."""

    TAG = "TouchUp_TextEdit"

    def __init__(self, path: str):
        self.path = path
        self.doc = fitz.open(path)
        self._font_cache: Dict[int, FontMetrics] = {}
        self._touchup_report: List[Tuple[int, str, str, fitz.Rect]] = []

    def close(self) -> None:
        self.doc.close()

    def _page_resources_xref(self, page: fitz.Page) -> int:
        xr = resolve_page_resources_xref(self.doc, page.xref)
        if xr is not None:
            return xr
        raise ValueError("Página sem Resources xref válido")

    @staticmethod
    def _searchable_tokens(stream_hint: str, max_tokens: int = 14) -> List[str]:
        """Extrai palavras pesquisáveis para alinhar ao texto renderizado (MuPDF)."""
        if not stream_hint:
            return []
        hint = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", stream_hint)
        seen: set[str] = set()
        out: List[str] = []
        for raw in hint.replace("\n", " ").split():
            tok = raw.strip(".,;:()[]\"'«»")
            if len(tok) < 2:
                continue
            if not any(c.isalpha() for c in tok):
                continue
            if tok in seen:
                continue
            seen.add(tok)
            out.append(tok)
            if len(out) >= max_tokens:
                break
        return out

    def _refine_touchup_rect_and_text(
        self,
        page: fitz.Page,
        rough: fitz.Rect,
        stream_hint: str,
    ) -> Tuple[fitz.Rect, str]:
        """
        Corrige desvio entre geometria do content stream e o layout real do MuPDF:
        usa ``search_for`` numa janela ampla à volta do rect aproximado e devolve
        união dos hits mais próximos + ``get_text`` nessa união.
        """
        hint = (stream_hint or "").strip()
        rough_cx = (rough.x0 + rough.x1) * 0.5
        rough_cy = (rough.y0 + rough.y1) * 0.5
        clip_large = (rough + (-55, -140, 55, 200)) & page.rect
        hits: List[Tuple[float, fitz.Rect, str]] = []
        for tok in self._searchable_tokens(hint):
            try:
                found = page.search_for(tok, clip=clip_large)
            except Exception:  # noqa: BLE001
                continue
            for r in found:
                cy = (r.y0 + r.y1) * 0.5
                cx = (r.x0 + r.x1) * 0.5
                score = abs(cy - rough_cy) * 2.2 + abs(cx - rough_cx) * 0.12
                hits.append((score, r, tok))
        if not hits:
            mtxt = page.get_text("text", clip=rough).strip()
            if len(mtxt) >= 2:
                return rough, mtxt
            return rough, hint
        hits.sort(key=lambda h: h[0])
        if hits[0][0] > 88:
            u = rough
        else:
            best_sc = hits[0][0]
            anchor = hits[0][1]
            acy = (anchor.y0 + anchor.y1) * 0.5
            line_rects: List[fitz.Rect] = []
            for sc, r, _tok in hits:
                if sc > best_sc + 38:
                    break
                if abs((r.y0 + r.y1) * 0.5 - acy) > 12:
                    continue
                if r.x1 < rough.x0 - 140 or r.x0 > rough.x1 + 140:
                    continue
                line_rects.append(r)
            if not line_rects:
                line_rects = [anchor]
            u = line_rects[0]
            for r in line_rects[1:]:
                u |= r
            u = (u + (-1, -2, 1, 2)) & page.rect
            u_cy = (u.y0 + u.y1) * 0.5
            u_cx = (u.x0 + u.x1) * 0.5
            if abs(u_cy - rough_cy) > 48 or abs(u_cx - rough_cx) > 160:
                u = rough
            elif rough.get_area() > 1 and u.get_area() > max(
                rough.get_area() * 25, page.rect.get_area() * 0.35
            ):
                u = rough

        mtxt = page.get_text("text", clip=(u + (-0.5, -0.5, 0.5, 0.5)) & page.rect).strip()
        if len(mtxt) >= 2:
            return u, mtxt
        if hint:
            return u, hint
        return u, mtxt

    def find_marked_content_blocks(self, page: fitz.Page) -> List[Tuple[fitz.Rect, str, str]]:
        """Lista (rect_aproximado, tipo, texto_hint) por ocorrência TouchUp_TextEdit."""
        blocks: List[Tuple[fitz.Rect, str, str]] = []

        def emit_touchup(r: fitz.Rect, kind: str, text: str = "") -> None:
            blocks.append((r, kind, text))

        res_xref = self._page_resources_xref(page)
        fonts = _build_font_name_to_xref(self.doc, res_xref)
        xobjects = _build_xobject_name_to_xref(self.doc, res_xref)

        it = ContentInterpreter(
            self.doc,
            res_xref,
            self._font_cache,
            fonts,
            xobjects,
            emit_touchup,
            mediabox=page.rect,
        )
        for xref in page.get_contents():
            try:
                data = self.doc.xref_stream(xref)
            except Exception as ex:  # noqa: BLE001
                LOG.warning("Falha ao ler content stream xref %s: %s", xref, ex)
                continue
            it.operand_stack.clear()
            it.run(data)

        return blocks

    def run(self, out_path: Optional[str] = None) -> str:
        if out_path is None:
            stem = Path(self.path).stem
            parent = Path(self.path).parent
            out_path = str(parent / f"{stem}_FORENSIC_ANALYSIS.pdf")

        self._touchup_report.clear()

        for page in self.doc:
            pno = page.number + 1
            blocks = self.find_marked_content_blocks(page)
            for rough, kind, hint in blocks:
                snapped, final_txt = self._refine_touchup_rect_and_text(page, rough, hint)
                self._touchup_report.append((pno, kind, final_txt, snapped))
                LOG.info(
                    "Página %s: Encontrada edição manual nas coordenadas (%s, %s)",
                    pno,
                    round(snapped.x0, 2),
                    round(snapped.y0, 2),
                )
                ann = page.add_highlight_annot(snapped)
                ann.set_colors(stroke=(1, 1, 0))
                if hasattr(ann, "set_opacity"):
                    ann.set_opacity(0.5)
                ann.update()

        self.doc.save(
            out_path,
            incremental=False,
            garbage=4,
            deflate=True,
        )
        txt_path = self._write_forensic_touchup_txt()
        LOG.info("Relatório textual TouchUp: %s", txt_path)
        return out_path

    def _write_forensic_touchup_txt(self) -> str:
        """Escreve ``<stem>_FORENSIC_TOUCHUP.txt`` junto ao PDF de entrada."""
        src = Path(self.path)
        txt_path = src.parent / f"{src.stem}_FORENSIC_TOUCHUP.txt"
        lines: List[str] = [
            "Relatório textual — regiões /TouchUp_TextEdit (Adobe Acrobat)",
            f"Ficheiro analisado: {self.path}",
            f"Total de realces registados: {len(self._touchup_report)}",
            "",
            "Texto: lido com MuPDF sobre o retângulo do realce (o que está realmente por baixo",
            "do amarelo). O marcador TouchUp no stream pode agrupar fragmentos desenhados noutras",
            "zonas da página; nesse caso o texto do stream não coincide com o conteúdo visual.",
            "",
        ]
        for i, (pno, kind, text, rect) in enumerate(self._touchup_report, start=1):
            lines.append("-" * 72)
            lines.append(f"#{i} | Página {pno} | {kind}")
            lines.append(
                f"Rect (user space, pts): "
                f"x0={rect.x0:.2f} y0={rect.y0:.2f} x1={rect.x1:.2f} y1={rect.y1:.2f}"
            )
            body = text.strip() if text else ""
            if body:
                lines.append("Texto (MuPDF / refino de layout, quando possível):")
                lines.append(body)
            else:
                lines.append(
                    "(Sem texto associado neste realce — clip só, texto invisível Tr=3, "
                    "ou bloco apenas com espaços.)"
                )
            lines.append("")
        txt_path.write_text("\n".join(lines), encoding="utf-8")
        return str(txt_path)


def scan_pdf_for_touchups(
    input_path: str,
    out_pdf_path: str,
    out_txt_path: str,
) -> List[Tuple[int, str, str, fitz.Rect]]:
    """Convenience wrapper for PDFForensicScanner.

    Runs the scanner, saves highlighted PDF to *out_pdf_path*,
    saves TouchUp text report to *out_txt_path*, and returns
    the raw touchup report list.
    """
    scanner = PDFForensicScanner(input_path)
    try:
        scanner.run(out_pdf_path)
        # Move the auto-generated txt to the requested path
        src_txt = Path(input_path).parent / f"{Path(input_path).stem}_FORENSIC_TOUCHUP.txt"
        if src_txt.exists() and out_txt_path:
            Path(out_txt_path).write_text(src_txt.read_text(encoding="utf-8"), encoding="utf-8")
    finally:
        scanner.close()
    return scanner._touchup_report


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(message)s",
    )
    if len(sys.argv) > 1:
        path = sys.argv[1].strip()
    else:
        path = input("Caminho do PDF de entrada: ").strip().strip('"')
    if not path:
        print("Caminho vazio.", file=sys.stderr)
        sys.exit(1)
    scanner = PDFForensicScanner(path)
    try:
        out = scanner.run()
    finally:
        scanner.close()
    print("Gerado:", out)
    stem = Path(path).stem
    print(
        "Relatório TouchUp (texto):",
        str(Path(path).parent / f"{stem}_FORENSIC_TOUCHUP.txt"),
    )


if __name__ == "__main__":
    main()
