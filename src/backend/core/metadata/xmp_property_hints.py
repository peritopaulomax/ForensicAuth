"""Significados forenses de propriedades XMP/EXIF/TIFF/Photoshop (visualizador semântico)."""

from __future__ import annotations

# Chave = nome local da propriedade (sem prefixo de namespace).
XMP_PROPERTY_HINTS: dict[str, str] = {
    # --- Estrutura XMP / RDF ---
    "xmpmeta": "Raiz do pacote de metadados XMP embutido no arquivo",
    "xmptk": "Versão do Adobe XMP Core que gerou ou reescreveu o pacote",
    "XMPToolkit": "Biblioteca geradora do pacote XMP",
    "RDF": "Container RDF — agrupa descrições de recursos e propriedades",
    "RDFDescription": "Bloco RDF com atributos e propriedades do recurso (imagem)",
    "about": "Identificador/URI do recurso descrito (geralmente vazio ou xmp.did:…)",
    "Seq": "Lista ordenada RDF (sequência de valores ou estruturas aninhadas)",
    "Bag": "Conjunto RDF não ordenado de valores",
    "Alt": "Lista RDF de alternativas (ex.: título em vários idiomas)",
    "li": "Item individual dentro de Seq/Bag/Alt",
    # --- Dublin Core ---
    "format": "Formato MIME do recurso (ex.: image/jpeg, image/png)",
    "Format": "Formato MIME do recurso",
    "title": "Título do recurso",
    "Title": "Título do recurso",
    "description": "Descrição textual do conteúdo (Dublin Core)",
    "creator": "Criador/autor do conteúdo",
    "Creator": "Criador/autor do conteúdo",
    "subject": "Assunto ou palavras-chave",
    "Subject": "Assunto ou palavras-chave",
    "rights": "Informação de direitos autorais ou uso",
    "Rights": "Informação de direitos autorais ou uso",
    "Artist": "Autor ou fotógrafo",
    # --- XMP básico (xap) ---
    "CreateDate": "Data/hora em que o recurso foi criado (captura ou geração)",
    "ModifyDate": "Data/hora da última modificação do arquivo/recurso",
    "MetadataDate": "Data/hora da última alteração nos metadados XMP",
    "CreatorTool": "Software ou dispositivo que criou o recurso",
    "Rating": "Classificação por estrelas (0–5, convenção Adobe)",
    "Label": "Rótulo de cor organizacional (Lightroom/Bridge)",
    "Nickname": "Apelido ou nome curto do recurso",
    "Identifier": "Identificador externo do recurso",
    # --- XMP Media Management ---
    "DocumentID": "ID único do documento nesta cadeia de derivação (xmp.did:…)",
    "InstanceID": "ID da instância atual do recurso (muda a cada gravação significativa)",
    "OriginalDocumentID": "ID do documento na origem da cadeia de edição",
    "DerivedFrom": "Referência ao documento de origem (derivação/reexportação)",
    "History": "Histórico de ações de edição (Photoshop, Camera Raw, Lightroom)",
    "ManageTo": "Destinatário da gestão de direitos (opcional)",
    "ManageUI": "URI de gestão de direitos (opcional)",
    # --- Histórico / ResourceEvent ---
    "action": "Ação registrada (created, saved, converted, cropped, printed…)",
    "when": "Data/hora em que a ação foi executada",
    "softwareAgent": "Software que executou a ação (ex.: Adobe Photoshop)",
    "changed": "Partes do documento alteradas na ação",
    "parameters": "Parâmetros adicionais da ação de edição",
    "stEvt:action": "Ação registrada no histórico de edição",
    "stEvt:when": "Momento da ação no histórico",
    "stEvt:softwareAgent": "Aplicativo que executou a ação",
    "stEvt:instanceID": "ID da instância após a ação",
    # --- Photoshop ---
    "ColorMode": "Modo de cor Photoshop (3=RGB, 4=CMYK, 7=Multichannel…)",
    "ICCProfile": "Nome do perfil ICC de cor associado",
    "DocumentAncestors": "IDs de documentos ancestrais na cadeia de edição Photoshop",
    "TextLayers": "Camadas de texto presentes (Photoshop)",
    "LayerName": "Nome de camada registrada nos metadados",
    "CaptionWriter": "Autor da legenda IPTC/Photoshop",
    "Headline": "Manchete/título editorial (IPTC)",
    "Instructions": "Instruções especiais de uso/publicação",
    "TransmissionReference": "Referência de transmissão IPTC",
    "Urgency": "Urgência editorial IPTC (1–8)",
    "Category": "Categoria IPTC",
    "SupplementalCategories": "Categorias suplementares IPTC",
    # --- TIFF ---
    "Make": "Fabricante da câmera ou dispositivo de captura",
    "Model": "Modelo da câmera ou dispositivo",
    "Software": "Software de processamento registrado no TIFF/EXIF",
    "Orientation": "Orientação da imagem (1=normal, 3=180°, 6=90° horário…)",
    "XResolution": "Resolução horizontal declarada (dpi)",
    "YResolution": "Resolução vertical declarada (dpi)",
    "ResolutionUnit": "Unidade de resolução (2=polegadas, 3=centímetros)",
    "YCbCrPositioning": "Amostragem YCbCr (1=centered, 2=co-sited)",
    "NativeDigest": "Hash interno Adobe dos campos nativos (integridade de metadados)",
    "ImageWidth": "Largura da imagem em pixels",
    "ImageLength": "Altura da imagem em pixels",
    "BitsPerSample": "Bits por amostra de cor",
    "Compression": "Esquema de compressão TIFF",
    "PhotometricInterpretation": "Interpretação fotométrica (RGB, YCbCr, etc.)",
    "SamplesPerPixel": "Número de amostras por pixel",
    "PlanarConfiguration": "Organização planar dos dados de cor",
    # --- EXIF (captura / técnico) ---
    "DateTimeOriginal": "Data/hora original da captura (relógio da câmera)",
    "DateTimeDigitized": "Data/hora em que a imagem foi digitalizada ou convertida",
    "SubSecTime": "Fração de segundo da captura",
    "SubSecTimeOriginal": "Fração de segundo da captura original",
    "SubSecTimeDigitized": "Fração de segundo da digitalização",
    "ExposureTime": "Tempo de exposição (ex.: 10/400 = 1/40 s)",
    "FNumber": "Abertura do diafragma (f-number, ex.: 50/10 = f/5.0)",
    "ExposureProgram": "Programa de exposição (0=não def., 1=manual, 2=normal…)",
    "ExposureMode": "Modo de exposição (0=auto, 1=manual, 2=bracketing)",
    "ExposureBiasValue": "Compensação de exposição em EV (ex.: 4/6 ≈ +0,67)",
    "MaxApertureValue": "Abertura máxima da lente em unidades APEX",
    "MeteringMode": "Modo de medição (1=avg, 2=center, 5=pattern, 6=partial…)",
    "LightSource": "Fonte de luz (0=desconhecida, 1=daylight, 4=flash…)",
    "Flash": "Estrutura ou flag de uso de flash na captura",
    "Fired": "Flash disparou (True/False)",
    "Function": "Flash presente sem disparo efetivo (ex.: pré-flash)",
    "Mode": "Modo do flash (0=sem flash, 3=auto, 9=on…)",
    "RedEyeMode": "Redução de olhos vermelhos ativa",
    "Return": "Status de retorno do flash/strobe",
    "FocalLength": "Distância focal da lente (mm)",
    "FocalLengthIn35mmFilm": "Equivalente em câmera full-frame 35mm",
    "DigitalZoomRatio": "Fator de zoom digital aplicado",
    "ISOSpeedRatings": "Sensibilidade ISO",
    "ISO": "Sensibilidade ISO",
    "SensitivityType": "Tipo de valor ISO reportado",
    "StandardOutputSensitivity": "ISO de saída padrão",
    "RecommendedExposureIndex": "Índice de exposição recomendado",
    "ExifVersion": "Versão do padrão EXIF (0221 = 2.21)",
    "FlashpixVersion": "Versão FlashPix suportada",
    "ColorSpace": "Espaço de cor (1=sRGB, 65535=não calibrado)",
    "ComponentsConfiguration": "Ordem dos componentes de cor (YCbCr/RGB)",
    "CompressedBitsPerPixel": "Compressão média em bits por pixel",
    "PixelXDimension": "Largura efetiva da imagem (pixels)",
    "PixelYDimension": "Altura efetiva da imagem (pixels)",
    "SceneCaptureType": "Tipo de cena (0=standard, 1=landscape, 2=portrait, 3=night)",
    "SceneType": "Origem da cena (1=fotografia direta)",
    "CustomRendered": "Renderização especial (0=normal, 1=HDR, 6=panorama…)",
    "Contrast": "Ajuste de contraste da câmera (0=normal)",
    "Saturation": "Ajuste de saturação da câmera (0=normal)",
    "Sharpness": "Ajuste de nitidez da câmera (0=normal)",
    "GainControl": "Controle de ganho ISO digital",
    "WhiteBalance": "Balanço de branco (0=auto, 1=manual)",
    "SubjectDistanceRange": "Faixa de distância do assunto (0=desconhecida)",
    "SensingMethod": "Tipo de sensor (2=one-chip color area, 3=three-chip…)",
    "FileSource": "Origem do arquivo (3=câmera digital DSC)",
    "LensModel": "Modelo da lente utilizada",
    "LensMake": "Fabricante da lente",
    "LensSerialNumber": "Número de série da lente",
    "BodySerialNumber": "Número de série do corpo da câmera",
    # --- GPS ---
    "GPSLatitude": "Latitude GPS (graus decimais ou DMS)",
    "GPSLongitude": "Longitude GPS",
    "GPSAltitude": "Altitude GPS",
    "GPSTimeStamp": "Hora UTC da posição GPS",
    "GPSDateStamp": "Data UTC da posição GPS",
    "GPSVersionID": "Versão do EXIF GPS",
    "GPSLatitudeRef": "Referência latitude (N/S)",
    "GPSLongitudeRef": "Referência longitude (E/W)",
    "GPSAltitudeRef": "Referência altitude (0=acima nível mar)",
    # --- Camera Raw / DNG ---
    "RawFileName": "Nome do arquivo RAW de origem",
    "Version": "Versão do esquema de metadados ou perfil",
    # --- PDF / outros ---
    "Producer": "Software produtor (PDF ou derivado)",
    "Creator": "Aplicativo criador do documento",
}


def property_hint(name: str, *, element_name: str | None = None) -> str | None:
    """Resolve dica por nome local, QName (prefix:local) ou caminho (Flash.Fired)."""
    if not name:
        return None
    if name in XMP_PROPERTY_HINTS:
        return XMP_PROPERTY_HINTS[name]
    local = name.split(":")[-1]
    if local in XMP_PROPERTY_HINTS:
        return XMP_PROPERTY_HINTS[local]
    if "." in local:
        tail = local.split(".")[-1]
        if tail in XMP_PROPERTY_HINTS:
            return XMP_PROPERTY_HINTS[tail]
    if element_name == "Description" and local == "Description":
        return XMP_PROPERTY_HINTS.get("RDFDescription")
    return None
