# Conteúdo para o arquivo: postprocessing.py

import numpy as np
import cv2 as cv

# Conteúdo para o arquivo: postprocessing.py

import numpy as np
import cv2 as cv
from numba import njit, prange

# Conteúdo para o arquivo: postprocessing.py

import numpy as np
import cv2 as cv
from numba import njit, prange

# Conteúdo para o arquivo: postprocessing.py

import numpy as np
import cv2 as cv
from numba import njit, prange

# Conteúdo para o arquivo: postprocessing.py

import numpy as np
import cv2 as cv
from numba import njit, prange
from scipy.ndimage import median_filter # --- NOVA IMPORTAÇÃO ---

# Conteúdo para o arquivo: postprocessing.py

import numpy as np
import cv2 as cv
from numba import njit, prange
from scipy.ndimage import median_filter

def get_circular_kernel(radius):
    """Cria um kernel (ou 'footprint') circular para vizinhanças."""
    y, x = np.ogrid[-radius:radius+1, -radius:radius+1]
    mask = x**2 + y**2 <= radius**2
    return np.where(mask, 1, 0)

# A função paralela agora recebe os arrays pré-calculados.
@njit(parallel=True)
def _calculate_dlf_error_parallel(field, radius, coords, S_pinv):
    """
    Calcula o erro de ajuste linear (DLF) para cada pixel de forma paralela.
    """
    m, n, _ = field.shape
    error_map = np.zeros((m, n), dtype=np.float64)
    
    # A matriz S é a mesma para todas as vizinhanças
    N = len(coords)
    S = np.ones((N, 3), dtype=np.float64)
    S[:, 1:] = coords

    for i in prange(radius, m - radius):
        for j in range(radius, n - radius):
            # Extrai os vetores de deslocamento na vizinhança usando os índices pré-calculados
            neighborhood_vx = np.zeros(N, dtype=np.float64)
            neighborhood_vy = np.zeros(N, dtype=np.float64)
            for k in range(N):
                y, x = coords[k]
                neighborhood_vx[k] = field[i + y, j + x, 0]
                neighborhood_vy[k] = field[i + y, j + x, 1]

            ax = S_pinv @ neighborhood_vx
            ay = S_pinv @ neighborhood_vy
            
            error_x = np.sum((neighborhood_vx - S @ ax)**2)
            error_y = np.sum((neighborhood_vy - S @ ay)**2)
            
            error_map[i, j] = error_x + error_y
            
    return error_map

def dlf_postprocess(vect_field, p_m=4, p_n=6, t_e_sq=300, t_s=1200, p_d=10):
    """
    Pipeline de post-processing completo baseado no artigo TIFS 2015.
    """
    m, n, _ = vect_field.shape
    
    # Passo 1: Filtro de Mediana
    k_size = int(2 * p_m + 1)
    if k_size % 2 == 0: k_size += 1
    if k_size < 3: k_size = 3
    
    field_filtered_x = median_filter(vect_field[..., 0], size=k_size)
    field_filtered_y = median_filter(vect_field[..., 1], size=k_size)
    field_filtered = np.stack((field_filtered_x, field_filtered_y), axis=-1).astype(np.float64)
    
    # --- LÓGICA CORRIGIDA ---
    # Pré-cálculo da vizinhança e da matriz S, FORA da função Numba.
    radius = p_n
    y, x = np.ogrid[-radius:radius+1, -radius:radius+1]
    mask = x**2 + y**2 <= radius**2
    coords = np.argwhere(mask) - radius # Coordenadas relativas da vizinhança
    
    N = len(coords)
    S = np.ones((N, 3), dtype=np.float64)
    S[:, 1:] = coords
    S_pinv = np.linalg.pinv(S) # Pseudo-inversa calculada uma vez

    # Passo 2: Cálculo do Erro de Ajuste Linear (DLF)
    error_map = _calculate_dlf_error_parallel(field_filtered, radius, coords, S_pinv)
    
    # Passo 3: Limiarização do Erro
    threshold = np.sqrt(t_e_sq)
    mask = error_map < threshold
    
    # Passo 5: Remoção de regiões pequenas (T_S)
    mask_uint8 = mask.astype(np.uint8)
    N, components = cv.connectedComponents(mask_uint8)
    final_mask = np.zeros_like(mask)
    if N > 1:
        for i in range(1, N):
            component_mask = (components == i)
            if np.sum(component_mask) > t_s:
                final_mask = np.logical_or(final_mask, component_mask)

    # Passo 6: Espelhamento das Regiões
    mirrored_mask = final_mask.copy()
    ys, xs = np.where(final_mask)
    for y, x in zip(ys, xs):
        di, dj = field_filtered[y, x].astype(int)
        y_dest, x_dest = y + di, x + dj
        if 0 <= y_dest < m and 0 <= x_dest < n:
            mirrored_mask[y_dest, x_dest] = True
    
    # Passo 7: Dilatação Morfológica
    kernel = get_circular_kernel(p_d)
    dilated_mask = cv.dilate(mirrored_mask.astype(np.uint8), kernel.astype(np.uint8)) > 0
    
    return dilated_mask
def gradn(im):
    """
    Compute the norm of the gradient of the image im of shape (m, n, 3). Returns an array of shape (m - 1, n - 1).
    """
    grad = np.sqrt(np.diff(im, axis=0)[:, :-1]**2 + np.diff(im, axis=1)[:-1, :]**2)
    return grad

def compute_mask_1(vect_field, m, n, p, min_region_size):
    """
    Compute the mask of the copy-moved area from the vect_field. Method 1.
    MODIFICADO para aceitar o tamanho mínimo da região (T_S do artigo).
    """
    r = p
    th = 0.5
    s = 2 * p

    #Compute the gradn of x and y displacement map
    vx = gradn(vect_field[..., 0])
    vy = gradn(vect_field[..., 1])

    #Compute a first mask
    mask_0 = np.zeros((m, n))
    u = (np.mean(vx) + np.mean(vy)) / 100
    mask_0[:-1, :-1] = 1 * (vy < u) * (vx < u)

    #Filter a big part of the noise
    kernel = np.ones((r, r))
    kernel = kernel / np.sum(kernel)
    mask_1 = cv.filter2D(mask_0, -1, kernel)
    mask_2 = 1 * (mask_1 > th)

    # --- LÓGICA DE FILTRAGEM MODIFICADA ---
    # Agora filtra por tamanho absoluto em pixels, como descrito no artigo de 2015.
    mask_3 = np.uint8((mask_2))
    N, component = cv.connectedComponents(mask_3)
    
    liste_component = []
    for i in range(1, N):
        # Mantém apenas componentes com área maior que o 'min_region_size'
        area = np.sum(1 * (component == i))
        if area > min_region_size:
            liste_component.append(i)
            
    mask_4 = np.zeros((m, n))
    for i in liste_component:
        mask_4 += 1 * (component == i)

    #dilatate the result to compensate the patch effect
    kernel = np.ones((s, s))
    mask = cv.dilate(mask_4, kernel) > 0
    return mask


def compute_mask_2(vect_field, m, n, p):
    """
    Compute the mask of the copy-moved area from the vect_field. Method 2.
    """
    # Compute end_points = start_points + displacement_vectors
    ii, jj = np.meshgrid(np.arange(m), np.arange(n), indexing="ij")
    ij = np.stack((ii, jj), axis=-1)
    end_points = ij + vect_field
    # Compose function f : start_points -> end_points with itself
    end_points2 = end_points[end_points[..., 0], end_points[..., 1]]
    # Compute the ground distances after this second application of f
    back_and_forth_distance = np.max(np.abs(end_points2 - ij), axis=-1)
    # mask := "coherent" points = points where back_and_forth_distance is 0
    mask = (back_and_forth_distance == 0).astype("uint8")
    # erode mask
    eroded_mask = cv.erode(mask, np.ones((2, 2)))
    # Select the 2 biggest connected components
    N, components = cv.connectedComponents(eroded_mask)
    bc = np.bincount(components.flatten())
    indices = np.argsort(bc)[::-1]
    biggest_components = ((components == indices[1]) + (components == indices[2])).astype("uint8")
    # Dilate mask
    final_mask = cv.dilate(biggest_components, np.ones((15, 15))) > 0
    return final_mask


def fscore(mask, gt):
    """Compute F-measure of computed mask vs ground truth."""
    tp = np.sum(mask * gt)
    fp = np.sum(mask * (gt < 1))
    fn = np.sum((mask < 1) * gt)
    
    return 2 * np.sum(tp) / (2 * np.sum(tp) + np.sum(fn) + np.sum(fp))