"""One-off: build forensics_analyzer.py from notebook extract."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / "_extract_analyzer.py").read_text(encoding="utf-8")
start = src.index("def create_error_plot")
end = src.index("# ==============================================================================\n# SEÇÃO 3:")
body = src[start:end]
header = '''"""Analisador forense de audio — portado de interface_gradio_Paulo.ipynb."""

import logging
import math

import librosa
import numpy as np
import plotly.graph_objects as go
from scipy import signal
from scipy.io import wavfile
from scipy.signal import firwin, filtfilt, hilbert, welch, windows

logger = logging.getLogger(__name__)

try:
    import ruptures as rpt  # noqa: F401
except Exception:
    rpt = None

'''
body = (
    body.replace("import gradio as gr\n", "")
    .replace("import matplotlib.pyplot as plt\n", "")
    .replace("import matplotlib.ticker as mticker\n", "")
    .replace("from PIL import Image # Importado para conversão de imagem\n", "")
    .replace("import io # Importado para conversão de imagem\n", "")
    .replace("from scipy.optimize import minimize\n", "")
)
out_path = ROOT / "src/backend/core/legacy/audio/forensics_analyzer.py"
out_path.write_text(header + body, encoding="utf-8")
print(f"Wrote {out_path} ({len(header + body)} bytes)")
