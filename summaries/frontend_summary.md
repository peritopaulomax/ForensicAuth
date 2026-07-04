# Frontend Summary — ForensicAuth

## O que é

SPA React para peritos interagirem com a plataforma forense.

## Stack

- React 18 + TypeScript
- Vite 5
- React Router v6
- Zustand (auth)
- TanStack Query (uso parcial)
- Axios + JWT
- Vitest + React Testing Library + Playwright

## Estrutura

```text
src/
├── pages/       → rotas React Router (~18,6k linhas TS/TSX)
├── components/  → componentes reutilizáveis e de domínio
├── services/    → clientes Axios
├── store/       → Zustand auth
├── hooks/       → hooks customizados
├── config/      → registro de técnicas forenses
├── lib/         → helpers puros
└── types/       → tipos TypeScript
```

## Rotas principais

- `/login`, `/primeiro-acesso`
- `/` (casos), `/dashboard`, `/cases/new`, `/cases/:caseId`
- `/cases/:caseId/analysis/image-group/:groupId`
- `/cases/:caseId/analysis/:tecnica` (rotas legadas redirecionadas para agrupamento por mídia)
- `/users` (admin)
- `/analysis` e `/analysis/run` (rotas alternativas legadas apontando para `MediaPanels` e `Analysis`)

## Fluxos de usuário

1. Login → token no localStorage → lista de casos
2. Criar caso → upload de evidência → aba análises
3. Selecionar técnica → ajustar parâmetros → submeter job → polling
4. Visualizar artefatos → salvar derivado → cadeia de custódia
5. Exportar/importar VCP ou Peritus
6. Fechar caso → assinaturas obrigatórias

## Riscos

- Token em localStorage (XSS)
- Páginas muito grandes (`CaseDetail.tsx`: ~1494 linhas, `AudioForensicsHub.tsx`: ~1262 linhas)
- TanStack Query subutilizado
- Tratamento de erro com `any`
- Polling longo sem WebSocket/retry
- Rotas legadas extensas e fragmentadas
- Fonte Google Fonts externa (viola RNF-01 offline)
- Teste `caseAnalysisNav.test.ts` quebrado por rota desatualizada

## Dívidas

- Cobertura de testes insuficiente em páginas/hooks (~15 arquivos de teste)
- E2E com mocks estáticos
- Roteamento legado extenso
- Sem i18n
- Estilização misturada (CSS global + inline) sem design system
- Componentes grandes com estado local excessivo

## Confiabilidade

Média — funcional, mas com débito de manutenibilidade e testes.
