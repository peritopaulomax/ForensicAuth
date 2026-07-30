import { describe, it, expect } from "vitest";
import {
  AUDIO_ANALYSIS_GROUPS,
  VIDEO_ANALYSIS_GROUPS,
  PDF_ANALYSIS_GROUPS,
  MEDIA_GROUP_CATALOG,
  getMediaAnalysisGroup,
  findMediaGroupForTechnique,
  resolveMediaTechniqueTabLabel,
} from "./mediaAnalysisGroups";

describe("mediaAnalysisGroups", () => {
  it("exposes canonical audio/video/pdf group ids", () => {
    expect(MEDIA_GROUP_CATALOG.audio.map((g) => g.id)).toEqual([
      "audio-forense",
      "audio-estrutura",
      "audio-spoofing",
    ]);
    expect(MEDIA_GROUP_CATALOG.video.map((g) => g.id)).toEqual([
      "video-estrutura",
      "video-manipulacao",
    ]);
    expect(MEDIA_GROUP_CATALOG.pdf.map((g) => g.id)).toEqual(["pdf-estrutura", "pdf-conteudo"]);
  });

  it("uses a single audio forensics hub card", () => {
    const hub = getMediaAnalysisGroup("audio", "audio-forense");
    expect(hub?.techniques.map((t) => t.id)).toEqual(["__audio_hub__"]);
    expect(getMediaAnalysisGroup("audio", "audio-espectral")?.id).toBe("audio-forense");
    expect(getMediaAnalysisGroup("audio", "audio-niveis")?.id).toBe("audio-forense");
  });

  it("finds techniques across media catalogs", () => {
    expect(findMediaGroupForTechnique("videofact")?.group.id).toBe("video-manipulacao");
    expect(findMediaGroupForTechnique("truvil")?.group.id).toBe("video-manipulacao");
    expect(findMediaGroupForTechnique("vilocal")?.group.id).toBe("video-manipulacao");
    expect(findMediaGroupForTechnique("pdf_forensic_extract")?.group.id).toBe("pdf-conteudo");
    expect(findMediaGroupForTechnique("audio_spoofing_detection")?.group.id).toBe("audio-spoofing");
    expect(findMediaGroupForTechnique("mp3_parser")?.group.id).toBe("audio-estrutura");
    expect(findMediaGroupForTechnique("opus_parser")?.group.id).toBe("audio-estrutura");
    expect(findMediaGroupForTechnique("audio_enf")?.group.id).toBe("audio-forense");
    expect(findMediaGroupForTechnique("__audio_hub__")?.group.id).toBe("audio-forense");
  });

  it("audio container parsers use human tab labels", () => {
    const group = getMediaAnalysisGroup("audio", "audio-estrutura");
    expect(group).toBeTruthy();
    const labels = group!.techniques.map((e) => resolveMediaTechniqueTabLabel(e));
    expect(labels).toEqual(["Metadados", "Parser MP3", "Parser Opus"]);
  });

  it("finds audio metadata in estrutura group", () => {
    expect(findMediaGroupForTechnique("audio_metadata")?.group.id).toBe("audio-estrutura");
  });

  it("pdf group techniques use human tab labels", () => {
    const group = getMediaAnalysisGroup("pdf", "pdf-estrutura");
    expect(group).toBeTruthy();
    const labels = group!.techniques.map((e) => resolveMediaTechniqueTabLabel(e));
    expect(labels).toContain("Estrutura e métricas");
    expect(labels).toContain("Similaridade estrutural");
    expect(labels.every((l) => !l.startsWith("pdf_"))).toBe(true);
  });

  it("video estrutura includes metadata tab", () => {
    const group = getMediaAnalysisGroup("video", "video-estrutura");
    expect(group).toBeTruthy();
    const labels = group!.techniques.map((e) => resolveMediaTechniqueTabLabel(e));
    expect(labels).toEqual(["Metadados", "Parser ISO BMFF", "Similaridade ISO BMFF"]);
    expect(findMediaGroupForTechnique("video_metadata")?.group.id).toBe("video-estrutura");
  });

  it("applies empty scaffold hooks without dropping base groups", () => {
    expect(AUDIO_ANALYSIS_GROUPS.length).toBeGreaterThanOrEqual(3);
    expect(VIDEO_ANALYSIS_GROUPS.length).toBeGreaterThanOrEqual(2);
    expect(PDF_ANALYSIS_GROUPS.length).toBeGreaterThanOrEqual(2);
  });
});
