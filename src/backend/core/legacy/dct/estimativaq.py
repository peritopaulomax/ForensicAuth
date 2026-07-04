"""Estimacao da matriz de quantizacao JPEG.

Imagens com compressao JPEG apresentam histogramas com coeficientes DCT
com artefatos periodicos, cujo periodo equivale ao fator de quantizacao.
"""
import numpy as np
from PIL import Image
from numpy.fft import fft, fftshift
from scipy.fftpack import dct
from scipy.signal import lfilter

def estimativaq(image_path):
 

    # Leitura da imagem
    Im = np.array(Image.open(image_path))

    # Conversão para tipo double
    Im = np.double(Im)

    # Informações de luminância
    I = (0.299 * Im[:, :, 0] + 0.587 * Im[:, :, 1] + 0.114 * Im[:, :, 2])

    # Ajuste da estrutura de grid de blocos
    I2 = I.copy()
    I2[:-4, :-4] = I[4:, 4:]
    I2[-4:, :] = I[:4, :]
    I2[:, -4:] = I[:, :4]

    ordem = np.array([
            [1,  2,  6,  7, 15, 16, 28, 29],
            [3,  5,  8, 14, 17, 27, 30, 43],
            [4,  9, 13, 18, 26, 31, 42, 44],
            [10, 12, 19, 25, 32, 41, 45, 54],
            [11, 20, 24, 33, 40, 46, 53, 55],
            [21, 23, 34, 39, 47, 52, 56, 61],
            [22, 35, 38, 48, 51, 57, 60, 62],
            [36, 37, 49, 50, 58, 59, 63, 64]
        ]) # Ajuste para índice 0 do Python

    # Inicializações
    linhas, colunas = I.shape
    blin = linhas // 8
    bcol = colunas // 8
    coef = np.zeros((8, 8, blin * bcol))
    coef2 = np.zeros((8, 8, blin * bcol))
    k = 0
    minimo = 1
    maximo = 64

    maximo = 64
    minimo = 1

    # Histogramas e suas transformadas
    His = np.zeros((maximo - minimo + 1, 1001))
    FHis = His.copy()
    His2 = His.copy()
    FHis2 = FHis.copy()
    HiP = np.zeros((100, 1001))
    FHiP = HiP.copy()
    df2 = np.zeros((maximo - minimo + 1, 999))

    # Inicializações de matriz de quantização e correlações
    MatrizQ = np.zeros((8, 8))       # matriz de quantização estimada
    Corl = -1 * np.ones((8, 8))      # correlações

    # Dados com distribuição uniforme
    padrao = np.round(255 * np.random.rand(100, 10000))
    padrao = np.round((padrao) / np.arange(1, 101).reshape(-1, 1)) * np.arange(1, 101).reshape(-1, 1)

    # Janela de integração
    windowSize = 10


    linhas, colunas = I.shape
    blin = linhas // 8
    bcol = colunas // 8
    coef = np.zeros((8, 8, blin * bcol))
    coef2 = np.zeros((8, 8, blin * bcol))
    k = 0

    # Cálculo dos coeficientes DCT da imagem original e da versão com estrutura de blocos alterada
    for i in range(0, linhas - 7, 8):
        for j in range(0, colunas - 7, 8):
            bloco = I[i:i+8, j:j+8] - 128
            coef[:, :, k] = np.round(dct(dct(bloco.T, norm='ortho').T, norm='ortho'))
            bloco2 = I2[i:i+8, j:j+8] - 128
            coef2[:, :, k] = np.round(dct(dct(bloco2.T, norm='ortho').T, norm='ortho'))
            k += 1

    HiP = np.zeros((100, 1001))
    FHiP = np.zeros_like(HiP)

    # Cálculo das transformadas FFT dos histogramas de coeficientes DCT com distribuição uniforme
    for w in range(100):
        # Histograma de padrao[w, :] com bins de 0 a 1000
        HiP[w, :] = np.histogram(padrao[w, :], bins=np.arange(1002))[0]
        HiP[w, :] = HiP[w, :] / np.sum(HiP[w, :])
        FHiP[w, :] = np.abs(fftshift(fft(HiP[w, :])))

    # Limpar variáveis temporárias
    del HiP
    del padrao
    k = 0  # Índice inicial para histograma
    for cont in range(minimo, maximo + 1):
        # Encontra as posições (i, j) em coef que correspondem ao cont na ordem
        i, j = np.argwhere(ordem == cont)[0]
        
        # Extrai os coeficientes DCT correspondentes
        dummy = coef[i, j, :].flatten()
        # Calcula o histograma e sua transformada FFT
        His[k, :] = np.histogram(dummy, bins=np.arange(-500, 502))[0]
        # His[k, :] = His[k, :] / np.sum(His[k, :])  # Normalização comentada como no MATLAB
        FHis[k, :] = np.abs(fftshift(fft(His[k, :])))

        dummy = coef2[i, j, :].flatten()
        # Calcula o histograma e sua transformada FFT
        His2[k, :] = np.histogram(dummy, bins=np.arange(-500, 502))[0]
        # His[k, :] = His[k, :] / np.sum(His[k, :])  # Normalização comentada como no MATLAB
        FHis2[k, :] = np.abs(fftshift(fft(His2[k, :])))

        FHis2 = (FHis - FHis2) ** 2

        df2[k, :] = -np.diff(FHis2[k, :], 2)
            
        # Aplicação de filtro
        df2[k, :] = lfilter(np.ones(windowSize)/windowSize, 1, df2[k, :])
        
        # Remoção de valores negativos
        df2[k, df2[k, :] < 0] = 0
        
        # Cálculo de daux
        daux = np.concatenate([df2[k, :489], df2[k, 511:]])
        daux = daux - np.mean(daux)

        for w in range(1, 101):
            # Cálculo de fxx
            fxx = -np.diff(FHiP[w-1, :], 2)
            fxx = lfilter(np.ones(windowSize)/windowSize, 1, fxx)
            fxx[fxx < 0] = 0
            
            # Ajuste de Faux
            Faux = np.concatenate([fxx[:489], fxx[511:]])
            Faux = Faux - np.mean(Faux)
            
            # Cálculo de aux
            aux = np.sum(Faux * daux) / (np.linalg.norm(daux) * np.linalg.norm(Faux))
            
            # Ajuste de Corl e MatrizQ
            if aux > Corl[i, j] and aux > 0.2:
                Corl[i, j] = aux
                MatrizQ[i, j] = w
        
        k+=1
    return MatrizQ