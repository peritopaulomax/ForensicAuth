# Frontend Summary — ForensicAuth

**Atualizado:** 2026-07-04

## Stack

React 18 + TypeScript + Vite + Zustand + Axios + Playwright

## Rotas principais

| Rota | Página |
|---|---|
| `/`, `/cases/:id` | Casos |
| `/cases/:id?tab=analises` | Painéis por mídia |
| `/cases/:id/analysis/image-group/:groupId` | Hub imagem (7 grupos) |
| `/cases/:id/analysis/audio` | Hub espectral (ENF, LTAS, etc.) |
| `/cases/:id/analysis/audio_spoofing` | **Spoofing multi-detector** |
| `/cases/:id/analysis/:technique` | PDF, vídeo, técnicas dedicadas |

## Config

- `imageAnalysisGroups.ts` — grupos e visibilidade
- `imageTechniqueRegistry.tsx` — lazy load de páginas
- `forensicTechniqueMeta.ts` — citações ABNT, subtítulos
- `caseAnalysisNav.ts` — navegação dedicada vs hub

## Grupos imagem

`estrutura-arquivo`, `classicas-compressao`, `classicas-correlacao`, `classicas-aquisicao`, `dl-manipulacao`, `dl-sintetico`, `biometria-facial`

## Áudio

- **Espectral:** tabs em `AudioForensicsHub`
- **Spoofing:** checkboxes DF Arena / SLS / WeDefense em `AudioSpoofingAnalysis`

## Testes frontend

- Vitest: ~26 testes (`*.test.ts`)
- Playwright: 10 specs incl. `audio-spoofing-detectors.spec.ts`, `synthetic-new-detectors.spec.ts`

## Dívidas UI

Rotas legadas redirecionam; hub IMDL removido; páginas grandes; cobertura testes baixa
