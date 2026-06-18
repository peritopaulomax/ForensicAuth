from isom_parser_sepael import parse_iso_base_media
import os
import networkx as nx
from collections import defaultdict

ISO_BASE_MEDIA_EXTENSIONS = {'.mp4', '.3gp', '.m4a', '.mov', '.heic', '.m4v', '.f4v', '.m4b', '.m4r', '.m4p'}

def is_iso_base_media_file(filename):
    return os.path.splitext(filename.lower())[1] in ISO_BASE_MEDIA_EXTENSIONS

def calculate_structural_similarity_and_differences(graph1, graph2):
    """
    Calcula a similaridade estrutural entre dois grafos e identifica as diferenças.
    """
    def get_node_features(graph):
        features = defaultdict(int)
        for node in graph.nodes():
            node_type = graph.nodes[node]['type']
            features[node_type] += 1
            for child in graph.successors(node):
                child_type = graph.nodes[child]['type']
                features[(node_type, child_type)] += 1
        return features

    features1 = get_node_features(graph1)
    features2 = get_node_features(graph2)

    all_features = set(features1.keys()) | set(features2.keys())
    common_features = 0
    total_features = 0
    differences = []

    for feature in all_features:
        count1 = features1.get(feature, 0)
        count2 = features2.get(feature, 0)
        common_features += min(count1, count2)
        total_features += max(count1, count2)
        
        if count1 != count2:
            if isinstance(feature, tuple):
                diff = f"Relação '{feature[0]}->{feature[1]}': {count1} vs {count2}"
            else:
                diff = f"Box '{feature}': {count1} vs {count2}"
            differences.append(diff)

    similarity = common_features / total_features if total_features > 0 else 0
    return similarity, differences

def compare_structures(standard_files_dir, questioned_files_dir, similarity_threshold=0.7):
    standard_structures = {}
    questioned_structures = {}
    exact_matches = defaultdict(list)
    partial_matches = defaultdict(list)
    all_comparisons = {}  # Novo dicionário para armazenar todas as comparações

    # Processando arquivos padrão
    for filename in os.listdir(standard_files_dir):
        if is_iso_base_media_file(filename):
            filepath = os.path.join(standard_files_dir, filename)
            try:
                graph = parse_iso_base_media(filepath)
                standard_structures[filename] = graph
            except Exception as e:
                print(f"Erro ao processar arquivo padrão {filename}: {str(e)}")

    # Processando arquivos questionados e comparando
    for filename in os.listdir(questioned_files_dir):
        if is_iso_base_media_file(filename):
            filepath = os.path.join(questioned_files_dir, filename)
            try:
                graph = parse_iso_base_media(filepath)
                questioned_structures[filename] = graph

                all_comparisons[filename] = {}  # Inicializa comparações para este arquivo

                # Comparando com os padrões
                similarities = []
                for std_filename, std_graph in standard_structures.items():
                    similarity, differences = calculate_structural_similarity_and_differences(graph, std_graph)
                    all_comparisons[filename][std_filename] = (similarity, differences)
                    
                    if similarity == 1.0:
                        exact_matches[filename].append(std_filename)
                    else:
                        similarities.append((std_filename, similarity, differences))

                # Ordenar as similaridades em ordem decrescente
                similarities.sort(key=lambda x: x[1], reverse=True)

                # Adicionar todas as correspondências com a maior similaridade
                if similarities and similarities[0][1] >= similarity_threshold:
                    max_similarity = similarities[0][1]
                    for std_filename, similarity, differences in similarities:
                        if similarity == max_similarity:
                            partial_matches[filename].append((std_filename, similarity, differences))
                        else:
                            break  # Parar quando encontrar uma similaridade menor

            except Exception as e:
                print(f"Erro ao processar arquivo questionado {filename}: {str(e)}")

    return exact_matches, partial_matches, standard_structures, questioned_structures, all_comparisons

def print_comparison_results(exact_matches, partial_matches, standard_structures, questioned_structures, verbose=True):
    print("Resultados da Comparação:")
    print("-------------------------")

    print("\nCorrespondências Exatas:")
    n_exatas=0
    for q_file, matching_standards in exact_matches.items():
        print(f"  Arquivo Questionado: {q_file}")
        print("    Corresponde exatamente aos seguintes padrões:")
        for std_file in matching_standards:
            print(f"      - {std_file}")
        n_exatas+=1

    print("\nCorrespondências Parciais:")
    n_parciais=0
    for q_file, matches in partial_matches.items():
        if q_file not in exact_matches:
            print(f"  Arquivo Questionado: {q_file}")
            for std_file, similarity, differences in matches:
                print(f"    Semelhante a: {std_file} (Similaridade: {similarity:.2f})")
                if verbose:
                    print("    Principais diferenças:")
                    for diff in differences[:5]:  # Limitando a 5 diferenças para manter a saída concisa
                        print(f"      - {diff}")
                    if len(differences) > 5:
                        print(f"      ... e mais {len(differences) - 5} diferença(s)")
            n_parciais+=1

    print("\nArquivos Questionados sem Correspondências:")
    n_void=0
    for q_file in questioned_structures:
        
        if q_file not in exact_matches and q_file not in partial_matches:
            print(f"  - {q_file}")
            n_void+=1
        

    print("\nPadrões não Utilizados:")
    used_standards = set(std for match_list in exact_matches.values() for std in match_list)
    used_standards.update(std for match_list in partial_matches.values() for std, _, _ in match_list)
    unused_standards = set(standard_structures.keys()) - used_standards
    for std_file in unused_standards:
        print(f"  - {std_file}")

    print("\nResumo:")
    print(f"  Total de arquivos padrão processados: {len(standard_structures)}")
    print(f"  Total de arquivos questionados processados: {n_exatas+n_parciais+n_void}")
    print(f"  Arquivos questionados com correspondência exata: {n_exatas}")
    print(f"  Arquivos questionados com correspondência parcial: {n_parciais}") 
    print(f"  Arquivos questionados sem correspondências: {n_void}")
    print(f"  Padrões não utilizados: {len(unused_standards)}")

def get_specific_comparison(all_comparisons, questioned_file, standard_file):
    """
    Retorna a similaridade e diferenças entre um arquivo questionado específico e um arquivo padrão específico.
    """
    if questioned_file in all_comparisons and standard_file in all_comparisons[questioned_file]:
        similarity, differences = all_comparisons[questioned_file][standard_file]
        return f"Similaridade entre '{questioned_file}' e '{standard_file}': {similarity:.2f}\nDiferenças:\n" + "\n".join(f"- {diff}" for diff in differences)
    else:
        return f"Comparação não encontrada entre '{questioned_file}' e '{standard_file}'."    
