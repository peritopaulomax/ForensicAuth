# -*- coding: utf-8 -*-
"""Extracted from Analise MP3.ipynb"""

# --- Cell 0 ---
import struct
import os
import sys
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class FrameInfo:
    """Informações extraídas de um frame MP3"""
    offset: int
    version: str
    layer: str
    bitrate: int
    samplerate: int
    channel: str
    size: int
    padding: int
    protection: bool


class MP3Analyzer:
    """Analisador forense de arquivos MP3"""
    
    # Tabelas de decodificação MPEG
    VERSIONS = {0: "2.5", 2: "2", 3: "1"}
    LAYERS = {1: "III", 2: "II", 3: "I"}
    
    # Bitrates em kbps para MPEG-1 Layer III
    BITRATES_V1_L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 
                      160, 192, 224, 256, 320, 0]
    
    # Bitrates para MPEG-2/2.5 Layer III
    BITRATES_V2_L3 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 
                      96, 112, 128, 144, 160, 0]
    
    # Sample rates para MPEG-1
    SAMPLERATES_V1 = [44100, 48000, 32000, 0]
    
    # Sample rates para MPEG-2
    SAMPLERATES_V2 = [22050, 24000, 16000, 0]
    
    # Sample rates para MPEG-2.5
    SAMPLERATES_V25 = [11025, 12000, 8000, 0]
    
    # Modos de canal
    CHANNELS = {
        0: "Stereo",
        1: "Joint Stereo",
        2: "Dual Channel",
        3: "Mono"
    }
    
    # Gêneros ID3v1
    GENRES = [
        "Blues", "Classic Rock", "Country", "Dance", "Disco", "Funk", "Grunge",
        "Hip-Hop", "Jazz", "Metal", "New Age", "Oldies", "Other", "Pop", "R&B",
        "Rap", "Reggae", "Rock", "Techno", "Industrial", "Alternative", "Ska",
        "Death Metal", "Pranks", "Soundtrack", "Euro-Techno", "Ambient",
        "Trip-Hop", "Vocal", "Jazz+Funk", "Fusion", "Trance", "Classical",
        "Instrumental", "Acid", "House", "Game", "Sound Clip", "Gospel", "Noise",
        "AlternRock", "Bass", "Soul", "Punk", "Space", "Meditative",
        "Instrumental Pop", "Instrumental Rock", "Ethnic", "Gothic", "Darkwave",
        "Techno-Industrial", "Electronic", "Pop-Folk", "Eurodance", "Dream",
        "Southern Rock", "Comedy", "Cult", "Gangsta", "Top 40", "Christian Rap",
        "Pop/Funk", "Jungle", "Native American", "Cabaret", "New Wave",
        "Psychadelic", "Rave", "Showtunes", "Trailer", "Lo-Fi", "Tribal",
        "Acid Punk", "Acid Jazz", "Polka", "Retro", "Musical", "Rock & Roll",
        "Hard Rock"
    ]
    
    def __init__(self, filepath: str):
        """
        Inicializa o analisador
        
        Args:
            filepath: Caminho para o arquivo MP3
        """
        self.filepath = filepath
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Arquivo não encontrado: {filepath}")
        
        self.filesize = os.path.getsize(filepath)
        self.frames: List[FrameInfo] = []
        self.id3v1: Optional[Dict] = None
        self.id3v2: Optional[Dict] = None
        self.vbr_header: Optional[Dict] = None
        self.audio_start = 0
        self.audio_end = 0
    
    def analyze(self) -> str:
        """
        Realiza análise completa do arquivo
        
        Returns:
            Relatório formatado em texto
        """
        with open(self.filepath, 'rb') as f:
            # 1. Verificar ID3v2 no início
            self.parse_id3v2(f)
            
            # 2. Analisar frames MP3
            self.parse_frames(f)
            
            # 3. Verificar ID3v1 no final
            self.parse_id3v1(f)
        
        # 4. Gerar relatório
        return self.generate_report()
    
    def parse_frame_header(self, data: bytes) -> Optional[Dict]:
        """
        Decodifica header de frame MP3 (4 bytes)
        
        Args:
            data: 4 bytes do header
            
        Returns:
            Dicionário com campos decodificados ou None se inválido
        """
        if len(data) < 4:
            return None
        
        # Converter para inteiro de 32 bits (big-endian)
        h = struct.unpack('>I', data)[0]
        
        # Verificar sync word (11 bits mais significativos = 1)
        if (h >> 21) != 0x7FF:
            return None
        
        # Extrair campos bit a bit
        version_bits = (h >> 19) & 3
        layer_bits = (h >> 17) & 3
        protection_bit = (h >> 16) & 1
        bitrate_idx = (h >> 12) & 15
        samplerate_idx = (h >> 10) & 3
        padding_bit = (h >> 9) & 1
        private_bit = (h >> 8) & 1
        channel_mode = (h >> 6) & 3
        mode_extension = (h >> 4) & 3
        copyright_bit = (h >> 3) & 1
        original_bit = (h >> 2) & 1
        emphasis = h & 3
        
        # Validar versão e layer
        if version_bits == 1 or layer_bits == 0:
            return None
        
        version = self.VERSIONS.get(version_bits, "Unknown")
        layer = self.LAYERS.get(layer_bits, "Unknown")
        
        # Selecionar tabelas corretas
        if version == "1":
            bitrate_table = self.BITRATES_V1_L3 if layer == "III" else None
            samplerate_table = self.SAMPLERATES_V1
        elif version == "2":
            bitrate_table = self.BITRATES_V2_L3 if layer == "III" else None
            samplerate_table = self.SAMPLERATES_V2
        else:  # 2.5
            bitrate_table = self.BITRATES_V2_L3 if layer == "III" else None
            samplerate_table = self.SAMPLERATES_V25
        
        if not bitrate_table:
            return None
        
        bitrate = bitrate_table[bitrate_idx]
        samplerate = samplerate_table[samplerate_idx]
        
        # Validar bitrate e samplerate
        if bitrate == 0 or samplerate == 0:
            return None
        
        # Calcular tamanho do frame
        if layer == "III":
            # Layer III
            if version == "1":
                frame_size = int(144 * bitrate * 1000 / samplerate) + padding_bit
            else:
                frame_size = int(72 * bitrate * 1000 / samplerate) + padding_bit
        elif layer == "II":
            # Layer II
            frame_size = int(144 * bitrate * 1000 / samplerate) + padding_bit
        else:
            # Layer I
            frame_size = int(12 * bitrate * 1000 / samplerate + padding_bit) * 4
        
        return {
            'version': version,
            'layer': layer,
            'protection': protection_bit == 0,
            'bitrate': bitrate,
            'samplerate': samplerate,
            'padding': padding_bit,
            'channel': self.CHANNELS[channel_mode],
            'size': frame_size,
            'mode_extension': mode_extension,
            'copyright': copyright_bit == 1,
            'original': original_bit == 1
        }
    
    def parse_frames(self, f) -> None:
        """
        Analisa todos os frames MP3 do arquivo
        
        Args:
            f: File object posicionado após ID3v2
        """
        # Posicionar após ID3v2
        if self.id3v2:
            f.seek(self.id3v2['size'])
        else:
            f.seek(0)
        
        self.audio_start = f.tell()
        max_frames = 100  # Limitar para análise rápida
        
        while len(self.frames) < max_frames:
            offset = f.tell()
            
            # Ler próximos 4 bytes
            header_bytes = f.read(4)
            if len(header_bytes) < 4:
                break
            
            # Tentar decodificar header
            frame_info = self.parse_frame_header(header_bytes)
            
            if frame_info:
                # Frame válido encontrado
                self.frames.append(FrameInfo(
                    offset=offset,
                    version=frame_info['version'],
                    layer=frame_info['layer'],
                    bitrate=frame_info['bitrate'],
                    samplerate=frame_info['samplerate'],
                    channel=frame_info['channel'],
                    size=frame_info['size'],
                    padding=frame_info['padding'],
                    protection=frame_info['protection']
                ))
                
                # Verificar header VBR no primeiro frame
                if len(self.frames) == 1:
                    self.detect_vbr_header(f, frame_info)
                
                # Pular para próximo frame
                f.seek(offset + frame_info['size'])
            else:
                # Não é um frame válido, avançar 1 byte
                f.seek(offset + 1)
        
        self.audio_end = f.tell()
    
    def detect_vbr_header(self, f, first_frame: Dict) -> None:
        """
        Detecta headers VBR (Xing/Info/VBRI) no primeiro frame
        
        Args:
            f: File object
            first_frame: Informações do primeiro frame
        """
        current_pos = f.tell()
        
        # Calcular offset do side info
        if first_frame['version'] == "1":
            if first_frame['channel'] == "Mono":
                side_info_size = 17
            else:
                side_info_size = 32
        else:
            if first_frame['channel'] == "Mono":
                side_info_size = 9
            else:
                side_info_size = 17
        
        # Procurar Xing/Info
        f.seek(current_pos + side_info_size)
        vbr_data = f.read(200)  # Ler dados suficientes
        
        xing_offset = vbr_data.find(b'Xing')
        info_offset = vbr_data.find(b'Info')
        vbri_offset = vbr_data.find(b'VBRI')
        
        if xing_offset != -1:
            self.parse_xing_header(vbr_data[xing_offset:], 'Xing')
        elif info_offset != -1:
            self.parse_xing_header(vbr_data[info_offset:], 'Info')
        elif vbri_offset != -1:
            self.parse_vbri_header(vbr_data[vbri_offset:])
        
        f.seek(current_pos)
    
    def parse_xing_header(self, data: bytes, header_type: str) -> None:
        """
        Decodifica header Xing/Info
        
        Args:
            data: Dados começando com 'Xing' ou 'Info'
            header_type: 'Xing' ou 'Info'
        """
        if len(data) < 12:
            return
        
        flags = struct.unpack('>I', data[4:8])[0]
        
        self.vbr_header = {
            'type': header_type,
            'is_vbr': header_type == 'Xing'
        }
        
        offset = 8
        
        # Frames (se flag bit 0 está setado)
        if flags & 0x0001:
            if len(data) >= offset + 4:
                frames = struct.unpack('>I', data[offset:offset+4])[0]
                self.vbr_header['frames'] = frames
                offset += 4
        
        # Bytes (se flag bit 1 está setado)
        if flags & 0x0002:
            if len(data) >= offset + 4:
                bytes_size = struct.unpack('>I', data[offset:offset+4])[0]
                self.vbr_header['bytes'] = bytes_size
                offset += 4
        
        # TOC (se flag bit 2 está setado)
        if flags & 0x0004:
            offset += 100  # TOC tem 100 bytes
        
        # Quality (se flag bit 3 está setado)
        if flags & 0x0008:
            if len(data) >= offset + 4:
                quality = struct.unpack('>I', data[offset:offset+4])[0]
                self.vbr_header['quality'] = quality
                offset += 4
        
        # Procurar LAME tag
        if len(data) >= offset + 9:
            lame_data = data[offset:offset+9]
            if lame_data[:4] == b'LAME' or b'LAME' in lame_data:
                try:
                    lame_version = lame_data[:9].decode('ascii', errors='ignore')
                    self.vbr_header['encoder'] = lame_version.strip()
                except:
                    pass
    
    def parse_vbri_header(self, data: bytes) -> None:
        """
        Decodifica header VBRI
        
        Args:
            data: Dados começando com 'VBRI'
        """
        if len(data) < 26:
            return
        
        version = struct.unpack('>H', data[4:6])[0]
        delay = struct.unpack('>H', data[6:8])[0]
        quality = struct.unpack('>H', data[8:10])[0]
        bytes_size = struct.unpack('>I', data[10:14])[0]
        frames = struct.unpack('>I', data[14:18])[0]
        
        self.vbr_header = {
            'type': 'VBRI',
            'is_vbr': True,
            'version': version,
            'delay': delay,
            'quality': quality,
            'bytes': bytes_size,
            'frames': frames,
            'encoder': 'Fraunhofer (VBRI)'
        }
    
    def parse_id3v2(self, f) -> None:
        """
        Extrai tag ID3v2 do início do arquivo
        
        Args:
            f: File object
        """
        f.seek(0)
        header = f.read(10)
        
        if header[:3] != b'ID3':
            return
        
        version_major = header[3]
        version_minor = header[4]
        flags = header[5]
        
        # Decodificar synchsafe integer (4 bytes, 7 bits cada)
        size_bytes = header[6:10]
        size = (
            (size_bytes[0] << 21) |
            (size_bytes[1] << 14) |
            (size_bytes[2] << 7) |
            size_bytes[3]
        )
        
        # Ler dados da tag
        id3_data = f.read(size)
        
        # Parsear frames
        frames = self.parse_id3v2_frames(id3_data, f"{version_major}.{version_minor}")
        
        self.id3v2 = {
            'version': f"{version_major}.{version_minor}",
            'flags': flags,
            'size': size + 10,  # Incluir header
            'frames': frames
        }
    
    def parse_id3v2_frames(self, data: bytes, version: str) -> Dict:
        """
        Extrai frames individuais da tag ID3v2
        
        Args:
            data: Dados da tag ID3v2
            version: Versão da tag (ex: "2.3")
            
        Returns:
            Dicionário de frames
        """
        frames = {}
        pos = 0
        
        frame_id_size = 4 if version >= "2.3" else 3
        frame_size_bytes = 4 if version >= "2.3" else 3
        frame_flags_size = 2 if version >= "2.3" else 0
        
        while pos < len(data) - 10:
            # Frame ID
            frame_id_bytes = data[pos:pos+frame_id_size]
            
            # Verificar padding (bytes nulos)
            if frame_id_bytes[0] == 0:
                break
            
            try:
                frame_id = frame_id_bytes.decode('ascii')
            except:
                pos += 1
                continue
            
            pos += frame_id_size
            
            # Frame size
            if version >= "2.4":
                # Synchsafe integer
                size_bytes = data[pos:pos+4]
                frame_size = (
                    (size_bytes[0] << 21) |
                    (size_bytes[1] << 14) |
                    (size_bytes[2] << 7) |
                    size_bytes[3]
                )
            else:
                if frame_size_bytes == 4:
                    frame_size = struct.unpack('>I', data[pos:pos+4])[0]
                else:
                    frame_size = struct.unpack('>I', b'\x00' + data[pos:pos+3])[0]
            
            pos += frame_size_bytes
            
            # Flags
            if frame_flags_size > 0:
                frame_flags = data[pos:pos+frame_flags_size]
                pos += frame_flags_size
            
            # Frame data
            frame_data = data[pos:pos+frame_size]
            pos += frame_size
            
            # Decodificar texto se for frame de texto
            if frame_id.startswith('T'):
                text = self.decode_text_frame(frame_data)
                frames[frame_id] = {'size': frame_size, 'text': text}
            elif frame_id == 'COMM':
                text = self.decode_comm_frame(frame_data)
                frames[frame_id] = {'size': frame_size, 'text': text}
            elif frame_id == 'PRIV':
                owner, priv_data = self.decode_priv_frame(frame_data)
                frames[frame_id] = {'size': frame_size, 'owner': owner, 'data': priv_data}
            else:
                frames[frame_id] = {'size': frame_size, 'data': frame_data}
        
        return frames
    
    def decode_text_frame(self, data: bytes) -> str:
        """
        Decodifica frame de texto considerando encoding byte
        
        Args:
            data: Dados do frame
            
        Returns:
            Texto decodificado
        """
        if len(data) == 0:
            return ""
        
        encoding = data[0]
        text_data = data[1:]
        
        try:
            if encoding == 0:  # ISO-8859-1
                return text_data.decode('iso-8859-1').rstrip('\x00')
            elif encoding == 1:  # UTF-16 with BOM
                return text_data.decode('utf-16').rstrip('\x00')
            elif encoding == 2:  # UTF-16BE
                return text_data.decode('utf-16-be').rstrip('\x00')
            elif encoding == 3:  # UTF-8
                return text_data.decode('utf-8').rstrip('\x00')
        except:
            return f"<binary: {len(text_data)} bytes>"
        
        return ""
    
    def decode_comm_frame(self, data: bytes) -> str:
        """
        Decodifica frame COMM (comentário)
        
        Args:
            data: Dados do frame
            
        Returns:
            Comentário decodificado
        """
        if len(data) < 4:
            return ""
        
        encoding = data[0]
        language = data[1:4].decode('ascii', errors='ignore')
        
        # Pular short description (null-terminated)
        desc_end = data.find(b'\x00', 4)
        if desc_end == -1:
            return ""
        
        comment_data = data[desc_end+1:]
        
        try:
            if encoding == 0:
                return comment_data.decode('iso-8859-1')
            elif encoding == 1:
                return comment_data.decode('utf-16')
            elif encoding == 3:
                return comment_data.decode('utf-8')
        except:
            return f"<binary: {len(comment_data)} bytes>"
        
        return ""
    
    def decode_priv_frame(self, data: bytes) -> Tuple[str, bytes]:
        """
        Decodifica frame PRIV
        
        Args:
            data: Dados do frame
            
        Returns:
            Tupla (owner_id, private_data)
        """
        null_pos = data.find(b'\x00')
        if null_pos == -1:
            return "", data
        
        owner = data[:null_pos].decode('ascii', errors='ignore')
        priv_data = data[null_pos+1:]
        
        return owner, priv_data
    
    def parse_id3v1(self, f) -> None:
        """
        Extrai tag ID3v1 do final do arquivo
        
        Args:
            f: File object
        """
        # ID3v1 está nos últimos 128 bytes
        if self.filesize < 128:
            return
        
        f.seek(self.filesize - 128)
        tag_data = f.read(128)
        
        if tag_data[:3] != b'TAG':
            return
        
        # Extrair campos
        title = tag_data[3:33].decode('iso-8859-1', errors='ignore').strip('\x00 ')
        artist = tag_data[33:63].decode('iso-8859-1', errors='ignore').strip('\x00 ')
        album = tag_data[63:93].decode('iso-8859-1', errors='ignore').strip('\x00 ')
        year = tag_data[93:97].decode('iso-8859-1', errors='ignore').strip('\x00 ')
        comment = tag_data[97:127].decode('iso-8859-1', errors='ignore').strip('\x00 ')
        genre_byte = tag_data[127]
        
        # ID3v1.1: se byte 125 é 0 e 126 não é 0, então 126 é track number
        track = None
        if tag_data[125] == 0 and tag_data[126] != 0:
            track = tag_data[126]
            comment = tag_data[97:125].decode('iso-8859-1', errors='ignore').strip('\x00 ')
        
        genre = self.GENRES[genre_byte] if genre_byte < len(self.GENRES) else f"Unknown ({genre_byte})"
        
        self.id3v1 = {
            'title': title,
            'artist': artist,
            'album': album,
            'year': year,
            'comment': comment,
            'track': track,
            'genre': genre
        }
    
    def generate_report(self) -> str:
        """
        Gera relatório completo da análise
        
        Returns:
            Relatório formatado
        """
        lines = []
        
        # Cabeçalho
        lines.append("=" * 80)
        lines.append("RELATÓRIO DE ANÁLISE FORENSE - ARQUIVO MP3")
        lines.append("=" * 80)
        lines.append(f"Arquivo: {os.path.basename(self.filepath)}")
        lines.append(f"Caminho: {self.filepath}")
        lines.append(f"Tamanho: {self.filesize:,} bytes ({self.filesize/1024/1024:.2f} MB)")
        lines.append(f"Data da Análise: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # ID3v2
        if self.id3v2:
            lines.append("-" * 80)
            lines.append(f"[ID3v2] Versão {self.id3v2['version']}, {self.id3v2['size']:,} bytes")
            lines.append("-" * 80)
            
            frames = self.id3v2['frames']
            
            # Frames comuns
            common_frames = {
                'TIT2': 'Título',
                'TPE1': 'Artista',
                'TALB': 'Álbum',
                'TRCK': 'Faixa',
                'TYER': 'Ano',
                'TCON': 'Gênero'
            }
            
            for frame_id, name in common_frames.items():
                if frame_id in frames:
                    lines.append(f"  {name:12}: {frames[frame_id]['text']}")
            
            # Frames forenses
            lines.append("")
            lines.append("  [INFORMAÇÕES FORENSES]")
            
            forensic_frames = {
                'TENC': 'Encoder',
                'TSSE': 'Software',
                'COMM': 'Comentário',
                'TXXX': 'User Defined'
            }
            
            for frame_id, name in forensic_frames.items():
                if frame_id in frames:
                    value = frames[frame_id].get('text', '')
                    lines.append(f"  *** {name:12}: {value}")
            
            # Frame PRIV
            if 'PRIV' in frames:
                priv = frames['PRIV']
                owner = priv.get('owner', 'Unknown')
                data_size = len(priv.get('data', b''))
                lines.append(f"  *** PRIV Owner   : {owner}")
                lines.append(f"      PRIV Data    : {data_size} bytes")
            
            lines.append("")
        
        # Frames MP3
        if self.frames:
            lines.append("-" * 80)
            lines.append(f"[FRAMES MP3] {len(self.frames)} frames analisados")
            lines.append("-" * 80)
            
            first = self.frames[0]
            lines.append(f"  Versão MPEG     : {first.version}")
            lines.append(f"  Layer           : {first.layer}")
            lines.append(f"  Taxa Amostragem: {first.samplerate} Hz")
            lines.append(f"  Modo Canal      : {first.channel}")
            
            # Detectar VBR
            bitrates = list(set(f.bitrate for f in self.frames))
            bitrates.sort()
            
            if len(bitrates) > 1:
                lines.append(f"  *** ALERTA: VBR detectado")
                lines.append(f"      Bitrates encontrados: {bitrates} kbps")
            else:
                lines.append(f"  Bitrate         : {bitrates[0]} kbps (CBR)")
            
            # VBR Header
            if self.vbr_header:
                lines.append("")
                lines.append(f"  [VBR HEADER] Tipo: {self.vbr_header['type']}")
                if 'frames' in self.vbr_header:
                    lines.append(f"  Total Frames    : {self.vbr_header['frames']:,}")
                if 'bytes' in self.vbr_header:
                    lines.append(f"  Total Bytes     : {self.vbr_header['bytes']:,}")
                if 'encoder' in self.vbr_header:
                    lines.append(f"  *** Encoder     : {self.vbr_header['encoder']}")
            
            # Calcular duração
            samples_per_frame = 1152 if first.layer == "III" else 1152
            total_samples = len(self.frames) * samples_per_frame
            duration = total_samples / first.samplerate
            
            lines.append("")
            lines.append(f"  Duração Aprox.  : {duration:.2f} segundos ({duration/60:.2f} minutos)")
            
            # Análise de consistência
            lines.append("")
            lines.append("  [ANÁLISE DE CONSISTÊNCIA]")
            
            # Verificar mudanças de parâmetros
            versions = set(f.version for f in self.frames)
            samplerates = set(f.samplerate for f in self.frames)
            channels = set(f.channel for f in self.frames)
            
            if len(versions) > 1:
                lines.append(f"  *** ALERTA: Múltiplas versões MPEG detectadas: {versions}")
            
            if len(samplerates) > 1:
                lines.append(f"  *** ALERTA: Múltiplas taxas de amostragem: {samplerates} Hz")
            
            if len(channels) > 1:
                lines.append(f"  *** ALERTA: Mudanças no modo de canal: {channels}")
            
            if len(versions) == 1 and len(samplerates) == 1 and len(channels) == 1 and len(bitrates) == 1:
                lines.append("  ✓ Arquivo consistente - sem mudanças detectadas")
            
            lines.append("")
        
        # ID3v1
        if self.id3v1:
            lines.append("-" * 80)
            lines.append("[ID3v1] Tag encontrada (128 bytes no final)")
            lines.append("-" * 80)
            lines.append(f"  Título          : {self.id3v1['title']}")
            lines.append(f"  Artista         : {self.id3v1['artist']}")
            lines.append(f"  Álbum           : {self.id3v1['album']}")
            lines.append(f"  Ano             : {self.id3v1['year']}")
            if self.id3v1['track']:
                lines.append(f"  Faixa           : {self.id3v1['track']}")
            lines.append(f"  Gênero          : {self.id3v1['genre']}")
            if self.id3v1['comment']:
                lines.append(f"  Comentário      : {self.id3v1['comment']}")
            lines.append("")
        
        # Conclusão
        lines.append("=" * 80)
        lines.append("CONCLUSÃO DA ANÁLISE")
        lines.append("=" * 80)
        
        # Determinar tipo
        encoding_type = ""
        bitrates = list(set(f.bitrate for f in self.frames)) if self.frames else []
        if self.vbr_header and self.vbr_header.get('is_vbr'):
            encoding_type = "VBR (Variable Bitrate)"
        elif len(bitrates) > 1:
            encoding_type = "VBR sem header (suspeito)"
        else:
            encoding_type = "CBR (Constant Bitrate)"
        
        lines.append(f"Tipo de Codificação: {encoding_type}")
        
        # Identificar encoder
        encoder = "Desconhecido"
        if self.vbr_header and 'encoder' in self.vbr_header:
            encoder = self.vbr_header['encoder']
        elif self.id3v2 and 'TENC' in self.id3v2['frames']:
            encoder = self.id3v2['frames']['TENC']['text']
        elif self.id3v2 and 'TSSE' in self.id3v2['frames']:
            encoder = self.id3v2['frames']['TSSE']['text']
        
        lines.append(f"Encoder Identificado: {encoder}")
        
        # Alertas
        alerts = []
        versions = set(f.version for f in self.frames) if self.frames else set()
        samplerates = set(f.samplerate for f in self.frames) if self.frames else set()
        
        if len(bitrates) > 1 and not self.vbr_header:
            alerts.append("VBR sem header - pode indicar concatenação ou encoder atípico")
        
        if len(versions) > 1 or len(samplerates) > 1:
            alerts.append("Inconsistências nos parâmetros - possível edição/concatenação")
        
        if not self.id3v2 and not self.id3v1:
            alerts.append("Nenhuma tag de metadados encontrada")
        
        if alerts:
            lines.append("")
            lines.append("ALERTAS:")
            for i, alert in enumerate(alerts, 1):
                lines.append(f"  {i}. {alert}")
        else:
            lines.append("")
            lines.append("Nenhum alerta de inconsistência detectado.")
        
        lines.append("")
        lines.append("=" * 80)
        
        return "\n".join(lines)

if __name__ == "__main__":
    # Exemplo de uso local; substitua pelo caminho do arquivo de interesse.
    NOME_DO_ARQUIVO = "exemplo.mp3"
    try:
        analyzer = MP3Analyzer(NOME_DO_ARQUIVO)
        report = analyzer.analyze()
        print(report)
    except FileNotFoundError:
        print(f'\n[ERRO] Arquivo não encontrado: "{NOME_DO_ARQUIVO}"')
        print("Verifique o nome do arquivo e o caminho informado.")
    except Exception as e:
        print(f'\n[ERRO INESPERADO] Ocorreu um problema durante a análise: {e}')
