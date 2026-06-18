import type { MetadataTag } from "@/components/metadata/MetadataTagTable";
import type { MetadataTabId } from "@/components/metadata/metadataTabConfig";

const DESCRIPTIONS: Record<MetadataTabId, string> = {
  overview: "Alertas automáticos e campos prioritários para análise forense inicial.",
  exif: "Metadados TIFF/EXIF embutidos no arquivo (captura, câmera, datas internas).",
  makernotes: "Bloco proprietário do fabricante decodificado pelo ExifTool.",
  xmp: "Pacote XMP estruturado — histórico de edição, namespaces e árvore RDF/XML.",
  adobe: "Recursos Photoshop, Camera Raw, Lightroom e flags Adobe.",
  iptc: "Metadados editoriais IPTC (legenda, direitos, palavras-chave).",
  icc: "Perfil de cor ICC embutido e tags de caracterização.",
  jpeg: "Marcadores, quantização, Huffman e componentes do bitstream JPEG.",
  other: "Tags complementares (arquivo, composite, trailer) não classificadas acima.",
};

function collectSources(entries: MetadataTag[]): string {
  const parts = new Set<string>();
  for (const e of entries) {
    if (!e.source) continue;
    for (const s of e.source.split("+")) {
      if (s.trim()) parts.add(s.trim());
    }
  }
  return [...parts].join(" + ") || "—";
}

export function metadataSectionDescription(tabId: MetadataTabId): string {
  return DESCRIPTIONS[tabId];
}

export function metadataSectionMeta(
  tabId: MetadataTabId,
  ctx: {
    families: Record<string, MetadataTag[] | undefined>;
    summary: Record<string, unknown>;
    xmpPropertyCount?: number;
    jpegMarkerCount?: number;
  }
): string | undefined {
  const { families, summary, xmpPropertyCount, jpegMarkerCount } = ctx;
  switch (tabId) {
    case "overview": {
      const engines = summary.metadata_engines as string[] | undefined;
      const eng = engines?.length ? engines.join(" + ") : String(summary.metadata_engine || "—");
      return `Motores: ${eng}`;
    }
    case "exif": {
      const n = families.exif?.length ?? 0;
      return `${n} campo(s) · fontes: ${collectSources(families.exif || [])}`;
    }
    case "iptc": {
      const n = families.iptc?.length ?? 0;
      return `${n} campo(s) · fontes: ${collectSources(families.iptc || [])}`;
    }
    case "xmp": {
      const flat = families.xmp?.length ?? 0;
      const pkt = xmpPropertyCount ?? 0;
      return pkt > 0
        ? `${pkt} propriedade(s) no pacote · ${flat} tag(s) ExifTool`
        : `${flat} tag(s) ExifTool`;
    }
    case "icc": {
      const n = families.icc?.length ?? 0;
      return `${n} tag(s) ICC · perfil embutido: ${summary.has_icc ? "sim" : "não"}`;
    }
    case "makernotes": {
      const n = families.makernotes?.length ?? 0;
      return `${n} campo(s) · fontes: ${collectSources(families.makernotes || [])}`;
    }
    case "adobe": {
      const n = families.adobe?.length ?? 0;
      return `${n} campo(s) · fontes: ${collectSources(families.adobe || [])}`;
    }
    case "jpeg": {
      if (!summary.jpeg_structure_available) return undefined;
      return `${jpegMarkerCount ?? 0} marcador(es) · Q:${summary.quantization_table_count} · Huff:${Number(summary.huffman_dc_count) + Number(summary.huffman_ac_count)}`;
    }
    case "other": {
      const n = families.other?.length ?? 0;
      return `${n} campo(s)`;
    }
    default:
      return undefined;
  }
}
