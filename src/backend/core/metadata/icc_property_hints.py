"""Significados forenses de tags ICC / ICC_Profile."""

from __future__ import annotations

ICC_PROPERTY_HINTS: dict[str, str] = {
    # --- Resumo / identificação ---
    "ProfileSummary": "Resumo do perfil embutido (classe / espaço de cor / tamanho)",
    "ProfileDescription": "Nome legível do perfil ICC (ex.: sRGB IEC61966-2.1)",
    "ProfileFileSignature": "Assinatura do arquivo ICC (acsp = perfil válido)",
    "ProfileVersion": "Versão do formato ICC (528 = v2.0.0)",
    "ProfileClass": "Classe do perfil (mntr=monitor, prtr=impressora, scnr=scanner, spac=espaço)",
    "ProfileCMMType": "Tipo do CMM que criou o perfil (Lino=Linotype, ADBE=Adobe, etc.)",
    "ProfileCreator": "Criador do perfil ICC",
    "ProfileCopyright": "Copyright declarado no perfil ICC",
    "ProfileDateTime": "Data/hora de criação do perfil ICC",
    "ProfileID": "ID único do perfil (MD5 dos campos principais; zeros = não calculado)",
    "PrimaryPlatform": "Plataforma primária (MSFT=Microsoft, AAPL=Apple, etc.)",
    # --- Espaços de cor ---
    "ColorSpaceData": "Espaço de cor do dispositivo (RGB, CMYK, GRAY, Lab)",
    "ProfileConnectionSpace": "Espaço de conexão do perfil (geralmente XYZ ou Lab)",
    "ConnectionSpaceIlluminant": "Iluminante do espaço de conexão (CIE XYZ)",
    "RenderingIntent": "Intento de renderização (0=perceptual, 1=relative colorimetric, 2=saturation, 3=absolute)",
    # --- Dispositivo ---
    "DeviceManufacturer": "Fabricante do dispositivo associado ao perfil",
    "DeviceMfgDesc": "Descrição do fabricante do dispositivo",
    "DeviceModel": "Modelo do dispositivo associado ao perfil",
    "DeviceModelDesc": "Descrição do modelo/dispositivo (ex.: IEC 61966-2.1 sRGB)",
    "DeviceAttributes": "Atributos do dispositivo (reflective/transparent, matte/glossy)",
    "Technology": "Tecnologia de exibição (CRT, LCD, etc.)",
    # --- Pontos de referência e matrizes ---
    "MediaWhitePoint": "Ponto de branco da mídia (CIE XYZ)",
    "MediaBlackPoint": "Ponto de preto da mídia (CIE XYZ)",
    "RedMatrixColumn": "Coluna da matriz de conversão para vermelho (CIE XYZ)",
    "GreenMatrixColumn": "Coluna da matriz de conversão para verde (CIE XYZ)",
    "BlueMatrixColumn": "Coluna da matriz de conversão para azul (CIE XYZ)",
    "Luminance": "Luminância do espaço de conexão (CIE XYZ)",
    # --- Curvas de transferência (TRC) ---
    "RedTRC": "Curva de transferência do canal vermelho (tone response curve)",
    "GreenTRC": "Curva de transferência do canal verde",
    "BlueTRC": "Curva de transferência do canal azul",
    "GrayTRC": "Curva de transferência para perfis em escala de cinza",
    "TRC": "Curva de transferência genérica",
    # --- Medição e visualização ---
    "MeasurementGeometry": "Geometria de medição (0=desconhecida, 1=0°/45°, 2=45°/0°)",
    "MeasurementIlluminant": "Iluminante de medição (2=D65, 1=D50, etc.)",
    "MeasurementObserver": "Observador padrão (1=2°, 2=10°)",
    "MeasurementBacking": "Cor de fundo na medição (CIE XYZ)",
    "MeasurementFlare": "Flare medido na caracterização",
    "ViewingCondDesc": "Descrição das condições de visualização",
    "ViewingCondIlluminant": "Iluminante nas condições de visualização (CIE XYZ)",
    "ViewingCondSurround": "Nível de surround nas condições de visualização",
    "ViewingCondIlluminantType": "Tipo de iluminante de visualização (1=D50, 2=D65, etc.)",
    # --- Flags e metadados auxiliares ---
    "CMMFlags": "Flags do CMM (geralmente 0)",
    "ChromaticAdaptation": "Matriz de adaptação cromática",
    "Chromaticity": "Cromaticidade das primárias",
    "CharTarget": "Alvo de caracterização usado na criação do perfil",
    "CalibrationDateTime": "Data/hora da calibração do dispositivo",
    "DeviceSettings": "Configurações do dispositivo na criação do perfil",
    "MakeAndModel": "Marca e modelo do dispositivo",
    "NamedColor": "Entrada de cor nomeada no perfil",
    "Preview0": "Tabela de preview 0",
    "Preview1": "Tabela de preview 1",
    "Preview2": "Tabela de preview 2",
    "Ps2CRD0": "Tabela CRD PostScript 0",
    "Ps2CRD1": "Tabela CRD PostScript 1",
    "Ps2CRD2": "Tabela CRD PostScript 2",
    "Ps2CS0": "Espaço de cores PostScript 0",
    "Ps2CS1": "Espaço de cores PostScript 1",
    "Ps2CS2": "Espaço de cores PostScript 2",
    "Ps2RenderingIntent": "Intento de renderização PostScript",
    "ScreeningDesc": "Descrição de screening para impressão",
    "Gamut": "Gamat do dispositivo",
    "AToB0": "Tabela de transformação A→B0 (perceptual/device→PCS)",
    "AToB1": "Tabela de transformação A→B1 (relative colorimetric)",
    "AToB2": "Tabela de transformação A→B2 (saturation)",
    "BToA0": "Tabela de transformação B→A0 (PCS→device perceptual)",
    "BToA1": "Tabela de transformação B→A1 (PCS→device relative)",
    "BToA2": "Tabela de transformação B→A2 (PCS→device saturation)",
}


def _normalize_icc_tag(tag: str) -> str:
    if not tag:
        return ""
    if ":" in tag:
        prefix, local = tag.split(":", 1)
        if prefix.upper().startswith("ICC"):
            return local
        return local
    return tag


def icc_property_hint(tag: str) -> str | None:
    """Resolve significado forense de uma tag ICC/ICC_Profile."""
    if not tag:
        return None
    local = _normalize_icc_tag(tag)
    if local in ICC_PROPERTY_HINTS:
        return ICC_PROPERTY_HINTS[local]
    if tag in ICC_PROPERTY_HINTS:
        return ICC_PROPERTY_HINTS[tag]
    return None
