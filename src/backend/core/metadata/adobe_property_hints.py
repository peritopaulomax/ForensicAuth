"""Significados forenses de tags Adobe / Photoshop / DNG / Camera Raw."""

from __future__ import annotations

from core.metadata.xmp_property_hints import property_hint as _xmp_property_hint

ADOBE_PROPERTY_HINTS: dict[str, str] = {
    # --- Photoshop Image Resource Block (IRB) ---
    "DisplayedUnitsX": "Unidade de medida horizontal na interface (1=polegadas, 2=cm, 3=pontos)",
    "DisplayedUnitsY": "Unidade de medida vertical na interface (1=polegadas, 2=cm, 3=pontos)",
    "GlobalAltitude": "Altitude global para efeitos de iluminação/bevel (graus)",
    "GlobalAngle": "Ângulo global para sombras/realces de camada (graus)",
    "HasRealMergedData": "Indica se dados reais de camadas mescladas foram preservados (1=sim)",
    "IPTCDigest": "Hash MD5 dos dados IPTC — detecta alteração nos metadados IPTC",
    "NumSlices": "Número de fatias (slicing) definidas para exportação web",
    "PhotoshopFormat": "Formato do bloco Photoshop embutido (0=padrão)",
    "PhotoshopQuality": "Qualidade JPEG usada ao salvar pelo Photoshop (0–12)",
    "PhotoshopThumbnail": "Miniatura RGB embutida no bloco Photoshop (IRB)",
    "PixelAspectRatio": "Proporção largura/altura do pixel (1.0 = pixels quadrados)",
    "PrintPosition": "Posição da imagem na página de impressão (x y)",
    "PrintScale": "Escala de impressão (1=100%, 0.5=50%, etc.)",
    "PrintStyle": "Estilo de impressão (0=centered, 1=size to fit, 2=user defined)",
    "ProgressiveScans": "Número de scans na codificação JPEG progressiva",
    "ReaderName": "Aplicativo que leu o bloco Photoshop (ex.: Adobe Photoshop CS4)",
    "SlicesGroupName": "Nome do grupo de fatias (slicing) — pode refletir nome do arquivo original",
    "URL_List": "Lista de URLs associadas ao documento Photoshop",
    "WriterName": "Aplicativo que gravou o bloco Photoshop (ex.: Adobe Photoshop)",
    "XResolution": "Resolução horizontal declarada no bloco Photoshop (dpi)",
    "YResolution": "Resolução vertical declarada no bloco Photoshop (dpi)",
    # --- Photoshop / IPTC embutido ---
    "ColorMode": "Modo de cor Photoshop (3=RGB, 4=CMYK, 7=Multichannel)",
    "ICCProfile": "Nome do perfil ICC referenciado pelo Photoshop",
    "CaptionWriter": "Autor da legenda IPTC gravada pelo Photoshop",
    "Headline": "Manchete editorial IPTC",
    "Instructions": "Instruções especiais de uso/publicação",
    "TransmissionReference": "Referência de transmissão IPTC",
    "Urgency": "Urgência editorial IPTC (1–8)",
    "Category": "Categoria IPTC",
    "SupplementalCategories": "Categorias suplementares IPTC",
    "DocumentAncestors": "IDs de documentos ancestrais na cadeia de edição Photoshop",
    "TextLayers": "Camadas de texto presentes no documento",
    "LayerName": "Nome de camada registrada nos metadados",
    "LayersGroupInfo": "Informação de agrupamento de camadas",
    "LayerState": "Estado de visibilidade/seleção de camadas",
    "LayerSelectionIDs": "IDs das camadas selecionadas",
    "LayerGroupsEnabledID": "ID do grupo de camadas ativo",
    "LayerGroups": "Grupos de camadas no documento",
    "Version": "Versão do formato de metadados Adobe",
    # --- DNG / Camera Raw ---
    "DNGVersion": "Versão do formato DNG",
    "DNGBackwardVersion": "Versão DNG mínima compatível para leitura",
    "UniqueCameraModel": "Identificador único do modelo de câmera (DNG)",
    "LocalizedCameraModel": "Nome localizado do modelo de câmera",
    "CameraCalibration1": "Matriz de calibração da câmera (DNG)",
    "CameraCalibration2": "Segunda matriz de calibração (DNG)",
    "AsShotNeutral": "Neutralidade de cor no momento da captura",
    "AsShotWhiteXY": "Balanço de branco como coordenadas cromáticas",
    "BaselineExposure": "Exposição de referência DNG",
    "BaselineNoise": "Ruído de referência DNG",
    "BaselineSharpness": "Nitidez de referência DNG",
    "LinearResponseLimit": "Limite de resposta linear do sensor",
    "LensInfo": "Informação da lente (distâncias focais e aberturas)",
    "RawDataUniqueID": "ID único dos dados RAW",
    "OriginalRawFileName": "Nome do arquivo RAW de origem",
    "OriginalRawFileDigest": "Hash do arquivo RAW de origem",
    "ActiveArea": "Área ativa do sensor (crop efetivo)",
    "DefaultCropSize": "Tamanho de crop padrão",
    "DefaultCropOrigin": "Origem do crop padrão",
    "OpcodeList1": "Lista de opcodes de processamento DNG (estágio 1)",
    "OpcodeList2": "Lista de opcodes de processamento DNG (estágio 2)",
    "OpcodeList3": "Lista de opcodes de processamento DNG (estágio 3)",
    "ProfileName": "Nome do perfil de cor Camera Raw",
    "ProfileDigest": "Hash do perfil Camera Raw aplicado",
    "ProfileCalibrationSignature": "Assinatura de calibração do perfil",
    # --- Lightroom / Bridge flags ---
    "Marked": "Imagem marcada/selecionada no Lightroom/Bridge",
    "Rating": "Classificação por estrelas (0–5)",
    "Label": "Rótulo de cor organizacional",
    "CropTop": "Coordenada superior do recorte Lightroom",
    "CropLeft": "Coordenada esquerda do recorte Lightroom",
    "CropBottom": "Coordenada inferior do recorte Lightroom",
    "CropRight": "Coordenada direita do recorte Lightroom",
    "CropAngle": "Ângulo de rotação do recorte Lightroom",
    "HasCrop": "Indica se recorte Lightroom foi aplicado",
    "HasSettings": "Indica se ajustes Lightroom/Camera Raw foram aplicados",
    "AlreadyApplied": "Ajustes Camera Raw já aplicados ao pixel data",
    "History": "Histórico de ações de edição Adobe",
    "DerivedFrom": "Documento de origem na cadeia de derivação",
    "DocumentID": "ID único do documento Adobe",
    "InstanceID": "ID da instância atual do recurso",
    "OriginalDocumentID": "ID do documento na origem da cadeia",
    # --- PDF Adobe ---
    "Producer": "Software produtor do PDF",
    "Creator": "Aplicativo criador do documento",
    "Trapped": "Status de trapping em PDF",
}


def _normalize_adobe_tag(tag: str) -> tuple[str, str]:
    """Retorna (fabricante/prefixo, nome local)."""
    if not tag:
        return "", ""
    if ":" in tag:
        prefix, local = tag.split(":", 1)
        return prefix, local
    return "", tag


def adobe_property_hint(tag: str) -> str | None:
    """Resolve significado forense de uma tag Adobe/Photoshop/DNG."""
    if not tag:
        return None
    prefix, local = _normalize_adobe_tag(tag)
    if local in ADOBE_PROPERTY_HINTS:
        return ADOBE_PROPERTY_HINTS[local]
    if tag in ADOBE_PROPERTY_HINTS:
        return ADOBE_PROPERTY_HINTS[tag]
    if prefix.lower() in ("crs", "crssettings", "camera raw settings"):
        crs_hint = _xmp_property_hint(local)
        if crs_hint:
            return crs_hint
    return _xmp_property_hint(local) or _xmp_property_hint(tag)
