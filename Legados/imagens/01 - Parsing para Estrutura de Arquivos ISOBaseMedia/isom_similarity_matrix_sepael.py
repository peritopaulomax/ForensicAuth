import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

def generate_similarity_matrix(all_comparisons, questioned_files, standard_files):
    matrix = np.zeros((len(questioned_files), len(standard_files)))
    for i, questioned in enumerate(questioned_files):
        for j, standard in enumerate(standard_files):
            if questioned in all_comparisons and standard in all_comparisons[questioned]:
                matrix[i, j] = all_comparisons[questioned][standard][0]
    return matrix

def plot_similarity_matrix(matrix, questioned_files, standard_files,cmap):
   

    # Configurar o tamanho da figura para se ajustar à tela
    plt.figure(figsize=(12, 8))

    # Criar o heatmap
    plt.imshow(matrix, cmap=cmap, aspect='auto', vmin=0.5, vmax=1)

    # Adicionar uma barra de cores
    plt.colorbar(label='Similaridade')

    # Configurar os rótulos dos eixos
    plt.xticks(range(len(standard_files)), standard_files, rotation=90)
    plt.yticks(range(len(questioned_files)), questioned_files)

    plt.xlabel('Arquivos Padrão')
    plt.ylabel('Arquivos Questionados')
    plt.title('Matriz de Similaridade')

    # Ajustar o layout
    plt.tight_layout()

    # Mostrar a imagem
    plt.show()

def create_and_plot_similarity_matrix(all_comparisons, questioned_structures, standard_structures, cmap):
    questioned_files = list(questioned_structures.keys())
    standard_files = list(standard_structures.keys())
    
    similarity_matrix = generate_similarity_matrix(all_comparisons, questioned_files, standard_files)
    plot_similarity_matrix(similarity_matrix, questioned_files, standard_files, cmap)
    
    return similarity_matrix