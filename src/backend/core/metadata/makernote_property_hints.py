"""Significados forenses de MakerNotes — genéricos e por fabricante (ExifTool)."""

from __future__ import annotations

from core.metadata.exif_property_hints import exif_property_hint

# Tags comuns a vários fabricantes (prefixo MakerNotes: ou repetidas).
GENERIC_MAKERNOTE_HINTS: dict[str, str] = {
    "MakerNoteVersion": "Versão do esquema MakerNote do fabricante",
    "FirmwareVersion": "Versão do firmware da câmera no momento da captura",
    "SerialNumber": "Número de série do corpo ou dispositivo",
    "InternalSerialNumber": "Número de série interno gravado pelo fabricante",
    "LensSerialNumber": "Número de série da lente acoplada",
    "LensModel": "Modelo da lente reportado pelo firmware",
    "LensType": "Código interno do tipo de lente",
    "Lens": "Descrição ou código da lente montada",
    "LensID": "Identificador da lente na base do fabricante",
    "LensFocalLength": "Distância focal reportada pelo firmware",
    "LensMaxAperture": "Abertura máxima da lente montada",
    "LensMinAperture": "Abertura mínima da lente montada",
    "FocusMode": "Modo de foco (AF-S, AF-C, manual, etc.)",
    "AFMode": "Modo de autofoco selecionado",
    "AFAreaMode": "Modo de área de autofoco (single, dynamic, wide…)",
    "AFPoint": "Ponto de AF utilizado na captura",
    "AFPointsUsed": "Pontos de AF que confirmaram foco",
    "FocusDistance": "Distância de foco estimada",
    "FlashMode": "Modo de flash configurado na câmera",
    "FlashSetting": "Configuração detalhada do flash",
    "FlashExposureComp": "Compensação de exposição do flash",
    "ExternalFlashExposureComp": "Compensação do flash externo",
    "WhiteBalance": "Preset de balanço de branco da câmera",
    "WhiteBalanceFineTune": "Ajuste fino do balanço de branco",
    "ColorTemperature": "Temperatura de cor do balanço de branco (K)",
    "PictureStyle": "Estilo de imagem / Picture Control aplicado",
    "ColorMode": "Modo de cor da câmera (Standard, Vivid, Monochrome…)",
    "Sharpness": "Nível de nitidez in-camera",
    "Saturation": "Nível de saturação in-camera",
    "Contrast": "Nível de contraste in-camera",
    "ToneCompensation": "Compensação de tom (Nikon Picture Control)",
    "HueAdjustment": "Ajuste de matiz in-camera",
    "NoiseReduction": "Redução de ruído aplicada in-camera",
    "HighISONoiseReduction": "NR em ISO elevado",
    "LongExposureNoiseReduction": "NR de exposição longa",
    "VignetteControl": "Controle de vinheta in-camera",
    "ActiveDLighting": "Otimização de iluminação dinâmica (Nikon D-Lighting)",
    "HDR": "Modo HDR ou composição de alta faixa dinâmica",
    "ShootingMode": "Modo de disparo (P, S, A, M, cena, etc.)",
    "ExposureProgram": "Programa de exposição interno da câmera",
    "ExposureMode": "Modo de exposição (auto, manual, bracketing)",
    "ExposureCompensation": "Compensação de exposição dialada na câmera",
    "ExposureDifference": "Diferença de exposição entre medição e captura",
    "ISO": "ISO selecionado nas configurações da câmera",
    "ISOSetting": "Configuração ISO (auto/fixo/expandido)",
    "ISOInfo": "Informação estendida de ISO",
    "AutoISO": "Faixa ou limite de Auto ISO",
    "ShutterCount": "Contagem de disparos do obturador (forense de uso)",
    "ImageQuality": "Qualidade de gravação (RAW, JPEG fine/normal)",
    "Quality": "Qualidade de compressão/gravação",
    "Compression": "Esquema de compressão interno da câmera",
    "FileFormat": "Formato de arquivo gerado (RAW/JPEG/TIFF)",
    "ImageSize": "Tamanho de imagem configurado (L/M/S)",
    "ImageOptimization": "Otimização de imagem in-camera",
    "Rotation": "Rotação de sensor/imagem registrada",
    "VRMode": "Modo de estabilização de imagem (Vibration Reduction)",
    "VRInfo": "Informação de estabilização (VR/IS/OSS)",
    "DriveMode": "Modo de disparo contínuo/temporizador",
    "MeteringMode": "Modo de medição selecionado na câmera",
    "LightSource": "Fonte de luz configurada",
    "SceneMode": "Modo de cena automático",
    "PictureControl": "Perfil Picture Control / Film Simulation ativo",
    "DateTimeOriginal": "Data/hora da captura (relógio interno da câmera)",
    "TimeZone": "Fuso horário configurado na câmera",
    "GPSVersionID": "Versão do bloco GPS no MakerNote",
    "GPSStatus": "Status do receptor GPS no momento da captura",
}

# Nikon — comum em D70s, D200, D3xxx, D5xx, D7xx, D8xx, Z series.
NIKON_HINTS: dict[str, str] = {
    "NikonCaptureVersion": "Versão do Nikon Capture usado no processamento",
    "NikonCaptureOffsets": "Offsets de processamento Nikon Capture",
    "ImageProcessing": "Pipeline de processamento de imagem Nikon",
    "NEFCompression": "Compressão do NEF/RAW Nikon",
    "NEFLinearizationTable": "Tabela de linearização do RAW Nikon",
    "VignetteControl": "Controle de vinheta Nikon",
    "AutoDistortionControl": "Correção automática de distorção Nikon",
    "RetouchHistory": "Histórico de retoques aplicados na câmera",
    "ImageDataSize": "Tamanho dos dados de imagem no RAW",
    "JPGCompression": "Compressão JPEG in-camera Nikon",
    "CropHiSpeed": "Modo crop/alta velocidade (DX/crop modes)",
    "MultiExposure": "Modo de multi-exposição ativo",
    "HighISONoiseReduction": "NR de ISO alto Nikon",
    "PowerUpTime": "Tempo desde ligar a câmera até a captura",
    "AFInfo2": "Metadados estendidos de autofoco Nikon",
    "LensData": "Bloco de dados da lente Nikon (aberrações, distorção)",
    "LensDataVersion": "Versão do bloco LensData",
    "FlashInfo": "Informação detalhada do flash Nikon",
    "FlashControlMode": "Modo de controle do flash Nikon (TTL, manual…)",
    "FlashGNDistance": "Distância guia número do flash",
    "ExternalFlashFlags": "Flags do flash externo Nikon",
    "ProgramShift": "Shift de programa aplicado no modo P",
    "ExposureTuning": "Ajuste fino de exposição Nikon",
    "ColorSpace": "Espaço de cor configurado (sRGB / Adobe RGB)",
    "DigitalVariProgram": "Programa de cena automático Nikon",
    "ShootingMode": "Modo de disparo Nikon (PSAM, cena, U1/U2…)",
    "CameraSerialNumber": "Número de série do corpo Nikon",
    "ShutterCount": "Contagem de disparos do obturador Nikon",
}

# Canon — EOS, PowerShot, RF/EF.
CANON_HINTS: dict[str, str] = {
    "OwnerName": "Nome do proprietário configurado na câmera Canon",
    "CanonImageType": "Tipo de imagem Canon (Full RAW, CR2, etc.)",
    "CanonFirmwareVersion": "Versão do firmware Canon",
    "CanonModelID": "ID interno do modelo Canon",
    "LensModel": "Modelo da lente Canon (decodificado)",
    "LensType": "Código Canon do tipo de lente",
    "MaxFocalLength": "Distância focal máxima da lente Canon",
    "MinFocalLength": "Distância focal mínima da lente Canon",
    "ImageStabilization": "Estabilização de imagem da lente Canon (IS)",
    "MacroMode": "Modo macro ativo",
    "SelfTimer": "Temporizador de disparo Canon",
    "RecordMode": "Modo de gravação (single, continuous, video)",
    "FocusContinuous": "Foco contínuo ativo na captura",
    "AESetting": "Configuração de auto-exposição Canon",
    "MeteringMode": "Modo de medição Canon",
    "FlashActivity": "Flash disparou na captura Canon",
    "FlashDetails": "Detalhes do flash Canon (TTL, FEC, etc.)",
    "FocusDistanceUpper": "Limite superior da distância de foco",
    "FocusDistanceLower": "Limite inferior da distância de foco",
    "WhiteBalanceTable": "Tabela de balanço de branco Canon",
    "ColorTemperature": "Temperatura de cor do WB Canon",
    "PictureStyle": "Picture Style Canon ativo",
    "CustomPictureStyleFileName": "Arquivo de Picture Style personalizado",
    "ShutterCount": "Contagem de disparos do obturador Canon",
    "CameraSerialNumber": "Número de série do corpo Canon",
}

# Sony — Alpha, RX, ZV.
SONY_HINTS: dict[str, str] = {
    "SonyModelID": "ID interno do modelo Sony",
    "LensSpec": "Especificação da lente Sony montada",
    "LensMount": "Montagem da lente (E, A, etc.)",
    "FocalLength": "Distância focal Sony",
    "MinFocalLength": "Distância focal mínima",
    "MaxFocalLength": "Distância focal máxima",
    "FlashStatus": "Status do flash Sony",
    "FlashExposureCompSet": "Compensação de flash configurada",
    "ReleaseMode": "Modo de disparo Sony (single, continuous, bracket)",
    "SequenceNumber": "Número na sequência de burst",
    "Quality": "Qualidade RAW/JPEG Sony",
    "PictureEffect": "Efeito criativo Sony aplicado",
    "CreativeStyle": "Creative Style Sony ativo",
    "DynamicRangeOptimizer": "DRO Sony (otimizador de faixa dinâmica)",
    "HighISONoiseReduction2": "NR de ISO alto Sony",
    "ShutterCount": "Contagem de disparos Sony",
    "BatteryLevel": "Nível de bateria no momento da captura",
    "FocusPosition": "Posição do foco no mecanismo",
    "AFMicroAdjValue": "Valor de microajuste AF",
    "SteadyShot": "Estabilização SteadyShot ativa",
}

# Fujifilm — X series, GFX.
FUJIFILM_HINTS: dict[str, str] = {
    "FilmMode": "Simulação de filme Fujifilm (Provia, Velvia, etc.)",
    "DynamicRangeSetting": "Configuração de faixa dinâmica (DR100/200/400)",
    "DevelopmentDynamicRange": "Faixa dinâmica de desenvolvimento",
    "ImageGeneration": "Geração/versão do motor de imagem",
    "ImageStabilization": "Estabilização IBIS/OIS Fujifilm",
    "FocusMode": "Modo de foco Fujifilm",
    "AFMode": "Modo AF Fujifilm",
    "AFStatus": "Status do AF no disparo",
    "ShutterType": "Tipo de obturador (mecânico/eletrônico/híbrido)",
    "ShutterCount": "Contagem de disparos Fujifilm",
    "WhiteBalance": "Preset de balanço de branco Fujifilm",
    "WhiteBalanceFineTune": "Ajuste fino WB Fujifilm",
    "GrainEffect": "Efeito de granulação Fujifilm",
    "ColorChromeEffect": "Efeito Color Chrome",
    "Clarity": "Clareza/microcontraste in-camera",
}

# Olympus / OM System
OLYMPUS_HINTS: dict[str, str] = {
    "SpecialMode": "Modo especial Olympus (panorama, HDR, etc.)",
    "CameraType": "Tipo/família do corpo Olympus",
    "FocusMode": "Modo de foco Olympus",
    "FocusProcess": "Processo de foco utilizado",
    "AFSearch": "Estado da busca AF",
    "FlashMode": "Modo de flash Olympus",
    "FlashDevice": "Dispositivo de flash acoplado",
    "LensDistortionParams": "Parâmetros de distorção da lente Olympus",
    "ShutterCount": "Contagem de disparos Olympus",
    "StackedImage": "Imagem empilhada (modo composição)",
}

# Apple / iPhone
APPLE_HINTS: dict[str, str] = {
    "RunTime": "Tempo de execução do sistema no momento da captura",
    "AEStable": "Auto-exposição estabilizada",
    "AETarget": "Alvo de exposição automática",
    "AFStable": "Autofoco estabilizado",
    "AccelerationVector": "Vetor de aceleração do dispositivo",
    "ImageCaptureType": "Tipo de captura (photo, portrait, night…)",
    "LivePhotoVideoIndex": "Índice do vídeo Live Photo associado",
    "HDRGain": "Ganho HDR aplicado",
    "SignalToNoiseRatio": "SNR estimado na captura",
}

# DJI drones
DJI_HINTS: dict[str, str] = {
    "AbsoluteAltitude": "Altitude absoluta GPS do drone",
    "RelativeAltitude": "Altitude relativa ao ponto de decolagem",
    "GimbalPitch": "Inclinação do gimbal",
    "GimbalRoll": "Rolagem do gimbal",
    "GimbalYaw": "Guinada do gimbal",
    "FlightPitch": "Inclinação do voo",
    "FlightRoll": "Rolagem do voo",
    "FlightYaw": "Guinada do voo",
    "FlightXSpeed": "Velocidade horizontal X",
    "FlightYSpeed": "Velocidade horizontal Y",
    "FlightZSpeed": "Velocidade vertical",
}

MANUFACTURER_HINTS: dict[str, dict[str, str]] = {
    "Nikon": NIKON_HINTS,
    "Canon": CANON_HINTS,
    "Sony": SONY_HINTS,
    "Fujifilm": FUJIFILM_HINTS,
    "FujiFilm": FUJIFILM_HINTS,
    "Olympus": OLYMPUS_HINTS,
    "Apple": APPLE_HINTS,
    "DJI": DJI_HINTS,
    "GoPro": {
        "ImageHeight": "Altura da imagem GoPro",
        "ImageWidth": "Largura da imagem GoPro",
        "ProTune": "ProTune ativo (controle manual expandido)",
    },
    "Panasonic": {
        "WBRedLevel": "Nível vermelho do balanço de branco Panasonic",
        "WBGreenLevel": "Nível verde do balanço de branco Panasonic",
        "WBBlueLevel": "Nível azul do balanço de branco Panasonic",
        "BabyAge": "Idade configurada (modo baby)",
        "Location": "Localização configurada na câmera",
    },
    "Leica": {
        "LensType": "Código Leica do tipo de lente",
        "OriginalFileName": "Nome de arquivo original Leica",
    },
    "Samsung": {
        "SmartAlbum": "Álbum inteligente Samsung",
        "DeviceType": "Tipo de dispositivo Samsung",
    },
    "MakerNotes": GENERIC_MAKERNOTE_HINTS,
}


def _split_makernote_tag(tag: str) -> tuple[str, str]:
    if not tag:
        return "", ""
    if ":" in tag:
        prefix, local = tag.split(":", 1)
        return prefix, local
    return "", tag


def makernote_property_hint(tag: str) -> str | None:
    """
    Resolve significado de MakerNote.

    ExifTool decodifica por fabricante (Nikon:ISO, Canon:OwnerName).
    Tags desconhecidas retornam None — cobertura expande conforme novos padrões.
    """
    if not tag:
        return None
    prefix, local = _split_makernote_tag(tag)

    if prefix in MANUFACTURER_HINTS and local in MANUFACTURER_HINTS[prefix]:
        return MANUFACTURER_HINTS[prefix][local]

    if local in GENERIC_MAKERNOTE_HINTS:
        return GENERIC_MAKERNOTE_HINTS[local]

    if prefix == "MakerNotes" and local in GENERIC_MAKERNOTE_HINTS:
        return GENERIC_MAKERNOTE_HINTS[local]

    # Fabricante reconhecido mas tag específica sem entrada
    if prefix in MANUFACTURER_HINTS:
        generic = GENERIC_MAKERNOTE_HINTS.get(local)
        if generic:
            return f"{generic} ({prefix})"

    return exif_property_hint(tag)
