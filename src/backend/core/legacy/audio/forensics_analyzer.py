"""Analisador forense de audio: ENF, LTAS, niveis, DC local e comparacao espectral."""

import logging
import math

import librosa
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import signal
from scipy.io import wavfile
from scipy.signal import firwin, filtfilt, hilbert, welch, windows

from core.legacy.audio.spectrogram_decimate import (
    DEFAULT_MAX_FREQ_BINS,
    DEFAULT_MAX_TIME_BINS,
    decimate_spectrogram_max_pool,
)
from core.legacy.audio.spectrogram_scipy import compute_spectrogram_db, compute_spectrogram_db_from_audio

logger = logging.getLogger(__name__)

try:
    import ruptures as rpt  # noqa: F401
except Exception:
    rpt = None

def create_error_plot(message: str):
    """Cria um gráfico Plotly exibindo uma mensagem de erro."""
    fig = go.Figure()
    fig.add_annotation(
        x=0.5, y=0.5,
        text=message,
        showarrow=False,
        font=dict(size=16, color="red"),
        align="center"
    )
    fig.update_layout(
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        title="Erro na Análise",
        showlegend=False,
        width=800,
        height=400
    )
    return fig

class AudioForensicsAnalyzer:
    def __init__(self):
        logger.info("✅ AudioForensicsAnalyzer inicializado")


    def calculate_enf_deviation(self, audio_path: str, fnom: float, bwenf: float):
        try:
            L = 10000 
            Fs, sut = wavfile.read(audio_path)
            if sut.ndim > 1: sut = (sut[:, 0] + sut[:, 1]) / 2
            if np.issubdtype(sut.dtype, np.integer): sut = sut.astype(np.float64) / np.iinfo(sut.dtype).max

            fs = 20 * fnom
            escala = math.gcd(int(Fs), int(fs))
            sds = signal.resample(sut, int(len(sut) * (fs/escala) / (Fs/escala)))

            hBW = bwenf / 2
            filter_coeffs = firwin(L, [2*(fnom-hBW)/fs, 2*(fnom+hBW)/fs], pass_zero=False)
            padding_size = int(1.5 * L)
            sds_padded = np.concatenate([np.zeros(padding_size), sds, np.zeros(padding_size)])
            xn = filtfilt(filter_coeffs, 1, sds_padded)
            xn = xn - np.mean(xn)
            xa = hilbert(xn)
            xa = xa[padding_size:-padding_size]
            omegaHEE = np.angle(xa[1:] * np.conj(xa[:-1]))
            enf = fs * omegaHEE / (2 * np.pi)
            enf_deviation = enf - fnom
            time_axis = np.arange(len(enf)) / fs

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=time_axis,
                y=enf_deviation,
                mode='lines',
                name=f'Desvio de {fnom} Hz',
                line=dict(color='blue', width=1.5),
                hovertemplate='Tempo: %{x:.3f}s<br>Desvio: %{y:.3f}Hz<extra></extra>'
            ))
            fig.add_hline(y=0, line_dash="dash", line_color="red", 
                         annotation_text="Referência (0 Hz)", annotation_position="bottom right")
            
            fig.update_layout(
                title=f'Análise de Desvio ENF - {fnom} Hz',
                xaxis_title='Tempo (segundos)',
                yaxis_title='Desvio (Hz)',
                hovermode='x',
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                width=900,
                height=500
            )
            fig.update_xaxes(showgrid=True, gridcolor='lightgray')
            fig.update_yaxes(showgrid=True, gridcolor='lightgray')
            
            return fig

        except Exception as e:
            logger.error(f"Erro na análise ENF: {e}")
            return create_error_plot(f"Erro na Análise ENF:\n{e}")

    def analyze_quantization_levels(self, audio_path: str, bitdepth: int, canais: int):
        """
        Análise de níveis de quantização - equivalente à função niveis() do MATLAB
        """
        try:
            # Carregar áudio mantendo informação original de canais
            Fs, sut = wavfile.read(audio_path)
            
            # Converter para float se necessário, mantendo a escala original
            if np.issubdtype(sut.dtype, np.integer):
                sut = sut.astype(np.float64)
            else:
                # Se já é float, converter para a escala de inteiros
                sut = sut * (2**(bitdepth-1))
            
            info_messages = []
            
            # Determinar qual canal usar
            if sut.ndim == 1:
                # Áudio monaural
                canal = sut
                info_messages.append('Áudio monaural')
                dc_offset = np.mean(canal)
                info_messages.append(f'Desvio DC: {dc_offset:.2f}')
                
                # Calcular histograma
                bins = np.arange(-2**(bitdepth-1), 2**(bitdepth-1)+1)
                H, _ = np.histogram(canal, bins=bins)
                
                # Plotar com Plotly
                fig = go.Figure()
                bin_centers = bins[:-1]
                fig.add_trace(go.Scatter(
                    x=bin_centers,
                    y=H,
                    mode='lines',
                    name='Histograma',
                    line=dict(color='blue', width=2),
                    hovertemplate='Nível: %{x}<br>Ocorrências: %{y}<extra></extra>'
                ))
                
                info_text = '<br>'.join(info_messages)
                fig.add_annotation(
                    x=0.02, y=0.98,
                    xref='paper', yref='paper',
                    text=info_text,
                    showarrow=False,
                    align='left',
                    bgcolor='wheat',
                    bordercolor='black',
                    borderwidth=1
                )
                
                fig.update_layout(
                    title='Histograma das amostras de áudio - todas as amostras',
                    xaxis_title='Níveis de Quantização',
                    yaxis_title='Ocorrências',
                    showlegend=False,
                    width=900,
                    height=500
                )
                fig.update_xaxes(showgrid=True, gridcolor='lightgray')
                fig.update_yaxes(showgrid=True, gridcolor='lightgray')
                
                return fig
                
            else:
                # Áudio estéreo
                if canais > 0 and canais <= sut.shape[1]:
                    # Canal específico selecionado
                    canal = sut[:, canais-1]
                    dc_offset = np.mean(canal)
                    info_messages.append(f'Canal {canais} selecionado')
                    info_messages.append(f'Desvio DC: {dc_offset:.2f}')
                    
                    # Calcular histograma
                    bins = np.arange(-2**(bitdepth-1), 2**(bitdepth-1)+1)
                    H, _ = np.histogram(canal, bins=bins)
                    
                    # Plotar com Plotly
                    fig = go.Figure()
                    bin_centers = bins[:-1]
                    fig.add_trace(go.Scatter(
                        x=bin_centers,
                        y=H,
                        mode='lines',
                        name=f'Canal {canais}',
                        line=dict(color='blue', width=2),
                        hovertemplate='Nível: %{x}<br>Ocorrências: %{y}<extra></extra>'
                    ))
                    
                    info_text = '<br>'.join(info_messages)
                    fig.add_annotation(
                        x=0.02, y=0.98,
                        xref='paper', yref='paper',
                        text=info_text,
                        showarrow=False,
                        align='left',
                        bgcolor='wheat',
                        bordercolor='black',
                        borderwidth=1
                    )
                    
                    fig.update_layout(
                        title=f'Histograma das amostras de áudio - Canal {canais}',
                        xaxis_title='Níveis de Quantização',
                        yaxis_title='Ocorrências',
                        showlegend=False,
                        width=900,
                        height=500
                    )
                    fig.update_xaxes(showgrid=True, gridcolor='lightgray')
                    fig.update_yaxes(showgrid=True, gridcolor='lightgray')
                    
                    return fig
                else:
                    # Ambos os canais (canais = 0 ou inválido)
                    info_messages.append('Áudio estéreo')
                    dc_left = np.mean(sut[:, 0])
                    dc_right = np.mean(sut[:, 1])
                    info_messages.append(f'Desvio DC do canal esquerdo: {dc_left:.2f}')
                    info_messages.append(f'Desvio DC do canal direito: {dc_right:.2f}')
                    
                    # Calcular histogramas para ambos os canais
                    bins = np.arange(-2**(bitdepth-1), 2**(bitdepth-1)+1)
                    H_left, _ = np.histogram(sut[:, 0], bins=bins)
                    H_right, _ = np.histogram(sut[:, 1], bins=bins)
                    
                    # Plotar com subplots
                    fig = make_subplots(
                        rows=2, cols=1,
                        subplot_titles=('Canal Esquerdo', 'Canal Direito'),
                        vertical_spacing=0.15
                    )
                    
                    bin_centers = bins[:-1]
                    
                    fig.add_trace(
                        go.Scatter(
                            x=bin_centers, y=H_left,
                            mode='lines', name='Canal Esquerdo',
                            line=dict(color='blue', width=2),
                            hovertemplate='Nível: %{x}<br>Ocorrências: %{y}<extra></extra>'
                        ),
                        row=1, col=1
                    )
                    
                    fig.add_trace(
                        go.Scatter(
                            x=bin_centers, y=H_right,
                            mode='lines', name='Canal Direito',
                            line=dict(color='red', width=2),
                            hovertemplate='Nível: %{x}<br>Ocorrências: %{y}<extra></extra>'
                        ),
                        row=2, col=1
                    )
                    
                    fig.update_xaxes(title_text="Níveis de Quantização", showgrid=True, gridcolor='lightgray')
                    fig.update_yaxes(title_text="Ocorrências", showgrid=True, gridcolor='lightgray')
                    
                    info_text = '<br>'.join(info_messages)
                    fig.add_annotation(
                        x=0.02, y=0.98,
                        xref='paper', yref='paper',
                        text=info_text,
                        showarrow=False,
                        align='left',
                        bgcolor='wheat',
                        bordercolor='black',
                        borderwidth=1
                    )
                    
                    fig.update_layout(
                        title='Histograma das amostras de áudio - Ambos os Canais',
                        height=700,
                        width=900,
                        showlegend=True,
                        legend=dict(
                            orientation="h",
                            yanchor="bottom",
                            y=1.02,
                            xanchor="right",
                            x=1
                        )
                    )
                    
                    return fig

        except Exception as e:
            logger.error(f"Erro na análise de níveis de quantização: {e}")
            return create_error_plot(f"Erro na Análise de Níveis:\n{e}")

    def analyze_local_dc(self, audio_path: str, dur: float):
        """
        Análise de DC local - equivalente à função localdc() do MATLAB
        dur: duração da janela em segundos
        """
        try:
            # Carregar áudio mantendo informação original
            Fs, sut = wavfile.read(audio_path)
            
            # Converter para float se necessário
            if np.issubdtype(sut.dtype, np.integer):
                # Determinar bitdepth do arquivo original
                if sut.dtype == np.int16:
                    bitdepth = 16
                elif sut.dtype == np.int32:
                    bitdepth = 32
                elif sut.dtype == np.int8:
                    bitdepth = 8
                else:
                    bitdepth = 16  # default
                sut = sut.astype(np.float64) / (2**(bitdepth-1))
            else:
                bitdepth = 16  # Assumir 16-bit para arquivos float
            
            # Separar canais
            if sut.ndim == 1:
                canal1 = sut
                canal2 = None
                num_canais = 1
            else:
                canal1 = sut[:, 0]
                canal2 = sut[:, 1] if sut.shape[1] > 1 else None
                num_canais = sut.shape[1]
            
            # Calcular número de amostras por janela
            window_samples = int(Fs * dur)
            
            # Padding para completar a última janela - EXATAMENTE como no MATLAB
            padding_needed = int(np.ceil(len(canal1) / window_samples) * window_samples) - len(canal1)
            canal1 = np.concatenate([canal1, np.zeros(padding_needed)])
            
            if canal2 is not None:
                canal2 = np.concatenate([canal2, np.zeros(padding_needed)])
            
            # Reshape em janelas - EXATAMENTE como no MATLAB
            num_windows = len(canal1) // window_samples
            canal1_windowed = canal1[:num_windows * window_samples].reshape(num_windows, window_samples)
            
            if canal2 is not None:
                canal2_windowed = canal2[:num_windows * window_samples].reshape(num_windows, window_samples)
            
            # Calcular DC médio para cada janela
            dcmean = np.zeros((num_windows, 2 if num_canais > 1 else 1))
            
            for k in range(num_windows):
                # Canal 1
                aux = canal1_windowed[k, :]
                aux_filtered = aux[np.abs(aux) < 0.95]  # Filtro como no MATLAB
                if len(aux_filtered) > 0:
                    dcmean[k, 0] = np.mean(aux_filtered) * (2**(bitdepth-1))
                
                # Canal 2 (se existir)
                if canal2 is not None:
                    aux = canal2_windowed[k, :]
                    aux_filtered = aux[np.abs(aux) < 0.95]  # Filtro como no MATLAB
                    if len(aux_filtered) > 0:
                        dcmean[k, 1] = np.mean(aux_filtered) * (2**(bitdepth-1))
            
            # Eixo temporal - centro das janelas
            time_axis = (np.arange(num_windows) + 0.5) * dur
            
            # Plotar - seguindo EXATAMENTE a lógica do MATLAB
            if num_canais == 1:
                # Apenas um canal
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=time_axis,
                    y=dcmean[:, 0],
                    mode='lines',
                    name='Canal Único',
                    line=dict(color='red', width=2),
                    hovertemplate='Tempo: %{x:.2f}s<br>DC: %{y:.2f}<extra></extra>'
                ))
                
                fig.update_layout(
                    title='Nível DC - Análise Local',
                    xaxis_title='Segundos',
                    yaxis_title='Nível de Quantização',
                    showlegend=False,
                    width=900,
                    height=500
                )
                fig.update_xaxes(showgrid=True, gridcolor='lightgray')
                fig.update_yaxes(showgrid=True, gridcolor='lightgray')
                
                return fig
            else:
                # Dois canais - dois gráficos como no MATLAB
                fig = make_subplots(
                    rows=2, cols=1,
                    subplot_titles=('Todos os canais', 'Equivalente monaural'),
                    vertical_spacing=0.15
                )
                
                # Primeiro gráfico - ambos os canais
                fig.add_trace(
                    go.Scatter(
                        x=time_axis, y=dcmean[:, 0],
                        mode='lines', name='Canal esquerdo',
                        line=dict(color='red', width=2),
                        hovertemplate='Tempo: %{x:.2f}s<br>DC: %{y:.2f}<extra></extra>'
                    ),
                    row=1, col=1
                )
                
                fig.add_trace(
                    go.Scatter(
                        x=time_axis, y=dcmean[:, 1],
                        mode='lines', name='Canal direito',
                        line=dict(color='red', dash='dash', width=2),
                        hovertemplate='Tempo: %{x:.2f}s<br>DC: %{y:.2f}<extra></extra>'
                    ),
                    row=1, col=1
                )
                
                # Segundo gráfico - equivalente monaural
                mono_equivalent = (dcmean[:, 0] + dcmean[:, 1]) / 2
                fig.add_trace(
                    go.Scatter(
                        x=time_axis, y=mono_equivalent,
                        mode='lines', name='Monaural',
                        line=dict(color='red', width=2),
                        hovertemplate='Tempo: %{x:.2f}s<br>DC: %{y:.2f}<extra></extra>'
                    ),
                    row=2, col=1
                )
                
                fig.update_xaxes(title_text="Segundos", showgrid=True, gridcolor='lightgray')
                fig.update_yaxes(title_text="Nível de Quantização", showgrid=True, gridcolor='lightgray')
                
                fig.update_layout(
                    title='Nível DC - Análise Local',
                    height=700,
                    width=900,
                    showlegend=True,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    )
                )
                
                return fig

        except Exception as e:
            logger.error(f"Erro na análise de DC local: {e}")
            return create_error_plot(f"Erro na Análise DC Local:\n{e}")

    def analyze_spectrogram(
        self,
        audio_path: str,
        fft_points: int,
        window_type: str,
        window_size_percent: float,
        resample_rate: float = None,
        *,
        decimate_display: bool = False,
        max_plot_time_bins: int = DEFAULT_MAX_TIME_BINS,
        max_plot_freq_bins: int = DEFAULT_MAX_FREQ_BINS,
        progress_callback=None,
        _preloaded_audio=None,
        _preloaded_sr=None,
    ):
        """
        Espectrograma Plotly; decimacao opcional para exibicao rapida.
        """
        try:
            def _progress(pct: int, msg: str) -> None:
                if progress_callback is not None:
                    progress_callback(pct, msg)

            if _preloaded_audio is not None and _preloaded_sr is not None:
                magnitude_db, times, freqs, sr, n_fft, hop_length, stft_meta = (
                    compute_spectrogram_db_from_audio(
                        _preloaded_audio,
                        int(_preloaded_sr),
                        fft_points=fft_points,
                        window_type=window_type,
                        window_size_percent=window_size_percent,
                        progress=_progress,
                    )
                )
            else:
                magnitude_db, times, freqs, sr, n_fft, hop_length, stft_meta = compute_spectrogram_db(
                    audio_path,
                    fft_points=fft_points,
                    window_type=window_type,
                    window_size_percent=window_size_percent,
                    resample_rate=resample_rate,
                    progress=_progress,
                )
            window_length = int(n_fft * window_size_percent / 100.0)

            _progress(55, "Preparando visualizacao…")
            if decimate_display:
                z_plot, times_plot, freqs_plot, decimation_meta = decimate_spectrogram_max_pool(
                    magnitude_db,
                    times,
                    freqs,
                    max_time_bins=max_plot_time_bins,
                    max_freq_bins=max_plot_freq_bins,
                )
            else:
                z_plot = magnitude_db
                times_plot = times
                freqs_plot = freqs
                n_rows, n_cols = magnitude_db.shape
                decimation_meta = {
                    "decimated": False,
                    "full_shape": [int(n_rows), int(n_cols)],
                    "display_shape": [int(n_rows), int(n_cols)],
                    "row_pool_factor": 1,
                    "col_pool_factor": 1,
                    "max_time_bins": None,
                    "max_freq_bins": None,
                }

            # Criar espectrograma com Plotly
            fig = go.Figure(data=go.Heatmap(
                z=z_plot,
                x=times_plot,
                y=freqs_plot,
                colorscale='Electric',
                hovertemplate='Tempo: %{x:.3f}s<br>Freq: %{y:.1f}Hz<br>Magnitude: %{z:.1f}dB<extra></extra>',
                colorbar=dict(title="Magnitude (dB)")
            ))

            title_suffix = ""
            if decimation_meta.get("decimated"):
                fr, fc = decimation_meta["full_shape"]
                dr, dc = decimation_meta["display_shape"]
                title_suffix = f" [visualizacao decimada {fr}x{fc} → {dr}x{dc}]"

            fig.update_layout(
                title=f'Espectrograma - {window_type.title()} Window ({window_size_percent}%){title_suffix}',
                xaxis_title='Tempo (segundos)',
                yaxis_title='Frequência (Hz)',
                width=1000,
                height=600
            )

            fig.update_xaxes(showgrid=True, gridcolor='lightgray')
            fig.update_yaxes(showgrid=True, gridcolor='lightgray')

            info_text = f"FFT: {n_fft} pontos | Janela: {window_type} ({window_length} amostras) | SR: {sr} Hz"
            if decimation_meta.get("decimated"):
                info_text += (
                    f" | Plot: max-pool {decimation_meta['col_pool_factor']}x"
                    f"{decimation_meta['row_pool_factor']}"
                )
            if stft_meta.get("hop_adjusted"):
                info_text += f" | Hop ajustado={stft_meta.get('hop_length_used', hop_length)}"
            fig.add_annotation(
                x=0.02, y=0.98,
                xref='paper', yref='paper',
                text=info_text,
                showarrow=False,
                align='left',
                bgcolor='rgba(255,255,255,0.8)',
                bordercolor='black',
                borderwidth=1
            )

            return {
                "figure": fig,
                "times": times,
                "frequencies": freqs,
                "magnitude_db": magnitude_db,
                "magnitude_db_display": z_plot.astype(np.float32),
                "times_display": times_plot,
                "frequencies_display": freqs_plot,
                "sample_rate": int(sr),
                "n_fft": n_fft,
                "hop_length": hop_length,
                "stft_meta": stft_meta,
                "display_decimation": decimation_meta,
            }

        except Exception as e:
            logger.error(f"Erro na análise de espectrograma: {e}")
            return {
                "figure": create_error_plot(f"Erro no Espectrograma:\n{e}"),
                "error": str(e),
            }

    def analyze_ltas(self, audio_path: str, pts: int, canais: int, resample_rate: float = None):
        """
        Análise LTAS - equivalente à função LTAS() do MATLAB
        pts: número de pontos para pwelch
        canais: canal selecionado (0=monaural equivalente, 1=esquerdo, 2=direito)
        resample_rate: taxa de reamostragem opcional
        """
        try:
            # Carregar áudio com reamostragem opcional
            if resample_rate is not None:
                audio, Fs = librosa.load(audio_path, sr=resample_rate, mono=False)
                if audio.ndim == 1:
                    sut = audio
                else:
                    sut = audio.T  # Transpor para formato (samples, channels)
            else:
                Fs, sut = wavfile.read(audio_path)
            
            # Converter para float se necessário
            if np.issubdtype(sut.dtype, np.integer):
                sut = sut.astype(np.float64) / np.iinfo(sut.dtype).max
            
            # Selecionar canal conforme lógica do MATLAB
            if sut.ndim == 1:
                canal = sut
                canal_info = "Áudio monaural"
            elif canais > 0 and canais <= sut.shape[1]:
                canal = sut[:, canais-1]
                canal_info = f"Canal {canais}"
            else:
                # Equivalente monaural (como no MATLAB)
                if sut.shape[1] >= 2:
                    canal = sut[:, 0]/2 + sut[:, 1]/2
                else:
                    canal = sut[:, 0]
                canal_info = "Equivalente monaural"
            
            # Calcular PSD usando método de Welch - EXATAMENTE como no MATLAB
            ff, psd = welch(canal, fs=Fs, nperseg=pts, return_onesided=True, scaling='density')
            
            # Normalizar PSD - EXATAMENTE como no MATLAB: psd=psd/norm(psd)
            psd = psd / np.linalg.norm(psd)
            
            # PSD ordenado em ordem decrescente - como no MATLAB
            spsd = np.sort(psd)[::-1]
            
            # Calcular derivada do LTAS ordenado (diferencial entre amostras)
            spsd_derivative = np.diff(spsd)
            ff_derivative = ff[1:]  # Eixo de frequência para derivada (uma amostra a menos)
            
            # Gráfico 1: LTAS Normal
            psd_db = 10*np.log10(psd + 1e-10)
            fig_normal = go.Figure()
            fig_normal.add_trace(
                go.Scatter(
                    x=ff, y=psd_db,
                    mode='lines', name='LTAS Normal',
                    line=dict(color='blue', width=1.5),
                    hovertemplate='Freq: %{x:.1f}Hz<br>Mag: %{y:.1f}dB<extra></extra>'
                )
            )
            fig_normal.update_layout(
                title=f'LTAS Normal - Método de Welch - {canal_info}',
                xaxis_title='Frequência (Hz)',
                yaxis_title='Magnitude (dB)',
                autosize=True,
            )
            fig_normal.update_xaxes(showgrid=True, gridcolor='lightgray')
            fig_normal.update_yaxes(showgrid=True, gridcolor='lightgray')
            
            # Gráfico 2: LTAS com compensação 6dB/oitava
            ff_comp = np.where(ff > 0, ff, 1e-10)
            psd_compensated = psd_db + 20*np.log10(ff_comp)
            fig_6db = go.Figure()
            fig_6db.add_trace(
                go.Scatter(
                    x=ff, y=psd_compensated,
                    mode='lines', name='LTAS 6dB/oitava',
                    line=dict(color='orange', width=1.5),
                    hovertemplate='Freq: %{x:.1f}Hz<br>Mag: %{y:.1f}dB<extra></extra>'
                )
            )
            fig_6db.update_layout(
                title=f'LTAS 6dB/oitava - Método de Welch - {canal_info}',
                xaxis_title='Frequência (Hz)',
                yaxis_title='Magnitude (dB)',
                autosize=True,
            )
            fig_6db.update_xaxes(showgrid=True, gridcolor='lightgray')
            fig_6db.update_yaxes(showgrid=True, gridcolor='lightgray')
            
            # Gráfico 3: LTAS Ordenado
            spsd_db = 10*np.log10(spsd + 1e-10)
            fig_sorted = go.Figure()
            fig_sorted.add_trace(
                go.Scatter(
                    x=ff, y=spsd_db,
                    mode='lines', name='LTAS Ordenado',
                    line=dict(color='green', width=1.5),
                    hovertemplate='Freq: %{x:.1f}Hz<br>Mag: %{y:.1f}dB<extra></extra>'
                )
            )
            fig_sorted.update_layout(
                title=f'LTAS Ordenado - Método de Welch - {canal_info}',
                xaxis_title='Frequência (Hz)',
                yaxis_title='Magnitude (dB)',
                autosize=True,
            )
            fig_sorted.update_xaxes(showgrid=True, gridcolor='lightgray')
            fig_sorted.update_yaxes(showgrid=True, gridcolor='lightgray')
            
            # Gráfico 4: Derivada do LTAS Ordenado
            # Calcular derivada do LTAS ordenado em dB (diferencial entre amostras)
            spsd_derivative = np.diff(spsd_db)
            ff_derivative = ff[1:]  # Eixo de frequência para derivada (uma amostra a menos)
            fig_derivative = go.Figure()
            fig_derivative.add_trace(
                go.Scatter(
                    x=ff_derivative, y=spsd_derivative,
                    mode='lines', name='Derivada LTAS Ordenado',
                    line=dict(color='red', width=1.5),
                    hovertemplate='Freq: %{x:.1f}Hz<br>Derivada: %{y:.6f}<extra></extra>'
                )
            )
            fig_derivative.update_layout(
                title=f'Derivada LTAS Ordenado - {canal_info}',
                xaxis_title='Frequência (Hz)',
                yaxis_title='Diferencial (dPSD/df)',
                autosize=True,
            )
            fig_derivative.update_xaxes(showgrid=True, gridcolor='lightgray')
            fig_derivative.update_yaxes(showgrid=True, gridcolor='lightgray')
            
            return fig_normal, fig_6db, fig_sorted, fig_derivative

        except Exception as e:
            logger.error(f"Erro na análise LTAS: {e}")
            error_plot = create_error_plot(f"Erro na Análise LTAS:\n{e}")
            return error_plot, error_plot, error_plot, error_plot

