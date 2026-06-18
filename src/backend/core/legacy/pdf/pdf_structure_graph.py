"""Parser e visualizacao de grafo PDF — portado de estrutura_pdf_metricas.ipynb."""

from __future__ import annotations

import os
import re
import shutil
import sys
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import networkx as nx
from pypdf import PdfReader
from pypdf.generic import DictionaryObject, IndirectObject, StreamObject

DOT_LAYOUT_ARGS = "-Grankdir=TB -Gnodesep=150 -Granksep=150"

try:
    from networkx.drawing.nx_agraph import graphviz_layout as _agraph_layout
except ImportError:
    _agraph_layout = None  # type: ignore

try:
    from networkx.drawing.nx_pydot import graphviz_layout as _pydot_layout
except ImportError:
    _pydot_layout = None  # type: ignore

try:
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfparser import PDFParser
    from pdfminer.pdftypes import resolve1
except ImportError:
    PDFDocument = None  # type: ignore

MAX_DEPTH = 1000
PDFMINER_STREAM_LENGTH_LIMIT = 50_000
PDFMINER_MAX_DICT_ENTRIES = 80

PDFMINER_CALLS = 0
PDFMINER_ACCUM = 0.0
OBJ_VISITED = 0
LARGE_STREAM_COUNT = 0


def reset_profiling_metrics() -> None:
    global PDFMINER_CALLS, PDFMINER_ACCUM, OBJ_VISITED, LARGE_STREAM_COUNT
    PDFMINER_CALLS = 0
    PDFMINER_ACCUM = 0.0
    OBJ_VISITED = 0
    LARGE_STREAM_COUNT = 0


def find_key(obj: Any, ref_num: int, key: Any) -> Any:
    if isinstance(obj, DictionaryObject):
        for k, v in obj.items():
            if isinstance(v, IndirectObject) and v.idnum == ref_num:
                key = k
            elif isinstance(v, DictionaryObject):
                key = find_key(v, ref_num, key)
    return key


def should_use_pdfminer(obj: Any) -> bool:
    if not isinstance(obj, DictionaryObject):
        return False
    if isinstance(obj, StreamObject):
        length_value = obj.get("/Length")
        if isinstance(length_value, IndirectObject):
            length_value = length_value.get_object()
        if isinstance(length_value, (int, float)) and length_value > PDFMINER_STREAM_LENGTH_LIMIT:
            return False
    if len(obj.keys()) > PDFMINER_MAX_DICT_ENTRIES:
        return False
    return True


def extract_indirect_object_content(pdfminer_document: Any, cache: dict, obj_num: int) -> Any:
    global LARGE_STREAM_COUNT
    if pdfminer_document is None:
        return None
    if obj_num in cache:
        return cache[obj_num]

    obj_ref = pdfminer_document.getobj(obj_num)
    resolved_obj = resolve1(obj_ref)

    if isinstance(resolved_obj, StreamObject):
        length_value = resolved_obj.get("/Length")
        if isinstance(length_value, IndirectObject):
            length_value = length_value.get_object()
        if isinstance(length_value, (int, float)) and length_value > PDFMINER_STREAM_LENGTH_LIMIT:
            LARGE_STREAM_COUNT += 1
            cache[obj_num] = None
            return None

    if isinstance(resolved_obj, bytes):
        content = resolved_obj.decode("latin1", errors="ignore")
    elif isinstance(resolved_obj, dict):
        content = {
            k: (v.decode("latin1") if isinstance(v, bytes) else v) for k, v in resolved_obj.items()
        }
    else:
        content = str(resolved_obj)

    cache[obj_num] = content
    return content


def process_references(
    obj: Any,
    parent_label: str,
    num_obj: int,
    graph: nx.DiGraph,
    reader: PdfReader,
    processed: Set[int],
    pdfminer_document: Any,
    pdfminer_cache: dict,
    depth: int = 0,
    force_third_level: bool = False,
) -> None:
    global OBJ_VISITED, PDFMINER_CALLS, PDFMINER_ACCUM, LARGE_STREAM_COUNT

    if depth > MAX_DEPTH:
        return

    if isinstance(obj, IndirectObject):
        obj = obj.get_object()

    obj_id = id(obj)
    if obj_id in processed:
        return
    processed.add(obj_id)

    OBJ_VISITED += 1

    content = obj.__repr__()
    references = re.findall(r"(IndirectObject)\((\d+), (\d+),", content)

    use_pdfminer = pdfminer_document is not None and num_obj != 0 and should_use_pdfminer(obj)

    if use_pdfminer and isinstance(obj, StreamObject):
        length_value = obj.get("/Length")
        if isinstance(length_value, IndirectObject):
            length_value = length_value.get_object()
        if isinstance(length_value, (int, float)) and length_value > PDFMINER_STREAM_LENGTH_LIMIT:
            LARGE_STREAM_COUNT += 1
            use_pdfminer = False

    if use_pdfminer:
        try:
            start_time = time.perf_counter()
            content_miner = extract_indirect_object_content(pdfminer_document, pdfminer_cache, num_obj)
            PDFMINER_CALLS += 1
            PDFMINER_ACCUM += time.perf_counter() - start_time
            if content_miner is not None:
                references_additional = re.findall(
                    r"([a-zA-Z]+)\': <PDFObjRef:(\d+)(>)", str(content_miner)
                )
                references.extend(references_additional)
        except Exception:
            pass

    for ref in references:
        ref_num = int(ref[1])
        child_label = f"obj_{ref_num}"
        try:
            obj_child = reader.get_object(ref_num)
            if isinstance(obj_child, DictionaryObject):
                child_type = obj_child.get("/Type", "void")
            else:
                child_type = "void"
        except Exception:
            child_type = "void"

        if child_type == "/StructTreeRoot":
            node_label = f"{ref_num}_{child_type}"
            if child_label not in graph:
                graph.add_node(child_label, label=node_label)
            graph.add_edge(parent_label, child_label, key="StructTreeRoot")
            continue

        node_label = f"{ref_num}_{child_type}"
        if child_label not in graph:
            graph.add_node(child_label, label=node_label)

        key = find_key(obj, ref_num, None)
        if key is None:
            key = ref[0]

        if force_third_level and depth == 1:
            intermediate_label = f"intermediate_{parent_label}"
            if intermediate_label not in graph:
                graph.add_node(intermediate_label, label=intermediate_label)
                graph.add_edge(parent_label, intermediate_label)
            graph.add_edge(intermediate_label, child_label, key=key)
        else:
            graph.add_edge(parent_label, child_label, key=key)

        next_force = force_third_level
        if isinstance(obj, DictionaryObject) and obj.get("/Type") == "/Pages":
            next_force = True

        process_references(
            IndirectObject(ref_num, 0, reader),
            child_label,
            ref_num,
            graph,
            reader,
            processed,
            pdfminer_document,
            pdfminer_cache,
            depth + 1,
            next_force,
        )


def parse_pdf_structure(file_path: str) -> nx.DiGraph:
    """Grafo estrutural de objetos PDF (nos e arestas tipadas)."""
    reset_profiling_metrics()

    pdfminer_document = None
    pdfminer_cache: dict = {}
    if PDFDocument is not None:
        try:
            pdf_bytes = Path(file_path).read_bytes()
            pdfminer_buffer = BytesIO(pdf_bytes)
            pdfminer_parser = PDFParser(pdfminer_buffer)
            pdfminer_document = PDFDocument(pdfminer_parser)
            if not getattr(pdfminer_document, "is_extractable", False):
                pdfminer_document = None
        except Exception:
            pdfminer_document = None

    with open(file_path, "rb") as file:
        reader = PdfReader(file)
        trailer = reader.trailer

        graph = nx.DiGraph()
        graph.add_node("trailer", label="trailer")
        processed: Set[int] = set()

        process_references(
            trailer,
            "trailer",
            0,
            graph,
            reader,
            processed,
            pdfminer_document,
            pdfminer_cache,
        )

    return graph


def _apply_dot_graph_attrs(graph: nx.DiGraph) -> None:
    """Atributos Graphviz para pydot (nx_pydot nao aceita args=)."""
    graph.graph["rankdir"] = "TB"
    graph.graph["nodesep"] = "150"
    graph.graph["ranksep"] = "150"


def _ensure_graphviz_on_path() -> None:
    """Inclui binarios Graphviz do conda no PATH (Windows: dot.exe em Library/bin)."""
    if shutil.which("dot"):
        return
    prefix = Path(sys.prefix)
    extra: list[Path] = []
    if sys.platform == "win32":
        extra.append(prefix / "Library" / "bin")
    extra.append(prefix / "bin")
    path_parts = [str(p) for p in extra if p.is_dir()]
    if not path_parts:
        return
    os.environ["PATH"] = os.pathsep.join(path_parts + [os.environ.get("PATH", "")])


def compute_graphviz_positions(graph: nx.DiGraph) -> Tuple[Dict[Any, Tuple[float, float]], str]:
    """Layout hierarquico Graphviz dot TB; sem fallback spring."""
    _ensure_graphviz_on_path()
    errors: list[str] = []

    if _agraph_layout is not None:
        try:
            pos = _agraph_layout(graph, prog="dot", args=DOT_LAYOUT_ARGS)
            return pos, "graphviz_dot_pygraphviz"
        except Exception as exc:
            errors.append(f"pygraphviz: {exc}")

    if _pydot_layout is not None:
        try:
            _apply_dot_graph_attrs(graph)
            pos = _pydot_layout(graph, prog="dot")
            return pos, "graphviz_dot_pydot"
        except Exception as exc:
            errors.append(f"pydot: {exc}")

    detail = "; ".join(errors) if errors else "nenhum backend (pygraphviz/pydot)"
    raise RuntimeError(
        "Layout Graphviz indisponivel para o grafo PDF. "
        "Instale o binario Graphviz e pydot ou pygraphviz no ambiente conda forensicauth. "
        f"Detalhes: {detail}"
    )


def _positions_for_pyvis(
    pos: Dict[Any, Tuple[float, float]], canvas: float = 900.0
) -> Dict[Any, Tuple[float, float]]:
    if not pos:
        return {}
    xs = [float(pos[n][0]) for n in pos]
    ys = [float(pos[n][1]) for n in pos]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    scaled: Dict[Any, Tuple[float, float]] = {}
    for node in pos:
        x = (float(pos[node][0]) - min_x) / span_x * canvas
        y = (float(pos[node][1]) - min_y) / span_y * canvas
        scaled[node] = (x, -y)
    return scaled


def render_graph_png(
    graph: nx.DiGraph,
    output_path: Path,
    pdf_label: str,
    pos: Optional[Dict[Any, Tuple[float, float]]] = None,
) -> None:
    """PNG com layout Graphviz dot TB (arvore hierarquica)."""
    if pos is None:
        pos, _ = compute_graphviz_positions(graph)
    plt.figure(figsize=(15, 12))

    node_labels = nx.get_node_attributes(graph, "label")
    edge_labels = nx.get_edge_attributes(graph, "key")
    nx.draw(
        graph,
        pos,
        labels=node_labels,
        with_labels=True,
        node_size=1600,
        node_color="lightblue",
        font_size=8,
        font_weight="bold",
        arrows=True,
        arrowstyle="-|>",
        arrowsize=16,
    )
    nx.draw_networkx_edge_labels(graph, pos, edge_labels=edge_labels, font_size=7)
    plt.title(f"Legenda: {pdf_label}", fontsize=16, fontweight="bold")
    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, format="PNG", bbox_inches="tight")
    plt.close()


def render_graph_html(
    graph: nx.DiGraph,
    output_path: Path,
    pos: Optional[Dict[Any, Tuple[float, float]]] = None,
) -> Optional[str]:
    """HTML PyVis com posicoes fixas do mesmo layout dot TB do PNG. None = sucesso."""
    try:
        from pyvis.network import Network
    except ImportError:
        return (
            "pyvis nao instalado no ambiente Python do backend. "
            "Execute: conda activate forensicauth && pip install pyvis"
        )

    try:
        if pos is None:
            pos, _ = compute_graphviz_positions(graph)
        pyvis_pos = _positions_for_pyvis(pos)

        net = Network(
            height="1200px",
            width="100%",
            notebook=False,
            cdn_resources="remote",
            directed=True,
            bgcolor="#ffffff",
            font_color="#1a1a2e",
        )

        for node, data in graph.nodes(data=True):
            label = str(data.get("label", node))
            title = f"<b>{node}</b><br>{label}"
            xy = pyvis_pos.get(node)
            if xy is not None:
                net.add_node(
                    str(node),
                    label=label,
                    title=title,
                    size=12,
                    x=float(xy[0]),
                    y=float(xy[1]),
                    physics=False,
                )
            else:
                net.add_node(str(node), label=label, title=title, size=12, physics=False)

        for source, target, data in graph.edges(data=True):
            key = str(data.get("key", ""))
            net.add_edge(
                str(source),
                str(target),
                title=key,
                label=key if len(key) < 24 else key[:21] + "…",
            )

        # show_buttons antes de set_options: set_options converte options em dict e
        # quebra o widget configure do PyVis se chamado depois.
        net.show_buttons(filter_=["physics", "interaction", "layout"])
        net.set_options(
            """
    {
      "physics": { "enabled": false },
      "configure": {
        "enabled": true,
        "filter": ["physics", "interaction", "layout"]
      },
      "interaction": {
        "navigationButtons": true,
        "keyboard": true,
        "hover": true,
        "dragNodes": true,
        "zoomView": true
      }
    }
    """
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        net.write_html(str(output_path), notebook=False, open_browser=False)
        return None
    except Exception as exc:
        return f"Falha ao gerar HTML PyVis: {exc}"


def analyze_pdf_structure(pdf_path: str, out_dir: Path) -> Dict[str, Any]:
    graph = parse_pdf_structure(pdf_path)
    pos, layout_engine = compute_graphviz_positions(graph)
    png_path = out_dir / "structure_graph.png"
    html_path = out_dir / "structure_graph.html"
    render_graph_png(graph, png_path, Path(pdf_path).name, pos=pos)
    html_error = render_graph_html(graph, html_path, pos=pos)
    return {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "objects_visited": OBJ_VISITED,
        "layout_engine": layout_engine,
        "structure_graph_image_path": str(png_path),
        "structure_graph_html_path": str(html_path) if html_error is None else None,
        "structure_graph_html_error": html_error,
    }
