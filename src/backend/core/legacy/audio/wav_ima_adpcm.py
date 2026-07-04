# -*- coding: utf-8 -*-
"""Extracted from Análise de Consistência Indice WAV IMA ADPCM.ipynb"""

# --- Cell 0 ---
import numpy as np
import matplotlib.pyplot as plt
import struct
from tqdm.auto import tqdm
import pandas as pd
from datetime import datetime

# --- Cell 1 ---
def read_wave_ima_adpcm(filename):
    """
    Lê arquivo WAV com codificação IMA ADPCM e extrai todos os parâmetros
    """
    print("Lendo arquivo WAV...")
    with open(filename, 'rb') as f:
        # Lê header RIFF
        riff = f.read(4)
        if riff != b'RIFF':
            raise ValueError("Não é um arquivo RIFF válido")
        
        file_size = struct.unpack('<I', f.read(4))[0]
        wave = f.read(4)
        if wave != b'WAVE':
            raise ValueError("Não é um arquivo WAVE válido")
        
        fmt_found = False
        data_found = False
        
        while True:
            chunk_id = f.read(4)
            if len(chunk_id) < 4:
                break
                
            chunk_size = struct.unpack('<I', f.read(4))[0]
            
            if chunk_id == b'fmt ':
                fmt_found = True
                fmt_start = f.tell()
                
                audio_format = struct.unpack('<H', f.read(2))[0]
                num_channels = struct.unpack('<H', f.read(2))[0]
                sample_rate = struct.unpack('<I', f.read(4))[0]
                byte_rate = struct.unpack('<I', f.read(4))[0]
                block_align = struct.unpack('<H', f.read(2))[0]
                bits_per_sample = struct.unpack('<H', f.read(2))[0]
                
                if audio_format != 0x0011:
                    raise ValueError(f"Formato não é IMA ADPCM (código: {audio_format:#x})")
                
                extra_size = struct.unpack('<H', f.read(2))[0]
                samples_per_block = struct.unpack('<H', f.read(2))[0]
                
                print(f"=== Informações do WAV ===")
                print(f"Formato: IMA ADPCM (0x{audio_format:04x})")
                print(f"Canais: {num_channels}")
                print(f"Sample Rate: {sample_rate} Hz")
                print(f"Block Align: {block_align} bytes")
                print(f"Bits per Sample: {bits_per_sample}")
                print(f"Samples per Block: {samples_per_block}")
                print()
                
                f.seek(fmt_start + chunk_size)
                
            elif chunk_id == b'fact':
                num_samples = struct.unpack('<I', f.read(4))[0]
                print(f"Total de samples: {num_samples}")
                if chunk_size > 4:
                    f.read(chunk_size - 4)
                    
            elif chunk_id == b'data':
                data_found = True
                data_size = chunk_size
                
                print(f"Data chunk size: {data_size} bytes")
                print()
                
                audio_data = f.read(data_size)
                break
            else:
                f.seek(chunk_size, 1)
        
        if not fmt_found or not data_found:
            raise ValueError("Chunks necessários não encontrados")
        
        return {
            'num_channels': num_channels,
            'sample_rate': sample_rate,
            'block_align': block_align,
            'samples_per_block': samples_per_block,
            'bits_per_sample': bits_per_sample,
            'audio_data': audio_data,
            'data_size': data_size
        }

# --- Cell 2 ---
def extract_nibbles_matlab_style(audio_data):
    """
    Extrai nibbles exatamente como o MATLAB faz com fread(...,'uint4','ieee-be')
    """
    print("Extraindo nibbles...")
    data_array = np.frombuffer(audio_data, dtype=np.uint8)
    
    nibbles = np.empty(len(data_array) * 2, dtype=np.uint8)
    
    # MATLAB 'uint4' com 'ieee-be' lê nibble baixo primeiro, depois alto
    nibbles[0::2] = data_array & 0x0F      # nibble baixo
    nibbles[1::2] = (data_array >> 4) & 0x0F  # nibble alto
    
    return nibbles

# --- Cell 3 ---
def analyze_single_channel(c, L, ncanais, samples_per_block, sample_rate, channel):
    """
    Analisa um único canal e retorna resultados (VERSÃO CORRIGIDA PARA MONO/ESTÉREO)
    """
    # Tabelas IMA ADPCM
    IndexTab = np.array([-1, -1, -1, -1, 2, 4, 6, 8, -1, -1, -1, -1, 2, 4, 6, 8], dtype=np.int8)
    StepTab = np.array([
        7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45,
        50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173, 190, 209, 230,
        253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963,
        1060, 1166, 1282, 1411, 1552, 1707, 1878, 2066, 2272, 2499, 2749, 3024, 3327,
        3660, 4026, 4428, 4871, 5358, 5894, 6484, 7132, 7845, 8630, 9493, 10442, 11487,
        12635, 13899, 15289, 16818, 18500, 20350, 22385, 24623, 27086, 29794, 32767
    ], dtype=np.int16)
    
    # Parâmetros
    napcpb = samples_per_block
    nppcpb = ((napcpb - 1) // 8) + 1
    
    # Reshape 1: dados=reshape(c,8,L/8)
    dados = c.reshape(8, L // 8, order='F')
    
    # Seleciona canal
    a = dados[:, channel::ncanais]
    
    # O cálculo do número de colunas (L2[1]) usa 'ncanais' para ser dinâmico.
    num_colunas_reshape = a.shape[1] // (nppcpb * (8 // ncanais)) if ncanais > 0 else 0

    # Verificação de consistência para o reshape.
    if a.size != (8 * nppcpb) * num_colunas_reshape:
        # Lógica alternativa que usa o tamanho de 'a' diretamente.
        num_colunas_reshape = a.size // (8 * nppcpb)

    a = a.reshape(8 * nppcpb, num_colunas_reshape, order='F')
    
    L2 = a.shape
    
    # Inicialização
    indice = 0
    saida = np.zeros((6, L2[1]))
    armazenaindicesetep = np.zeros((2, napcpb * L // (ncanais * 8 * nppcpb)), dtype=np.int16) # ajustado para ncanais
    minimo = 0
    maximo = 0
    n = 0
    
    # Lista para armazenar detalhes das inconsistências
    inconsistencias_detalhadas = []
    
    # Loop principal
    for j in range(L2[1]):
        indiceinicio = 0
        
        for i in range(L2[0]):
            
            if i == 4 or i == 5:  # Lê o índice do header (ordem correta: LSB, MSB)
                if i == 4:
                    indiceinicio = indiceinicio + int(a[i, j])  # LSB
                else:
                    indiceinicio = int(a[i, j]) * 16 + indiceinicio  # MSB
                    
                    # Verifica inconsistência
                    if indice != indiceinicio:
                        minimo = 0
                        maximo = 0
                        
                        if n >= napcpb:
                            if np.min(armazenaindicesetep[0, n-napcpb:n]) == 0:
                                minimo = -1
                            if np.max(armazenaindicesetep[0, n-napcpb:n]) == 88:
                                maximo = 1
                        
                        saida[:, j] = [1, indice, indiceinicio, indice - indiceinicio, minimo, maximo]
                        
                        # Calcula o instante de tempo da inconsistência
                        sample_number = j * samples_per_block
                        tempo_segundos = sample_number / sample_rate
                        
                        # Formata tempo em HH:MM:SS.mmm
                        horas = int(tempo_segundos // 3600)
                        minutos = int((tempo_segundos % 3600) // 60)
                        segundos = tempo_segundos % 60
                        tempo_formatado = f"{horas:02d}:{minutos:02d}:{segundos:06.3f}"
                        
                        # Armazena detalhes
                        inconsistencias_detalhadas.append({
                            'bloco': j,
                            'sample': sample_number,
                            'tempo_segundos': tempo_segundos,
                            'tempo_formatado': tempo_formatado,
                            'indice_calculado': indice,
                            'indice_header': indiceinicio,
                            'diferenca': indice - indiceinicio,
                            'atingiu_minimo': minimo == -1,
                            'atingiu_maximo': maximo == 1
                        })
                    
                    # Atualiza o índice
                    indice = indiceinicio
                    
                    # Clipping
                    if indice > 88:
                        indice = 88
                    if indice < 0:
                        indice = 0
                    
                    # Armazena
                    if n < armazenaindicesetep.shape[1]:
                        armazenaindicesetep[0, n] = indice
                        armazenaindicesetep[1, n] = StepTab[indice]
                    n = n + 1
                    
            elif i > 7:  # Processa dados ADPCM
                SampxCode = int(a[i, j])
                indice = indice + IndexTab[SampxCode]
                
                # Clipping
                if indice > 88:
                    indice = 88
                if indice < 0:
                    indice = 0
                
                if n < armazenaindicesetep.shape[1]:
                    armazenaindicesetep[0, n] = indice
                    armazenaindicesetep[1, n] = StepTab[indice]
                n = n + 1
    
    return {
        'saida': saida,
        'indices': armazenaindicesetep[:, :n],
        'num_blocos': L2[1],
        'num_samples': n,
        'inconsistencias_detalhadas': inconsistencias_detalhadas
    }

# --- Cell 4 ---
def check_ima_adpcm_consistency_full(filename, analyze_all_channels=True, export_report=True):
    """
    Análise completa de consistência IMA ADPCM
    
    Parameters:
    -----------
    filename : str
        Nome do arquivo WAV
    analyze_all_channels : bool
        Se True, analisa todos os canais. Se False, apenas canal 0
    export_report : bool
        Se True, exporta relatório em CSV
    """
    
    # Lê arquivo WAV
    wav_info = read_wave_ima_adpcm(filename)
    
    ncanais = wav_info['num_channels']
    samples_per_block = wav_info['samples_per_block']
    sample_rate = wav_info['sample_rate']
    audio_data = wav_info['audio_data']
    
    # Extrai nibbles
    c = extract_nibbles_matlab_style(audio_data)
    L = len(c)
    
    print(f"=== Processamento ===")
    print(f"Total de nibbles: {L:,}")
    print(f"Número de canais: {ncanais}")
    print()
    
    # Analisa canais
    resultados_canais = {}
    
    if analyze_all_channels:
        canais_analisar = range(ncanais)
    else:
        canais_analisar = [0]
    
    for channel in canais_analisar:
        print(f"Processando Canal {channel}...")
        resultado = analyze_single_channel(c, L, ncanais, samples_per_block, sample_rate, channel)
        resultados_canais[channel] = resultado
    
    # Gera gráfico apenas das flags de inconsistência
    print("\nGerando visualização das inconsistências...")
    plot_inconsistency_flags(resultados_canais)
    
    # Gera relatório estatístico
    print("\nGerando relatório estatístico...")
    generate_statistics_report(resultados_canais, wav_info)
    
    # Exporta relatório detalhado
    if export_report:
        print("\nExportando relatório detalhado...")
        export_detailed_report(resultados_canais, wav_info, filename)
        
    return resultados_canais

if __name__ == "__main__":
    # Exemplo de uso local; substitua pelo caminho do arquivo de interesse.
    nome_do_arquivo = "exemplo.wav"
    try:
        resultados = check_ima_adpcm_consistency_full(
            nome_do_arquivo,
            analyze_all_channels=True,
            export_report=True,
        )
    except FileNotFoundError:
        print(f'\n[ERRO] Arquivo não encontrado: "{nome_do_arquivo}"\nVerifique o nome e o caminho do arquivo.')
    except ValueError as e:
        print(f'\n[ERRO] Ocorreu um problema ao ler o arquivo: {e}')

