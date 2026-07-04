import os
import shutil
import sys

import librosa
import torch


def _check_torchvision_matches_torch():
    """transformers importa torchvision; versão velha + torch novo → nms does not exist."""
    try:
        import torchvision  # noqa: F401
    except Exception as e:
        msg = str(e).lower()
        if "nms" in msg or "does not exist" in msg:
            print(
                "Erro: torchvision não combina com a versão do PyTorch instalada.\n"
                "Corrija com:\n"
                "  pip install --upgrade torchvision torchaudio\n"
                "Ou reinstale a tríade a partir de: https://pytorch.org/get-started/locally/\n",
                file=sys.stderr,
            )
            sys.exit(1)
        raise


_check_torchvision_matches_torch()
from transformers import pipeline

# Apenas estes .py fazem parte do modelo remoto (não copiar detector.py etc. para o cache HF)
_REMOTE_CODE_PY = (
    "backbone.py",
    "configuration_antispoofing.py",
    "conformer.py",
    "feature_extraction_antispoofing.py",
    "modeling_antispoofing.py",
    "pipeline_antispoofing.py",
)


def _torch_version_major_minor():
    ver = torch.__version__.split("+")[0].strip()
    parts = ver.split(".")
    try:
        major = int(parts[0])
    except (ValueError, IndexError):
        return 0, 0
    try:
        minor = int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        minor = 0
    return major, minor


def _torch_ge_2_6():
    major, minor = _torch_version_major_minor()
    return major > 2 or (major == 2 and minor >= 6)


def _local_snapshot_uses_only_pytorch_bin(model_dir: str) -> bool:
    if not os.path.isdir(model_dir):
        return False
    if not os.path.isfile(os.path.join(model_dir, "pytorch_model.bin")):
        return False
    return not any(name.endswith(".safetensors") for name in os.listdir(model_dir))


def _local_dir_has_safetensors(model_dir: str) -> bool:
    if not os.path.isdir(model_dir):
        return False
    return any(name.endswith(".safetensors") for name in os.listdir(model_dir))

# Origem do modelo (escolha explícita ou automática):
#   export DF_ARENA_MODEL="Speech-Arena-2025/DF_Arena_1B_V_1"   # Hub
#   export DF_ARENA_MODEL="/caminho/para/pasta_com_weights"    # pasta local
# Se não definir: usa a pasta deste script se existir pytorch_model.bin; senão o Hub.
HUB_MODEL_ID = "Speech-Arena-2025/DF_Arena_1B_V_1"
_model_dir = os.path.dirname(os.path.abspath(__file__))
_local_weights = os.path.join(_model_dir, "pytorch_model.bin")
if os.environ.get("DF_ARENA_MODEL"):
    model_path = os.environ["DF_ARENA_MODEL"].strip()
elif os.path.isfile(_local_weights):
    model_path = _model_dir
else:
    model_path = HUB_MODEL_ID


def _sync_trust_remote_code_cache(model_dir: str) -> None:
    """Copia todos os .py do snapshot local para o cache do HF.

    O transformers às vezes não copia módulos só importados em cadeia (ex.: conformer.py),
    e falha ao abrir .../transformers_modules/<nome>/conformer.py.
    """
    model_dir = os.path.abspath(model_dir)
    if not os.path.isdir(model_dir):
        return
    if not os.path.isfile(os.path.join(model_dir, "config.json")):
        return
    cache_name = os.path.basename(model_dir)
    dest = os.path.join(
        os.path.expanduser("~"),
        ".cache",
        "huggingface",
        "modules",
        "transformers_modules",
        cache_name,
    )
    os.makedirs(dest, exist_ok=True)
    for name in _REMOTE_CODE_PY:
        src = os.path.join(model_dir, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(dest, name))
    pycache = os.path.join(dest, "__pycache__")
    if os.path.isdir(pycache):
        shutil.rmtree(pycache, ignore_errors=True)


_resolved_model = os.path.abspath(os.path.expanduser(model_path))
if os.path.isdir(_resolved_model) and os.path.isfile(
    os.path.join(_resolved_model, "config.json")
):
    _sync_trust_remote_code_cache(_resolved_model)
    model_path = _resolved_model

if _local_snapshot_uses_only_pytorch_bin(model_path) and not _torch_ge_2_6():
    ma, mi = _torch_version_major_minor()
    print(
        f"Erro: nesta pasta só há pesos em pytorch_model.bin e o PyTorch atual é {ma}.{mi}.\n"
        "O transformers atual exige PyTorch >= 2.6 para carregar .bin (CVE-2025-32434),\n"
        "ou pesos em safetensors.\n\n"
        "Recomendado (menos disco, um comando):\n"
        "  pip install -r requirements.txt\n"
        "  (ou: pip install 'torch>=2.6' alinhado ao seu CUDA — ver pytorch.org)\n\n"
        "Alternativa (mantém PyTorch 2.5; +~4GB em model.safetensors):\n"
        "  pip install safetensors && python convert_pytorch_bin_to_safetensors.py\n\n"
        "Outra: carregar do Hub\n"
        "  export DF_ARENA_MODEL=Speech-Arena-2025/DF_Arena_1B_V_1\n",
        file=sys.stderr,
    )
    sys.exit(1)

print("Carregando o Detector Universal de 1 Bilhão de Parâmetros...")
print(f"  Origem: {model_path}")

_device_pref = os.environ.get("DF_ARENA_DEVICE", "cpu").strip().lower()
if _device_pref == "cuda" and torch.cuda.is_available():
    _device = 0
elif _device_pref == "cuda" and not torch.cuda.is_available():
    print("Aviso: DF_ARENA_DEVICE=cuda, mas CUDA não está disponível. Usando CPU.")
    _device = -1
else:
    _device = -1

_model_kwargs = {
    "dtype": torch.float32,
}
if _local_dir_has_safetensors(model_path):
    _model_kwargs["use_safetensors"] = True

# pipeline configurado para a arquitetura RAPTOR
# trust_remote_code=True carrega os scripts locais de modelagem
pipe = pipeline(
    "antispoofing",
    model=model_path,
    trust_remote_code=True,
    device=_device,
    model_kwargs=_model_kwargs,
)

def analisar_audio(arquivo_wav):
    if not os.path.exists(arquivo_wav):
        print(f"Erro: {arquivo_wav} não encontrado.")
        return None

    # O modelo exige taxa de amostragem de 16kHz
    audio, _ = librosa.load(arquivo_wav, sr=16000)
    audio = audio.astype("float32")
    
    # Realiza a predição universal
    result = pipe(audio)
    
    print(f"\n--- Relatório de Autenticidade ---")
    print(f"Arquivo: {os.path.basename(arquivo_wav)}")
    print(f"Resultado: {'SINTÉTICO (FAKE)' if result['label'] == 'spoof' else 'REAL (HUMANO)'}")
    print(f"Confiança: {result['score']:.4f}")
    return result


def analisar_pasta_audio(pasta_audio):
    if not os.path.isdir(pasta_audio):
        print(f"Erro: pasta não encontrada: {pasta_audio}")
        return

    extensoes_audio = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".wma"}
    arquivos_audio = sorted(
        [
            nome
            for nome in os.listdir(pasta_audio)
            if os.path.isfile(os.path.join(pasta_audio, nome))
            and os.path.splitext(nome)[1].lower() in extensoes_audio
        ]
    )

    if not arquivos_audio:
        print(f"Nenhum arquivo de áudio encontrado em: {pasta_audio}")
        return

    total_fake = 0
    total_real = 0
    total_erro = 0

    print(f"\nIniciando análise de {len(arquivos_audio)} arquivo(s) em: {pasta_audio}")
    for nome in arquivos_audio:
        caminho_audio = os.path.join(pasta_audio, nome)
        try:
            result = analisar_audio(caminho_audio)
            if result is None:
                total_erro += 1
                continue
            if result["label"] == "spoof":
                total_fake += 1
            else:
                total_real += 1
        except Exception as e:
            total_erro += 1
            print(f"\n--- Erro ao processar ---")
            print(f"Arquivo: {nome}")
            print(f"Motivo: {e}")

    print("\n=== Resumo Final ===")
    print(f"Total de arquivos: {len(arquivos_audio)}")
    print(f"REAL (HUMANO): {total_real}")
    print(f"SINTÉTICO (FAKE): {total_fake}")
    print(f"Erros: {total_erro}")

# Por padrão, analisa todos os áudios da pasta audio_analise_IA
analisar_pasta_audio("audio_analise_IA")