import struct
from typing import Dict, List, Tuple
import networkx as nx
import os
from collections import defaultdict

# Dicionário com descrições dos boxes conhecidos
BOX_DESCRIPTIONS = {
    'ftyp': 'File Type Box - Identifica o tipo e as especificações do arquivo',
    'moov': 'Movie Box - Contém todos os metadados do filme',
    'mvhd': 'Movie Header Box - Metadados gerais do filme',
    'trak': 'Track Box - Contém uma faixa de áudio ou vídeo',
    'tkhd': 'Track Header Box - Características gerais da faixa',
    'mdia': 'Media Box - Contém informações específicas da mídia da faixa',
    'mdhd': 'Media Header Box - Informações gerais sobre os dados de mídia',
    'hdlr': 'Handler Reference Box - Declara o tipo de mídia (áudio, vídeo, etc.)',
    'minf': 'Media Information Box - Características da mídia para reprodução',
    'stbl': 'Sample Table Box - Índices de tempo e dados para os quadros de mídia',
    'stsd': 'Sample Description Box - Informações de codificação para cada formato de amostra',
    'stts': 'Decoding Time to Sample Box - Mapeamento de tempo para amostras',
    'stss': 'Sync Sample Box - Tabela de amostras-chave (keyframes)',
    'ctts': 'Composition Time to Sample Box - Ajustes de tempo de composição',
    'stsc': 'Sample to Chunk Box - Mapeamento de amostras para chunks',
    'stsz': 'Sample Size Box - Tamanhos das amostras',
    'stco': 'Chunk Offset Box - Posições dos chunks no arquivo',
    'udta': 'User Data Box - Informações definidas pelo usuário',
    'meta': 'Metadata Box - Estrutura para incluir metadados',
    'dinf': 'Data Information Box - Informações sobre onde os dados de mídia podem ser encontrados',
    'edts': 'Edit Box - Define uma linha do tempo de edição para a faixa',
    'free': 'Free Space Box - Espaço não utilizado que pode ser aproveitado para inserções futuras',
    'mdat': 'Media Data Box - Contém os dados de mídia reais (áudio, vídeo)',
    'skip': 'Skip Box - Espaço reservado que pode ser ignorado',
    'wide': 'Wide Box - Espaço reservado para permitir que o box seguinte use tamanho de 64 bits',
    '©too': 'Tool Box - Informações sobre a ferramenta usada para criar o arquivo'
}

def read_box(file) -> Tuple[str, int, int]:
    start_pos = file.tell()
    size = struct.unpack('>I', file.read(4))[0]
    box_type_bytes = file.read(4)
    
    try:
        box_type = box_type_bytes.decode('ascii')
    except UnicodeDecodeError:
        box_type = box_type_bytes.decode('utf-8', errors='replace')
    
    if size == 1:
        size = struct.unpack('>Q', file.read(8))[0]
    elif size == 0:
        size = os.path.getsize(file.name) - start_pos
    
    return box_type, size, start_pos

def parse_full_box(file):
    version = struct.unpack('>B', file.read(1))[0]
    flags = struct.unpack('>3s', file.read(3))[0]
    return version, int.from_bytes(flags, byteorder='big')

def parse_mvhd(file):
    version, flags = parse_full_box(file)
    if version == 1:
        creation_time, modification_time = struct.unpack('>QQ', file.read(16))
        timescale, duration = struct.unpack('>IQ', file.read(12))
    else:
        creation_time, modification_time = struct.unpack('>II', file.read(8))
        timescale, duration = struct.unpack('>II', file.read(8))
    
    return {
        'version': version,
        'flags': flags,
        'creation_time': creation_time,
        'modification_time': modification_time,
        'timescale': timescale,
        'duration': duration
    }

def parse_tkhd(file):
    version, flags = parse_full_box(file)
    if version == 1:
        creation_time, modification_time, track_ID, _, duration = struct.unpack('>QQIIQ', file.read(32))
    else:
        creation_time, modification_time, track_ID, _, duration = struct.unpack('>IIIII', file.read(20))
    
    return {
        'version': version,
        'flags': flags,
        'creation_time': creation_time,
        'modification_time': modification_time,
        'track_ID': track_ID,
        'duration': duration
    }

def parse_mdhd(file):
    version, flags = parse_full_box(file)
    if version == 1:
        creation_time, modification_time, timescale, duration = struct.unpack('>QQII', file.read(28))
    else:
        creation_time, modification_time, timescale, duration = struct.unpack('>IIII', file.read(16))
    
    language = struct.unpack('>H', file.read(2))[0]
    lang = ''
    for i in range(3):
        lang += chr((language >> (2-i)*5 & 0x1f) + 0x60)
    
    return {
        'version': version,
        'flags': flags,
        'creation_time': creation_time,
        'modification_time': modification_time,
        'timescale': timescale,
        'duration': duration,
        'language': lang
    }

def parse_hdlr(file):
    _, flags = parse_full_box(file)
    pre_defined = struct.unpack('>I', file.read(4))[0]
    handler_type = file.read(4).decode('ascii')
    reserved = struct.unpack('>III', file.read(12))
    name_end = file.read().find(b'\x00')
    name = file.read(name_end).decode('utf-8')
    
    return {
        'flags': flags,
        'pre_defined': pre_defined,
        'handler_type': handler_type,
        'name': name
    }
def parse_box_content(file, box_type, size, end_pos):
    if box_type == 'mvhd':
        return parse_mvhd(file)
    elif box_type == 'tkhd':
        return parse_tkhd(file)
    elif box_type == 'mdhd':
        return parse_mdhd(file)
    elif box_type == 'hdlr':
        return parse_hdlr(file)
    elif box_type in ['moov', 'trak', 'edts', 'mdia', 'minf', 'stbl', 'dinf', 'udta','meta']:
        return parse_container_box(file, end_pos)
    else:
        return {'size': size, 'offset': file.tell()}

def parse_container_box(file, end_pos):
    content = []
    while file.tell() < end_pos:
        try:
            box_type, size, start_pos = read_box(file)
            box_end = start_pos + size
            box_content = parse_box_content(file, box_type, size, box_end)
            content.append({
                'type': box_type,
                'size': size,
                'offset': start_pos,
                'content': box_content
            })
            file.seek(box_end)
        except Exception as e:
            print(f"Erro ao processar box na posição {file.tell()}: {str(e)}")
            break
    return content

def parse_iso_base_media(filename: str) -> nx.DiGraph:
    G = nx.DiGraph()
    
    with open(filename, 'rb') as file:
        file_size = os.path.getsize(filename)
        while file.tell() < file_size:
            try:
                box_type, size, start_pos = read_box(file)
                end_pos = start_pos + size
                
                content = parse_box_content(file, box_type, size, end_pos)
                node_id = f"{box_type}_{start_pos}"
                description = BOX_DESCRIPTIONS.get(box_type, "Box não documentado")
                G.add_node(node_id, type=box_type, size=size, offset=start_pos, content=content, description=description)
                
                if isinstance(content, list):
                    add_sub_boxes_to_graph(G, node_id, content)
                
                file.seek(end_pos)
            except Exception as e:
                print(f"Erro ao processar arquivo na posição {file.tell()}: {str(e)}")
                break
    
    return G

def add_sub_boxes_to_graph(G, parent_id, sub_boxes):
    for sub_box in sub_boxes:
        sub_node_id = f"{sub_box['type']}_{sub_box['offset']}"
        description = BOX_DESCRIPTIONS.get(sub_box['type'], "Box não documentado")
        G.add_node(sub_node_id, **sub_box, description=description)
        G.add_edge(parent_id, sub_node_id)
        
        if isinstance(sub_box['content'], list):
            add_sub_boxes_to_graph(G, sub_node_id, sub_box['content'])

def print_graph_structure(G: nx.DiGraph):
    def print_node(node, level=0):
        node_data = G.nodes[node]
        indent = "  " * level
        print(f"{indent}{node_data['type']} (Tamanho: {node_data['size']}, Offset: {node_data['offset']})")
        print(f"{indent}  Descrição: {node_data['description']}")
        
        if 'content' in node_data and isinstance(node_data['content'], dict):
            for key, value in node_data['content'].items():
                print(f"{indent}  {key}: {value}")
        
        for child in sorted(G.successors(node), key=lambda x: G.nodes[x]['offset']):
            print_node(child, level + 1)

    roots = [n for n in G.nodes() if G.in_degree(n) == 0]
    for root in sorted(roots, key=lambda x: G.nodes[x]['offset']):
        print_node(root)