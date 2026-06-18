# -*- coding: utf-8 -*-
"""Extracted from Analise_Opus.ipynb"""

# --- Cell 0 ---
import struct
import os
import sys
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════════════
# ESTRUTURAS DE DADOS
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class OggPage:
    """Representa uma página Ogg completa"""
    offset: int              # Posição no arquivo
    version: int             # Versão (sempre 0)
    header_type: int         # Flags: 0x01=cont, 0x02=BOS, 0x04=EOS
    granule_position: int    # Timestamp (samples @ 48kHz)
    serial_number: int       # ID do fluxo lógico
    page_sequence: int       # Número sequencial da página
    checksum: int            # CRC32
    segments: List[int]      # Tabela de segmentos
    data: bytes              # Dados da página
    
    @property
    def is_bos(self) -> bool:
        """Verifica se é página BOS (Beginning of Stream)"""
        return bool(self.header_type & 0x02)
    
    @property
    def is_eos(self) -> bool:
        """Verifica se é página EOS (End of Stream)"""
        return bool(self.header_type & 0x04)
    
    @property
    def is_continued(self) -> bool:
        """Verifica se continua pacote anterior"""
        return bool(self.header_type & 0x01)
    
    @property
    def total_size(self) -> int:
        """Tamanho total da página (header + segments + data)"""
        return 27 + len(self.segments) + len(self.data)


@dataclass
class OpusIDHeader:
    """Cabeçalho de Identificação Opus (OpusHead)"""
    version: int             # Versão (sempre 1)
    channels: int            # Número de canais (1-255)
    pre_skip: int            # Samples a descartar no início
    input_sample_rate: int   # Taxa original antes da codificação
    output_gain: int         # Ganho em dB (Q7.8)
    channel_mapping: int     # Família de mapeamento
    
    def get_output_gain_db(self) -> float:
        """Converte output_gain (Q7.8) para dB"""
        return self.output_gain / 256.0
    
    def get_channel_description(self) -> str:
        """Retorna descrição do número de canais"""
        if self.channels == 1:
            return "Mono"
        elif self.channels == 2:
            return "Stereo"
        else:
            return f"{self.channels} canais"
    
    def get_sample_rate_description(self) -> str:
        """Retorna descrição da taxa de amostragem"""
        if self.input_sample_rate == 0:
            return "48000 Hz (padrão)"
        elif self.input_sample_rate == 8000:
            return "8000 Hz (telefonia)"
        elif self.input_sample_rate == 16000:
            return "16000 Hz (wideband/gravador)"
        elif self.input_sample_rate == 44100:
            return "44100 Hz (CD)"
        elif self.input_sample_rate == 48000:
            return "48000 Hz (profissional)"
        else:
            return f"{self.input_sample_rate} Hz (customizado)"


@dataclass
class OpusCommentHeader:
    """Cabeçalho de Comentários Opus (OpusTags)"""
    vendor: str              # String do vendor/encoder
    comments: Dict[str, str]   # Tags de usuário (TAG=valor)


@dataclass
class OpusTOCByte:
    """Análise do TOC (Table of Contents) byte de um pacote Opus"""
    toc_value: int           # Valor bruto (0-255)
    config: int              # Config code (5 bits)
    stereo: bool             # Stereo flag (1 bit)
    frame_count_code: int    # Frame count code (2 bits)
    
    def get_mode(self) -> str:
        """Retorna o modo do codec (SILK/Hybrid/CELT)"""
        if self.config < 12:
            return "SILK-only"
        elif self.config < 16:
            return "Hybrid (SILK+CELT)"
        else:
            return "CELT-only"
    
    def get_bandwidth(self) -> str:
        """Retorna a bandwidth"""
        config = self.config
        if config < 12:
            return "Narrowband (8 kHz)" if config < 2 else \
                   "Wideband (16 kHz)" if config < 12 else "Unknown"
        elif config < 14:
            return "Narrowband (8 kHz)"
        elif config < 16:
            return "Wideband (16 kHz)"
        elif config < 20:
            return "Super-wideband (24 kHz)"
        else:
            return "Fullband (48 kHz)"
    
    def get_frame_count(self) -> str:
        """Retorna descrição do número de frames"""
        codes = {
            0: "1 frame",
            1: "2 frames (igual tamanho)",
            2: "2 frames (tamanhos diferentes)",
            3: "Código arbitrário (vários frames)"
        }
        return codes.get(self.frame_count_code, "Unknown")

# --- Cell 1 ---
class OggOpusAnalyzer:
    """
    Analisador forense completo de arquivos Ogg/Opus
    """
    
    def __init__(self, filepath: str):
        """
        Inicializa o analisador com o caminho do arquivo
        
        Args:
            filepath: Caminho do arquivo .opus
        """
        self.filepath = filepath
        
        # Verificar se arquivo existe
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Arquivo não encontrado: {filepath}")
        
        # Informações básicas do arquivo
        self.filename = os.path.basename(filepath)
        self.filesize = os.path.getsize(filepath)
        
        # Estruturas extraídas
        self.pages: List[OggPage] = []
        self.id_header: Optional[OpusIDHeader] = None
        self.comment_header: Optional[OpusCommentHeader] = None
        self.toc_analysis: List[OpusTOCByte] = []  # TOC bytes dos pacotes de áudio
        
        # Resultados da análise
        self.warnings: List[str] = []
        self.errors: List[str] = []
        self.duration_seconds: Optional[float] = None
    
    
    # ═══════════════════════════════════════════════════════════════════════
    # PARSING DE PÁGINAS OGG
    # ═══════════════════════════════════════════════════════════════════════
    
    def parse_all_pages(self, f) -> None:
        """
        Lê todas as páginas Ogg do arquivo
        
        Args:
            f: File handle aberto em modo 'rb'
        """
        while True:
            page = self.parse_single_page(f)
            if page is None:
                break
            self.pages.append(page)
    
    
    def parse_single_page(self, f) -> Optional[OggPage]:
        """
        Lê uma única página Ogg do arquivo
        
        Args:
            f: File handle aberto em modo 'rb'
        
        Returns:
            OggPage ou None se não houver mais páginas
        """
        start_offset = f.tell()
        
        # Buscar capture pattern "OggS"
        capture = f.read(4)
        if len(capture) < 4:
            return None
        
        if capture != b'OggS':
            # Não é uma página Ogg válida
            return None
        
        # Ler restante do header (23 bytes)
        try:
            version = struct.unpack('B', f.read(1))[0]
            header_type = struct.unpack('B', f.read(1))[0]
            granule_position = struct.unpack('<Q', f.read(8))[0]
            serial_number = struct.unpack('<I', f.read(4))[0]
            page_sequence = struct.unpack('<I', f.read(4))[0]
            checksum = struct.unpack('<I', f.read(4))[0]
            num_segments = struct.unpack('B', f.read(1))[0]
        except struct.error:
            return None
        
        # Ler segment table
        segment_table = []
        try:
            for _ in range(num_segments):
                segment_table.append(struct.unpack('B', f.read(1))[0])
        except struct.error:
            return None
        
        # Ler dados
        data_size = sum(segment_table)
        data = f.read(data_size)
        
        if len(data) < data_size:
            # Arquivo truncado
            self.errors.append(f"Página em offset {start_offset}: dados truncados")
            return None
        
        return OggPage(
            offset=start_offset,
            version=version,
            header_type=header_type,
            granule_position=granule_position,
            serial_number=serial_number,
            page_sequence=page_sequence,
            checksum=checksum,
            segments=segment_table,
            data=data
        )
    
    
    # ═══════════════════════════════════════════════════════════════════════
    # PARSING DE HEADERS OPUS
    # ═══════════════════════════════════════════════════════════════════════
    
    def parse_id_header(self) -> Optional[OpusIDHeader]:
        """
        Extrai e valida o ID Header (OpusHead) da primeira página
        
        Returns:
            OpusIDHeader ou None se não encontrado/inválido
        """
        if not self.pages:
            self.errors.append("Nenhuma página Ogg encontrada")
            return None
        
        first_page = self.pages[0]
        
        # Validar BOS
        if not first_page.is_bos:
            self.errors.append("Primeira página não tem flag BOS")
        
        # Validar granule position
        if first_page.granule_position != 0:
            self.warnings.append(f"Primeira página tem granule_position != 0: {first_page.granule_position}")
        
        # Verificar magic signature "OpusHead"
        if not first_page.data.startswith(b'OpusHead'):
            self.errors.append("Primeira página não contém 'OpusHead'")
            return None
        
        # Verificar tamanho mínimo (19 bytes)
        if len(first_page.data) < 19:
            self.errors.append(f"OpusHead truncado: apenas {len(first_page.data)} bytes")
            return None
        
        # Extrair campos
        try:
            version = struct.unpack('B', first_page.data[8:9])[0]
            channels = struct.unpack('B', first_page.data[9:10])[0]
            pre_skip = struct.unpack('<H', first_page.data[10:12])[0]
            input_sample_rate = struct.unpack('<I', first_page.data[12:16])[0]
            output_gain = struct.unpack('<h', first_page.data[16:18])[0]
            channel_mapping = struct.unpack('B', first_page.data[18:19])[0]
        except struct.error as e:
            self.errors.append(f"Erro ao parsear OpusHead: {e}")
            return None
        
        # Validar versão
        if version != 1:
            self.warnings.append(f"OpusHead versão não padrão: {version} (esperado: 1)")
        
        # Validar canais
        if channels == 0:
            self.errors.append("Número de canais inválido: 0")
        
        # Análise forense do pre-skip
        if pre_skip == 104:
            # Assinatura confirmada do WhatsApp Android!
            pass  # Isso é tratado em identify_origin()
        elif pre_skip == 312:
            # Valor típico da libopus/FFmpeg padrão
            pass
        elif pre_skip == 120:
            # Valor típico de alguns encoders alternativos
            pass
        else:
            self.warnings.append(
                f"Pre-skip não padrão: {pre_skip} (WhatsApp Android=104, libopus=312, outros=120)"
            )
        
        self.id_header = OpusIDHeader(
            version=version,
            channels=channels,
            pre_skip=pre_skip,
            input_sample_rate=input_sample_rate,
            output_gain=output_gain,
            channel_mapping=channel_mapping
        )
        
        return self.id_header
    
    
    def parse_comment_header(self) -> Optional[OpusCommentHeader]:
        """
        Extrai e valida o Comment Header (OpusTags) da segunda página
        
        Returns:
            OpusCommentHeader ou None se não encontrado/inválido
        """
        if len(self.pages) < 2:
            self.errors.append("Segunda página não encontrada (Comment Header)")
            return None
        
        second_page = self.pages[1]
        
        # Validar granule position
        if second_page.granule_position != 0:
            self.warnings.append(f"Segunda página tem granule_position != 0: {second_page.granule_position}")
        
        # Verificar magic signature "OpusTags"
        if not second_page.data.startswith(b'OpusTags'):
            self.errors.append("Segunda página não contém 'OpusTags'")
            return None
        
        offset = 8  # Pular "OpusTags"
        
        try:
            # Ler vendor string
            vendor_length = struct.unpack('<I', second_page.data[offset:offset+4])[0]
            offset += 4
            
            if offset + vendor_length > len(second_page.data):
                self.errors.append("OpusTags: vendor string truncada")
                return None
            
            vendor_string = second_page.data[offset:offset+vendor_length].decode('utf-8', errors='replace')
            offset += vendor_length
            
            # Ler número de comentários
            if offset + 4 > len(second_page.data):
                self.errors.append("OpusTags: contador de comentários truncado")
                return None
            
            num_comments = struct.unpack('<I', second_page.data[offset:offset+4])[0]
            offset += 4
            
            # Ler comentários
            comments = {}
            for i in range(num_comments):
                if offset + 4 > len(second_page.data):
                    self.warnings.append(f"OpusTags: comentário {i+1} truncado")
                    break
                
                comment_length = struct.unpack('<I', second_page.data[offset:offset+4])[0]
                offset += 4
                
                if offset + comment_length > len(second_page.data):
                    self.warnings.append(f"OpusTags: comentário {i+1} truncado")
                    break
                
                comment_string = second_page.data[offset:offset+comment_length].decode('utf-8', errors='replace')
                offset += comment_length
                
                # Separar TAG=valor
                if '=' in comment_string:
                    tag, value = comment_string.split('=', 1)
                    comments[tag.upper()] = value
                else:
                    comments[f"_UNKNOWN_{i}"] = comment_string
            
        except struct.error as e:
            self.errors.append(f"Erro ao parsear OpusTags: {e}")
            return None
        
        self.comment_header = OpusCommentHeader(
            vendor=vendor_string,
            comments=comments
        )
        
        return self.comment_header
    
    
    # ═══════════════════════════════════════════════════════════════════════
    # ANÁLISE FORENSE
    # ═══════════════════════════════════════════════════════════════════════
    
    def analyze_serial_number(self) -> Dict[str, Any]:
        """
        Analisa o serial number para identificar assinaturas específicas
        
        Returns:
            Dicionário com informações sobre o serial number
        """
        if not self.pages:
            return {}
        
        serial = self.pages[0].serial_number
        
        result = {
            'serial_number': serial,
            'serial_hex': f"0x{serial:08X}",
            'platform_signature': None,
            'confidence': 'Desconhecida'
        }
        
        # Detectar assinaturas conhecidas
        if serial == 0x00000000:
            result['platform_signature'] = 'WhatsApp Android'
            result['confidence'] = 'ALTA'
            result['note'] = 'Serial number zero é assinatura do WhatsApp Android'
        
        elif serial == 0x00000064:  # 100 decimal
            result['platform_signature'] = 'WhatsApp iOS (iPhone/iPad)'
            result['confidence'] = 'ALTA'
            result['note'] = 'Serial number 0x00000064 (100 decimal) é assinatura do WhatsApp iOS (pre-skip 312)'
        
        else:
            result['platform_signature'] = 'Outro encoder (serial aleatório)'
            result['confidence'] = 'Baixa'
            result['note'] = 'Serial number aleatório indica encoder padrão (FFmpeg, libopus, etc.)'
        
        return result
    
    
    def validate_structure(self) -> None:
        """
        Valida a estrutura do arquivo conforme RFC 7845
        """
        if not self.pages:
            return
        
        # 1. Verificar serial number consistente
        if len(self.pages) > 1:
            first_serial = self.pages[0].serial_number
            for i, page in enumerate(self.pages[1:], start=1):
                if page.serial_number != first_serial:
                    self.errors.append(
                        f"Página {i}: serial_number muda de {first_serial:08X} para {page.serial_number:08X} (CONCATENAÇÃO?)"
                    )
        
        # 2. Verificar page_sequence contínuo
        for i, page in enumerate(self.pages):
            if page.page_sequence != i:
                self.errors.append(
                    f"Página {i}: page_sequence esperado {i}, encontrado {page.page_sequence} (PÁGINAS FALTANDO?)"
                )
        
        # 3. Verificar granule_position crescente
        prev_granule = -1
        for i, page in enumerate(self.pages):
            if page.granule_position < prev_granule and page.granule_position != 0:
                self.errors.append(
                    f"Página {i}: granule_position DECRESCENTE ({prev_granule} -> {page.granule_position}) 🚨"
                )
            prev_granule = page.granule_position
        
        # 4. Verificar apenas uma página BOS
        bos_count = sum(1 for page in self.pages if page.is_bos)
        if bos_count != 1:
            self.errors.append(f"Arquivo tem {bos_count} páginas BOS (esperado: 1)")
        
        # 5. Verificar apenas uma página EOS
        eos_count = sum(1 for page in self.pages if page.is_eos)
        if eos_count != 1:
            self.warnings.append(f"Arquivo tem {eos_count} páginas EOS (esperado: 1)")
        
        # 6. Verificar se EOS é a última página
        if eos_count == 1:
            last_eos_index = None
            for i, page in enumerate(self.pages):
                if page.is_eos:
                    last_eos_index = i
            
            if last_eos_index != len(self.pages) - 1:
                self.errors.append(
                    f"Página EOS não é a última (índice {last_eos_index} de {len(self.pages)-1})"
                )
    
    
    def analyze_audio_packets(self) -> None:
        """
        Analisa os pacotes de áudio (páginas 3+) e extrai TOC bytes
        """
        # Páginas de áudio começam após ID Header (pág 1) e Comment Header (pág 2)
        if len(self.pages) < 3:
            return
        
        for i, page in enumerate(self.pages[2:], start=2):
            # Cada página pode conter múltiplos pacotes Opus
            # Por simplicidade, analisamos o primeiro byte de cada página
            if len(page.data) > 0:
                toc_byte = page.data[0]
                
                # Decodificar TOC byte
                config = (toc_byte >> 3) & 0x1F      # Bits 7-3
                stereo = bool((toc_byte >> 2) & 0x01) # Bit 2
                frame_count_code = toc_byte & 0x03    # Bits 1-0
                
                toc = OpusTOCByte(
                    toc_value=toc_byte,
                    config=config,
                    stereo=stereo,
                    frame_count_code=frame_count_code
                )
                
                self.toc_analysis.append(toc)
                
                # Análise: verificar se TOC muda ao longo do arquivo
                if i == 2:  # Primeira página de áudio
                    self.first_toc = toc_byte
                elif toc_byte != self.first_toc:
                    self.warnings.append(
                        f"Página {i}: TOC byte muda de 0x{self.first_toc:02X} "
                        f"para 0x{toc_byte:02X} (modo/bandwidth diferente)"
                    )
    
    
    def calculate_duration(self) -> Optional[float]:
        """
        Calcula a duração do áudio baseada na última granule_position
        
        Returns:
            Duração em segundos, ou None se não puder calcular
        """
        if not self.pages:
            return None
        
        # Última granule position = total de samples @ 48kHz
        last_granule = self.pages[-1].granule_position
        
        if last_granule == 0:
            return None
        
        # Pre-skip deve ser descontado
        pre_skip = self.id_header.pre_skip if self.id_header else 0
        
        # Duração = (samples - pre_skip) / 48000
        effective_samples = last_granule - pre_skip
        duration = effective_samples / 48000.0
        
        self.duration_seconds = duration
        return duration
    
    
    def identify_origin(self) -> Dict[str, Any]:
        """
        Tenta identificar a origem/encoder do arquivo
        
        Returns:
            Dicionário com informações de origem
        """
        origin_info = {
            'vendor': None,
            'encoder_type': 'Desconhecido',
            'likely_source': 'Desconhecido',
            'confidence': 'Baixa',
            'platform_hint': None
        }
        
        if not self.comment_header:
            return origin_info
        
        vendor = self.comment_header.vendor.lower()
        origin_info['vendor'] = self.comment_header.vendor
        
        # Análise do vendor string
        if 'whatsapp' in vendor:
            origin_info['encoder_type'] = 'WhatsApp'
            origin_info['likely_source'] = 'Mensagem de voz WhatsApp'
            origin_info['confidence'] = 'Alta'
            
            # Tentar identificar plataforma pelo pre-skip
            if self.id_header:
                pre_skip = self.id_header.pre_skip
                if pre_skip == 104:
                    origin_info['platform_hint'] = 'Android (assinatura confirmada: pre-skip=104) 🚨'
                    origin_info['confidence'] = 'Muito Alta'
                elif pre_skip == 312:
                    # Pre-skip 312 sozinho não distingue (é o padrão libopus)
                    # Precisa combinar com serial number para identificar iOS
                    origin_info['platform_hint'] = 'iOS usa pre-skip 312 (padrão), verificar serial number'
                    origin_info['confidence'] = 'Média'
                elif pre_skip == 120:
                    origin_info['platform_hint'] = 'Encoder alternativo'
                else:
                    origin_info['platform_hint'] = f'Atípico: pre-skip={pre_skip} (investigar!)'
                    self.warnings.append(
                        f"Pre-skip não padrão ({pre_skip}): pode indicar encoder customizado ou manipulação"
                    )
        
        elif 'telegram' in vendor:
            origin_info['encoder_type'] = 'Telegram'
            origin_info['likely_source'] = 'Mensagem de voz Telegram'
            origin_info['confidence'] = 'Alta'
        
        elif 'discord' in vendor:
            origin_info['encoder_type'] = 'Discord'
            origin_info['likely_source'] = 'Gravação/transmissão Discord'
            origin_info['confidence'] = 'Alta'
        
        elif 'libopus' in vendor or 'opus' in vendor:
            origin_info['encoder_type'] = f'libopus ({vendor})'
            origin_info['likely_source'] = 'Encoder padrão ou FFmpeg'
            origin_info['confidence'] = 'Média'
        
        elif 'ffmpeg' in vendor or 'lavf' in vendor:
            origin_info['encoder_type'] = 'FFmpeg'
            origin_info['likely_source'] = 'Conversão/processamento via FFmpeg'
            origin_info['confidence'] = 'Alta'
        
        # Análise do sample rate (ID Header)
        if self.id_header:
            sr = self.id_header.input_sample_rate
            
            if sr == 8000:
                origin_info['likely_source'] += ' (telefonia/VoIP)'
            elif sr == 16000:
                origin_info['likely_source'] += ' (wideband/gravador básico)'
            elif sr == 44100:
                origin_info['likely_source'] += ' (CD/música)'
            elif sr == 48000:
                origin_info['likely_source'] += ' (profissional/vídeo)'
        
        return origin_info
    
    
    # ═══════════════════════════════════════════════════════════════════════
    # RELATÓRIO 
    # ═══════════════════════════════════════════════════════════════════════
    
    def generate_report(self) -> str:
        """
        Gera relatório completo em formato texto
        
        Returns:
            String com o relatório formatado
        """
        lines = []
        
        # Cabeçalho
        lines.append("═" * 80)
        lines.append("RELATÓRIO - ANÁLISE DE ARQUIVO OGG/OPUS")
        lines.append("═" * 80)
        lines.append(f"Data da análise: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # Informações do arquivo
        lines.append("─" * 80)
        lines.append("[1] INFORMAÇÕES BÁSICAS DO ARQUIVO")
        lines.append("─" * 80)
        lines.append(f"Nome do arquivo: {self.filename}")
        lines.append(f"Tamanho: {self.filesize:,} bytes ({self.filesize / 1024:.2f} KB)")
        lines.append(f"Total de páginas Ogg: {len(self.pages)}")
        
        if self.duration_seconds:
            minutes = int(self.duration_seconds // 60)
            seconds = self.duration_seconds % 60
            lines.append(f"Duração calculada: {minutes}:{seconds:05.2f} ({self.duration_seconds:.2f}s)")
        
        lines.append("")
        
        # ID Header
        lines.append("─" * 80)
        lines.append("[2] ID HEADER (OpusHead) - PARÂMETROS TÉCNICOS")
        lines.append("─" * 80)
        
        if self.id_header:
            lines.append(f"Versão: {self.id_header.version}")
            lines.append(f"Canais: {self.id_header.channels} ({self.id_header.get_channel_description()})")
            lines.append(f"Pre-skip: {self.id_header.pre_skip} samples")
            lines.append(f"*** Input Sample Rate: {self.id_header.get_sample_rate_description()}")
            lines.append(f"Output Gain: {self.id_header.get_output_gain_db():.2f} dB")
            lines.append(f"Channel Mapping Family: {self.id_header.channel_mapping}")
        else:
            lines.append("⚠ ID Header não encontrado ou inválido")
        
        lines.append("")
        
        # Comment Header
        lines.append("─" * 80)
        lines.append("[3] COMMENT HEADER (OpusTags) - METADADOS")
        lines.append("─" * 80)
        
        if self.comment_header:
            lines.append(f"*** Vendor String: {self.comment_header.vendor}")
            lines.append(f"Total de tags: {len(self.comment_header.comments)}")
            
            if self.comment_header.comments:
                lines.append("\nTags encontradas:")
                for tag, value in sorted(self.comment_header.comments.items()):
                    lines.append(f"  {tag} = {value}")
        else:
            lines.append("⚠ Comment Header não encontrado ou inválido")
        
        lines.append("")
        
        # Identificação de origem
        lines.append("─" * 80)
        lines.append("[4] IDENTIFICAÇÃO DE ORIGEM/ENCODER")
        lines.append("─" * 80)
        
        origin = self.identify_origin()
        lines.append(f"Vendor: {origin['vendor']}")
        lines.append(f"Tipo de encoder: {origin['encoder_type']}")
        lines.append(f"Provável fonte: {origin['likely_source']}")
        lines.append(f"Confiança da identificação: {origin['confidence']}")
        
        if origin.get('platform_hint'):
            lines.append(f"Plataforma sugerida: {origin['platform_hint']}")
        
        lines.append("")
        
        # Análise de serial number (ASSINATURA CRÍTICA!)
        serial_info = self.analyze_serial_number()
        if serial_info:
            lines.append("─" * 80)
            lines.append("[5] ASSINATURA DE SERIAL NUMBER ")
            lines.append("─" * 80)
            lines.append(f"Serial Number: {serial_info['serial_hex']} (decimal: {serial_info['serial_number']})")
            lines.append(f"*** Assinatura: {serial_info['platform_signature']}")
            lines.append(f"*** Confiança: {serial_info['confidence']}")
            if 'note' in serial_info:
                lines.append(f"\nNota: {serial_info['note']}")
            
            # Se for assinatura WhatsApp, destacar
            if serial_info['confidence'] == 'ALTA':
                lines.append("")
                lines.append(" ASSINATURA IDENTIFICADAA ")
                lines.append(f"    O serial number {serial_info['serial_hex']} é uma")
                lines.append(f"    assinatura de:")
                lines.append(f"    >>> {serial_info['platform_signature']} <<<")
                
            
            lines.append("")
        
        # Análise de TOC bytes (bitstream)
        if self.toc_analysis:
            lines.append("─" * 80)
            lines.append("[6] ANÁLISE DE BITSTREAM (TOC Bytes)")
            lines.append("─" * 80)
            
            # Usar primeiro TOC como referência
            if self.toc_analysis:
                first_toc = self.toc_analysis[0]
                lines.append(f"TOC byte típico: 0x{first_toc.toc_value:02X}")
                lines.append(f"  Modo: {first_toc.get_mode()}")
                lines.append(f"  Bandwidth: {first_toc.get_bandwidth()}")
                lines.append(f"  Stereo: {'Sim' if first_toc.stereo else 'Não'}")
                lines.append(f"  Frames: {first_toc.get_frame_count()}")
                
                # Estatística de TOC bytes
                toc_values = [toc.toc_value for toc in self.toc_analysis]
                unique_tocs = set(toc_values)
                
                if len(unique_tocs) == 1:
                    lines.append(f"\n✓ TOC consistente em todos os {len(toc_values)} pacotes")
                else:
                    lines.append(f"\n⚠ Encontrados {len(unique_tocs)} TOC bytes diferentes:")
                    from collections import Counter
                    toc_counts = Counter(toc_values)
                    for toc_val, count in toc_counts.most_common(5):
                        pct = (count / len(toc_values)) * 100
                        lines.append(f"    0x{toc_val:02X}: {count} vezes ({pct:.1f}%)")
            
            lines.append("")
        
        # Estrutura das páginas
        lines.append("─" * 80)
        lines.append("[7] ESTRUTURA DAS PÁGINAS OGG")
        lines.append("─" * 80)
        lines.append(f"{'Pág':<4} {'Offset':<10} {'Seq':<5} {'Granule':<15} {'Flags':<10} {'Size':>8}")
        lines.append("─" * 80)
        
        for i, page in enumerate(self.pages[:20]):  # Mostrar primeiras 20
            flags = []
            if page.is_bos:
                flags.append("BOS")
            if page.is_eos:
                flags.append("EOS")
            if page.is_continued:
                flags.append("CONT")
            
            flag_str = ",".join(flags) if flags else "-"
            
            lines.append(
                f"{i:<4} {page.offset:<10} {page.page_sequence:<5} "
                f"{page.granule_position:<15} {flag_str:<10} {page.total_size:>8}"
            )
        
        if len(self.pages) > 20:
            lines.append(f"... (mais {len(self.pages) - 20} páginas)")
        
        lines.append("")
        
        # Avisos e erros
        if self.warnings:
            lines.append("─" * 80)
            lines.append("[8] AVISOS ⚠")
            lines.append("─" * 80)
            for warning in self.warnings:
                lines.append(f"⚠ {warning}")
            lines.append("")
        
        if self.errors:
            lines.append("─" * 80)
            lines.append("[9] ERROS/INCONSISTÊNCIAS 🚨")
            lines.append("─" * 80)
            for error in self.errors:
                lines.append(f"🚨 {error}")
            lines.append("")
        
        # Conclusão
        lines.append("═" * 80)
        lines.append("[CONCLUSÃO]")
        lines.append("═" * 80)
        
        if self.errors:
            lines.append("⚠ O arquivo apresenta INCONSISTÊNCIAS ESTRUTURAIS.")
            lines.append("  Possíveis causas:")
            lines.append("  - Arquivo corrompido")
            lines.append("  - Manipulação/edição")
            lines.append("  - Concatenação mal feita")
            lines.append("  - Encoder não conforme com RFC 7845")
        elif self.warnings:
            lines.append("⚠ O arquivo está estruturalmente válido, mas apresenta algumas anomalias.")
            lines.append("  Recomenda-se análise complementar.")
        else:
            lines.append("✓ O arquivo está estruturalmente conforme com RFC 7845.")
            lines.append("  Nenhuma inconsistência detectada na estrutura.")
            lines.append("")
            lines.append("NOTA: Estrutura válida NÃO garante ausência de edição prévia.")
            lines.append("      Recomenda-se análise espectral e temporal complementar.")
        
        lines.append("")
        lines.append("═" * 80)
        lines.append("Fim do relatório")
        lines.append("═" * 80)
        
        return "\n".join(lines)
    
    
    # ═══════════════════════════════════════════════════════════════════════
    # MÉTODO PRINCIPAL
    # ═══════════════════════════════════════════════════════════════════════
    
    def analyze(self) -> str:
        """
        Realiza análise completa do arquivo Ogg/Opus
        
        Returns:
            String com o relatório completo
        """
        try:
            with open(self.filepath, 'rb') as f:
                # 1. Ler todas as páginas Ogg
                self.parse_all_pages(f)
                
                # 2. Processar ID Header (página 1)
                self.parse_id_header()
                
                # 3. Processar Comment Header (página 2)
                self.parse_comment_header()
                
                # 4. Validar estrutura
                self.validate_structure()
                
                # 5. Analisar pacotes de áudio (TOC bytes)
                self.analyze_audio_packets()
                
                # 6. Calcular duração
                self.calculate_duration()
            
            # 6. Gerar relatório
            return self.generate_report()
        
        except Exception as e:
            return f"ERRO ao analisar arquivo: {str(e)}"

# --- Cell 2 ---
# === ETAPA DE EXECUÇÃO ===

# 👇 Insira o nome do seu arquivo aqui
NOME_DO_ARQUIVO = 'WhatsApp Ptt 2025-09-30 at 13.20.51.ogg'

try:
    # Instanciar o analisador com o arquivo
    analyzer = OggOpusAnalyzer(NOME_DO_ARQUIVO)

    # Realizar a análise completa
    report = analyzer.analyze()

    # Exibir o relatório na tela
    print(report)

except FileNotFoundError:
    print(f'\n[ERRO] Arquivo não encontrado: "{NOME_DO_ARQUIVO}"')
    print("Verifique o nome do arquivo e o caminho informado.")
except Exception as e:
    print(f'\n[ERRO INESPERADO] Ocorreu um problema durante a análise: {e}')
