"""Significados forenses de tags EXIF/TIFF (aba EXIF do visualizador de metadados)."""

from __future__ import annotations

from core.metadata.xmp_property_hints import property_hint as _xmp_property_hint

# Chave = nome local da tag (sem prefixo EXIF:/GPS:).
EXIF_PROPERTY_HINTS: dict[str, str] = {
    # --- Datas e software (TIFF + EXIF) ---
    "DateTime": "Data/hora da última modificação do arquivo (tag TIFF 306)",
    "ModifyDate": "Data/hora da última modificação gravada nos metadados",
    "CreateDate": "Data/hora de criação/digitalização do recurso",
    "DateTimeOriginal": "Data/hora original da captura (relógio da câmera)",
    "DateTimeDigitized": "Data/hora em que a imagem foi digitalizada ou convertida",
    "SubSecTime": "Fração de segundo da última modificação",
    "SubSecTimeOriginal": "Fração de segundo da captura original",
    "SubSecTimeDigitized": "Fração de segundo da digitalização",
    "OffsetTime": "Deslocamento de fuso horário da última modificação",
    "OffsetTimeOriginal": "Deslocamento de fuso horário da captura",
    "OffsetTimeDigitized": "Deslocamento de fuso horário da digitalização",
    "Software": "Software que processou ou salvou o arquivo (ex.: Photoshop)",
    # --- Identificação do dispositivo ---
    "Make": "Fabricante da câmera ou dispositivo de captura",
    "Model": "Modelo da câmera ou dispositivo",
    "SerialNumber": "Número de série do dispositivo",
    "BodySerialNumber": "Número de série do corpo da câmera",
    "LensMake": "Fabricante da lente",
    "LensModel": "Modelo da lente utilizada",
    "LensSerialNumber": "Número de série da lente",
    "LensSpecification": "Especificação da lente (distâncias focais, aberturas)",
    "UniqueCameraModel": "Identificador único do modelo de câmera (DNG)",
    "CameraSerialNumber": "Número de série da câmera",
    # --- Dimensões e orientação ---
    "ImageWidth": "Largura da imagem em pixels",
    "ImageLength": "Altura da imagem em pixels",
    "ImageHeight": "Altura da imagem em pixels",
    "ExifImageWidth": "Largura efetiva registrada no bloco EXIF (pixels)",
    "ExifImageHeight": "Altura efetiva registrada no bloco EXIF (pixels)",
    "PixelXDimension": "Largura efetiva da imagem (pixels)",
    "PixelYDimension": "Altura efetiva da imagem (pixels)",
    "Orientation": "Orientação da imagem (1=normal, 3=180°, 6=90° horário, 8=270°…)",
    "XResolution": "Resolução horizontal declarada (dpi)",
    "YResolution": "Resolução vertical declarada (dpi)",
    "ResolutionUnit": "Unidade de resolução (2=polegadas, 3=centímetros)",
    # --- Exposição e captura ---
    "ExposureTime": "Tempo de exposição em segundos (ex.: 0.025 = 1/40 s)",
    "FNumber": "Abertura do diafragma (f-number)",
    "ExposureProgram": "Programa de exposição (0=não def., 1=manual, 2=normal…)",
    "ExposureMode": "Modo de exposição (0=auto, 1=manual, 2=bracketing)",
    "ExposureBiasValue": "Compensação de exposição em EV",
    "ExposureCompensation": "Compensação de exposição em EV (alias de ExposureBiasValue)",
    "ExposureIndex": "Índice de exposição utilizado",
    "ShutterSpeedValue": "Velocidade do obturador em unidades APEX",
    "ApertureValue": "Abertura em unidades APEX",
    "MaxApertureValue": "Abertura máxima da lente em unidades APEX",
    "BrightnessValue": "Brilho estimado da cena (APEX)",
    "MeteringMode": "Modo de medição (1=média, 2=centro, 5=matricial, 6=parcial…)",
    "LightSource": "Fonte de luz (0=desconhecida, 1=daylight, 4=flash…)",
    "ISOSpeedRatings": "Sensibilidade ISO",
    "ISO": "Sensibilidade ISO",
    "PhotographicSensitivity": "Sensibilidade fotográfica (ISO moderno)",
    "SensitivityType": "Tipo de valor ISO reportado",
    "StandardOutputSensitivity": "ISO de saída padrão",
    "RecommendedExposureIndex": "Índice de exposição recomendado",
    "FocalLength": "Distância focal da lente (mm)",
    "FocalLengthIn35mmFormat": "Equivalente em câmera full-frame 35 mm",
    "FocalLengthIn35mmFilm": "Equivalente em filme 35 mm (alias)",
    "DigitalZoomRatio": "Fator de zoom digital aplicado",
    "SubjectDistance": "Distância estimada ao assunto (metros)",
    "SubjectDistanceRange": "Faixa de distância do assunto (0=desconhecida)",
    # --- Flash ---
    "Flash": "Status de flash codificado (bitmask: disparo, modo, retorno, olhos vermelhos)",
    "FlashEnergy": "Energia do flash (Beam Candle Power Seconds)",
    "FlashpixVersion": "Versão FlashPix suportada",
    # --- Cor e processamento ---
    "ColorSpace": "Espaço de cor (1=sRGB, 65535=não calibrado, 2=Adobe RGB)",
    "ComponentsConfiguration": "Ordem dos componentes de cor (ex.: 1 2 3 0 = Y Cb Cr)",
    "CompressedBitsPerPixel": "Compressão média em bits por pixel",
    "Compression": "Esquema de compressão (6=JPEG no TIFF/EXIF)",
    "Contrast": "Ajuste de contraste da câmera (0=normal)",
    "Saturation": "Ajuste de saturação da câmera (0=normal)",
    "Sharpness": "Ajuste de nitidez da câmera (0=normal)",
    "GainControl": "Controle de ganho ISO digital",
    "WhiteBalance": "Balanço de branco (0=auto, 1=manual)",
    "CustomRendered": "Renderização especial (0=normal, 1=HDR, 6=panorama…)",
    "SceneCaptureType": "Tipo de cena (0=standard, 1=landscape, 2=portrait, 3=night)",
    "SceneType": "Origem da cena (1=fotografia direta)",
    "YCbCrPositioning": "Amostragem YCbCr (1=centered, 2=co-sited)",
    "YCbCrCoefficients": "Coeficientes de transformação RGB→YCbCr",
    "Gamma": "Valor gamma declarado",
    # --- Sensor e CFA ---
    "SensingMethod": "Tipo de sensor (2=one-chip color, 3=three-chip…)",
    "CFAPattern": "Padrão de filtro de cor (CFA) do sensor",
    "CFARepeatPatternDim": "Dimensão do padrão CFA repetido",
    "CFAPattern2": "Padrão CFA estendido",
    "FileSource": "Origem do arquivo (3=câmera digital DSC)",
    # --- Versões e interoperabilidade ---
    "ExifVersion": "Versão do padrão EXIF (0221 = 2.21)",
    "ExifOffset": "Deslocamento do bloco EXIF dentro do segmento APP1 (bytes)",
    "InteropIndex": "Índice de interoperabilidade (R98 = recomendado EXIF)",
    "InteropVersion": "Versão do registro de interoperabilidade",
    # --- Miniatura embutida ---
    "ThumbnailImage": "Miniatura JPEG embutida no bloco EXIF",
    "ThumbnailLength": "Tamanho da miniatura embutida (bytes)",
    "ThumbnailOffset": "Deslocamento da miniatura no bloco EXIF (bytes)",
    "JPEGInterchangeFormat": "Offset do JPEG embutido (miniatura)",
    "JPEGInterchangeFormatLength": "Tamanho do JPEG embutido (miniatura)",
    # --- Comentários e descrição ---
    "UserComment": "Comentário do usuário (pode estar vazio ou em charset específico)",
    "ImageDescription": "Descrição textual da imagem",
    "Artist": "Autor ou fotógrafo",
    "Copyright": "Informação de direitos autorais",
    # --- GPS ---
    "GPSVersionID": "Versão do bloco GPS EXIF",
    "GPSLatitude": "Latitude GPS",
    "GPSLongitude": "Longitude GPS",
    "GPSAltitude": "Altitude GPS",
    "GPSTimeStamp": "Hora UTC da posição GPS",
    "GPSDateStamp": "Data UTC da posição GPS",
    "GPSLatitudeRef": "Referência de latitude (N ou S)",
    "GPSLongitudeRef": "Referência de longitude (E ou W)",
    "GPSAltitudeRef": "Referência de altitude (0=acima do nível do mar)",
    "GPSProcessingMethod": "Método de processamento GPS",
    "GPSAreaInformation": "Nome da área GPS",
    "GPSDOP": "Diluição de precisão (DOP)",
    "GPSSpeed": "Velocidade GPS",
    "GPSSpeedRef": "Unidade de velocidade GPS",
    "GPSTrack": "Direção do movimento GPS",
    "GPSTrackRef": "Referência da direção (T=true north, M=magnetic)",
    "GPSImgDirection": "Direção da imagem no momento da captura",
    "GPSImgDirectionRef": "Referência da direção da imagem",
    "GPSMapDatum": "Datum geodésico utilizado",
    "GPSDestLatitude": "Latitude do destino",
    "GPSDestLongitude": "Longitude do destino",
    "GPSDestBearing": "Azimute para o destino",
    "GPSDestDistance": "Distância até o destino",
    # --- Outros frequentes em laudo ---
    "MakerNote": "Bloco proprietário do fabricante (MakerNotes)",
    "MakerNoteVersion": "Versão do esquema MakerNote",
    "ImageUniqueID": "Identificador único da imagem",
    "CameraOwnerName": "Nome do proprietário da câmera",
    "PhotometricInterpretation": "Interpretação fotométrica (RGB, YCbCr, etc.)",
    "BitsPerSample": "Bits por amostra de cor",
    "SamplesPerPixel": "Número de amostras por pixel",
    "PlanarConfiguration": "Organização planar dos dados de cor",
    "StripOffsets": "Offsets dos strips TIFF",
    "RowsPerStrip": "Linhas por strip TIFF",
    "StripByteCounts": "Tamanhos dos strips TIFF",
    "RelatedSoundFile": "Arquivo de áudio associado",
    "SpectralSensitivity": "Sensibilidade espectral do sensor",
    "SpatialFrequencyResponse": "Resposta em frequência espacial",
    "DeviceSettingDescription": "Configurações do dispositivo no momento da captura",
    "SubjectLocation": "Localização do assunto na imagem (coordenadas)",
    "SubjectArea": "Área do assunto na imagem",
    "BatteryLevel": "Nível de bateria reportado",
    "Temperature": "Temperatura ambiente ou do sensor",
    "Humidity": "Umidade relativa reportada",
    "Pressure": "Pressão atmosférica reportada",
    "WaterDepth": "Profundidade na água (subaquático)",
    "Acceleration": "Aceleração no momento da captura",
    "CameraElevationAngle": "Ângulo de elevação da câmera",
}


def _normalize_exif_tag(tag: str) -> str:
    """Extrai nome local de tags EXIF:Foo, GPS:Bar ou Foo."""
    if not tag:
        return ""
    if ":" in tag:
        prefix, local = tag.split(":", 1)
        if prefix.upper() in ("EXIF", "GPS", "IFD0", "IFD1", "SUBIFD", "INTEROP", "THUMBNAIL"):
            return local
        return local
    return tag


def exif_property_hint(tag: str) -> str | None:
    """Resolve significado forense de uma tag EXIF/TIFF/GPS."""
    if not tag:
        return None
    local = _normalize_exif_tag(tag)
    if local in EXIF_PROPERTY_HINTS:
        return EXIF_PROPERTY_HINTS[local]
    if tag in EXIF_PROPERTY_HINTS:
        return EXIF_PROPERTY_HINTS[tag]
    return _xmp_property_hint(local) or _xmp_property_hint(tag)
