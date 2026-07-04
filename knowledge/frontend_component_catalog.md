# Frontend Component Catalog — ForensicAuth

## Overview

SPA React 18 + TypeScript, Vite 5, React Router v6, Zustand, TanStack Query.

---

## Pages (`src/frontend/src/pages/`)

| Page | Route(s) | Purpose |
|---|---|---|
| `Login.tsx` | `/login` | Authentication |
| `FirstAccess.tsx` | `/primeiro-acesso` | First-access password setup |
| `Cases.tsx` | `/` | List cases |
| `Dashboard.tsx` | `/dashboard` | Overview of available techniques |
| `CaseForm.tsx` | `/cases/new`, `/cases/:caseId/edit` | Create/edit case |
| `CaseDetail.tsx` | `/cases/:caseId` | Case detail, evidence, analysis |
| `MediaPanels.tsx` | `/analysis` | Legacy analysis hub |
| `Analysis.tsx` | `/analysis/run` | Generic analysis runner |
| `Upload.tsx` | — | Evidence upload (unused standalone) |
| `Users.tsx` | `/users` | User management (admin) |
| `ImageAnalysisGroupPage.tsx` | `/cases/:caseId/analysis/image-group/:groupId` | Grouped image analysis |
| `ELAAnalysis.tsx` | `/cases/:caseId/analysis/ela` | Error Level Analysis |
| `ImageMetadataAnalysis.tsx` | `/cases/:caseId/analysis/image_metadata` | Metadata extraction |
| `DCTQuantization.tsx` | `/cases/:caseId/analysis/dct_quantization` | DCT quantization analysis |
| `ResamplingAnalysis.tsx` | `/cases/:caseId/analysis/resampling` | Resampling detection |
| `PatchMatchAnalysis.tsx` | `/cases/:caseId/analysis/patchmatch` | Copy-move detection |
| `CopyMovePcaAnalysis.tsx` | `/cases/:caseId/analysis/copy_move_pca` | Copy-move PCA |
| `WaveletNoiseResidueAnalysis.tsx` | `/cases/:caseId/analysis/wavelet_noise_residue` | Wavelet noise residue |
| `DoubleCompressionAnalysis.tsx` | `/cases/:caseId/analysis/double_compression` | Double JPEG compression |
| `BagExtractionAnalysis.tsx` | `/cases/:caseId/analysis/bag_extraction` | Blocking artifact grid |
| `ZeroGridAnalysis.tsx` | `/cases/:caseId/analysis/zero_grid` | ZERO grid detection |
| `SyntheticImageDetectionAnalysis.tsx` | `/cases/:caseId/analysis/synthetic_image_detection` | AI-generated image detection |
| `DistilDireAnalysis.tsx` | `/cases/:caseId/analysis/distildire` | DistilDire detection |
| `SafireAnalysis.tsx` | `/cases/:caseId/analysis/safire` | SAFIRE |
| `NoiseprintAnalysis.tsx` | `/cases/:caseId/analysis/noiseprint` | Noiseprint |
| `PresentationAttackDetectionAnalysis.tsx` | `/cases/:caseId/analysis/presentation_attack_detection` | PAD |
| `PRNUAnalysis.tsx` | `/cases/:caseId/analysis/prnu` | PRNU analysis |
| `JpegGhostsAnalysis.tsx` | `/cases/:caseId/analysis/jpeg_ghosts` | JPEG ghosts |
| `JpegStructureCompareAnalysis.tsx` | `/cases/:caseId/analysis/jpeg_structure_compare` | JPEG structure comparison |
| `ImdlBencoHub.tsx` | `/cases/:caseId/analysis/imdlbenco` | IMDL-BenCo hub |
| `ImdlMethodAnalysis.tsx` | `/cases/:caseId/analysis/imdl/:methodId` | IMDL specific method |
| `AudioForensicsHub.tsx` | `/cases/:caseId/analysis/audio` | Audio analysis hub |
| `PDFFontColorAnalysis.tsx` | `/cases/:caseId/analysis/pdf_font_overlay` | PDF font/color overlay |
| `PDFStructureMetricsAnalysis.tsx` | `/cases/:caseId/analysis/pdf_structure_metrics` | PDF structure metrics |
| `PDFStructureSimilarityAnalysis.tsx` | `/cases/:caseId/analysis/pdf_structure_similarity` | PDF similarity |
| `PDFForensicExtractAnalysis.tsx` | `/cases/:caseId/analysis/pdf_forensic_extract` | PDF forensic extraction |
| `VideoFactAnalysis.tsx` | `/cases/:caseId/analysis/videofact` | VideoFact |
| `StilVideoAnalysis.tsx` | `/cases/:caseId/analysis/stil_video_detection` | STIL video detection |
| `LowResFakeVideoAnalysis.tsx` | `/cases/:caseId/analysis/lowres_fake_video` | Low-res fake video |
| `IsoMediaStructureAnalysis.tsx` | `/cases/:caseId/analysis/isomedia_parser` | ISO BMFF parser |
| `IsoMediaSimilarityAnalysis.tsx` | `/cases/:caseId/analysis/isomedia_compare` | ISO BMFF similarity |
| `ClipBasedAnalysis.tsx` | `/cases/:caseId/analysis/clipbased_synthetic` | CLIP-based synthetic |
| `FakeVlmAnalysis.tsx` | `/cases/:caseId/analysis/fakevlm` | FakeVLM |

## Core Components (`src/frontend/src/components/`)

| Component | Purpose |
|---|---|
| `Layout.tsx` | Application shell with navbar |
| `ProtectedRoute.tsx` | Route guard requiring authentication |
| `AuthBootstrap.tsx` | Restore session on app load |
| `EvidenceDropZone.tsx` | Drag-and-drop upload zone |
| `EvidenceFileGrid.tsx` | Grid of evidence files |
| `EvidenceThumbnail.tsx` | Evidence thumbnail |
| `EvidenceFilePreview.tsx` | File preview modal |
| `CaseAnalysisPanels.tsx` | Analysis selection panels per media type |
| `CaseSharePanel.tsx` | Case sharing UI |
| `CustodyPanel.tsx` | Custody chain visualization |
| `DerivativesPanel.tsx` | Derivative evidences |
| `DerivationDagView.tsx` / `DerivationGraphModal.tsx` | Lineage graph |
| `JobArtifactImageThumb.tsx` | Job result thumbnail |
| `TechniqueConfig.tsx` | Parameter configuration |
| `ZoomableImageViewer.tsx` | Pan/zoom image viewer |
| `SyncedImagePairViewer.tsx` | Side-by-side image comparison |
| `PolygonRoiCanvas.tsx` / `RectRoiCanvas.tsx` | ROI drawing |
| `SpectrogramPlot.tsx` | Audio spectrogram |
| `AudioOverlayPlot.tsx` | Audio trace overlay |
| `PlotlyChartFrame.tsx` / `PlotlyHtmlFrame.tsx` | Plotly rendering |
| `VideoPlayer.tsx` | Video playback |

## Notes

- Most analysis pages use `AnalysisPageShell.tsx` for consistent layout.
- `ImageLegacyAnalysisRedirect.tsx` redirects legacy per-technique routes to grouped media view.
- `MediaPanels.tsx` and `Analysis.tsx` are legacy/alternative routes kept for compatibility.
