# Migração Streamlit → Next.js (`investa`) — Design (guarda-chuva)

**Data:** 2026-05-01
**Status:** Spec aprovada (aguardando review final)
**Repo destino:** `logomes/investa` (novo, monorepo)

## Sobre este documento

Este é um **spec guarda-chuva** que descreve a migração inteira. O esforço (~12 dias) é grande demais para um único plano de implementação executável. A migração foi decomposta em **sub-projetos** (Fase 1 a Fase 6 abaixo), e **cada sub-projeto terá seu próprio ciclo spec → plano → implementação** quando chegar a vez de ser executado.

O **primeiro sub-projeto** (a ser planejado imediatamente após este spec ser aprovado) é a **Fase 1 — Infra & API**. As fases seguintes serão brainstormadas e planejadas conforme cada uma chegar à fila.

## Objetivo

Migrar o dashboard atual `dashboard-investimentos` (Streamlit/Python) para uma stack web moderna (Next.js + FastAPI) com paridade funcional total e a UI definida no design handoff (`docs/design-handoff/`).

A motivação não é técnica — o Streamlit cumpre seu papel — mas visual: o handoff entrega um design de altíssima fidelidade (dark mode fintech, paleta teal/coral, sidebar nav, KPIs custom, charts SVG artesanais) que o Streamlit não consegue reproduzir devido a restrições do framework.

## Decisões de design

| # | Decisão | Justificativa |
|---|---------|---------------|
| 1 | Público sem login. Estado do usuário em `localStorage` | Mantém a vibe demo/portfólio do Streamlit atual; sem complexidade de auth/banco |
| 2 | Charts SVG portados de `charts.jsx` (handoff) para TS | Preserva fidelidade pixel-perfect ao mock; zero dependência de chart lib; ~6 componentes pequenos |
| 3 | Paridade funcional total antes de virar a chave | Switch limpo do Streamlit pro Next.js, sem usuário em limbo |
| 4 | Repo novo: `logomes/investa` | Coerente com branding do mock ("investa | análise patrimonial"); deixa o repo atual como histórico |
| 5 | Backend = port direto de `models.py` | YAGNI — engine funciona, 23 testes passam intactos. Refactor só se necessário depois |
| 6 | Renda Fixa = design-rich (Duration média, Por indexador, Calendário) | Mock entrega mais widgets que a versão Streamlit; vale o ~½ dia extra |
| 7 | Vercel (web) + Render (api), free tier | Mesmo modelo "push GitHub → deploy" do Streamlit Cloud atual; zero infra pra administrar |

## Stack

| Camada | Tecnologias |
|---|---|
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS, react-hook-form + zod, TanStack Query, Zustand (com `persist`) |
| Backend | Python 3.12, FastAPI, Pydantic v2, uvicorn |
| Engine de simulação | Reuso direto de `config.py` + `models.py` + `services/macro.py` do projeto Streamlit |
| Charts | SVG portados de `charts.jsx` (handoff), zero deps |
| Tests | pytest (api), Vitest (componentes web), Playwright (smoke E2E) |
| CI/CD | GitHub Actions, Vercel (web), Render (api) |

## 1. Estrutura do repo

```
investa/
├── api/                              # Python 3.12 / FastAPI
│   ├── main.py                       # FastAPI app + CORS + routers
│   ├── routers/
│   │   ├── macro.py
│   │   ├── simulation.py
│   │   └── fixed_income.py
│   ├── schemas/
│   │   ├── inputs.py                 # Pydantic input models
│   │   └── outputs.py                # Pydantic output models
│   ├── core/                         # migrado intacto do Streamlit
│   │   ├── config.py
│   │   ├── models.py
│   │   └── services/macro.py
│   ├── tests/                        # 23 existentes + ~5 integração
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── render.yaml                   # infra-as-code do Render
│
├── web/                              # Next.js 14 + TS
│   ├── app/
│   │   ├── layout.tsx                # Shell: Sidebar + Topbar + Drawer
│   │   ├── globals.css
│   │   ├── page.tsx                  # / → Visão Geral
│   │   ├── imovel/page.tsx
│   │   ├── carteira/page.tsx
│   │   ├── sensibilidade/page.tsx
│   │   ├── tributacao/page.tsx
│   │   ├── risco/page.tsx
│   │   ├── exportar/page.tsx
│   │   └── renda-fixa/page.tsx
│   ├── components/
│   │   ├── shell/
│   │   │   ├── Sidebar.tsx
│   │   │   ├── Topbar.tsx
│   │   │   └── ScenarioDrawer.tsx
│   │   ├── ui/                       # Card, Pill, Button, Tabs, Table, KpiCard
│   │   └── charts/                   # 6 chart primitives portados
│   │       ├── LineChart.tsx
│   │       ├── Donut.tsx
│   │       ├── Tornado.tsx
│   │       ├── Histogram.tsx
│   │       ├── Waterfall.tsx
│   │       └── Heatmap.tsx
│   ├── lib/
│   │   ├── api.ts                    # fetch wrappers + TanStack Query setup
│   │   ├── types.ts                  # TS espelhando Pydantic schemas
│   │   ├── store.ts                  # Zustand stores (scenario, fi-positions)
│   │   └── storage.ts                # localStorage helpers
│   ├── tests/
│   │   ├── components/               # Vitest unit tests
│   │   └── e2e/                      # Playwright smoke
│   ├── tailwind.config.ts
│   ├── next.config.mjs
│   ├── package.json
│   └── vercel.json                   # opcional
│
├── docs/
│   ├── architecture.md
│   ├── deployment.md
│   └── design-handoff/               # README + 8 screenshots do mock
│
├── .github/workflows/
│   ├── api-ci.yml                    # pytest
│   └── web-ci.yml                    # tsc + vitest + playwright (smoke only)
│
├── docker-compose.yml                # opcional para dev local
├── .gitignore
└── README.md
```

**Sem Turborepo / Nx / pnpm workspaces.** Dois pacotes independentes (Python e Node), pouca interdependência. Vercel e Render leem subdir nativamente.

## 2. Contrato da API

Cinco endpoints. Todos retornam `{ apiVersion: "1.0.0", data: {...} }` para versionamento futuro.

```
GET  /api/health
       → { status: "ok", version: "1.0.0" }

GET  /api/macro
       → { selic, cdi, ipca, usdBrl, sourceLabel, isStale }
       Cache server-side: 1h. Fallback hardcoded se BCB falhar.

GET  /api/portfolio/defaults
       → { realEstate, portfolio, benchmark }
       Cenário base que alimenta o form no primeiro carregamento.

POST /api/simulate
       Body: { capital, horizon, reinvest, realEstate, portfolio, benchmark }
       → { realEstate: SimulationResult,
           portfolio: SimulationResult,
           benchmark: SimulationResult,
           sensitivity: SensitivityRow[],
           taxComparison: TaxRow[] }
       ~100ms. Síncrono.

POST /api/simulate/monte-carlo
       Body: { realEstate, portfolio, horizon, mc: { nTrajectories, seed, targetPatrimony } }
       → { realEstate: MonteCarloResult, portfolio: MonteCarloResult }
       ~3-8s com nTrajectories=10000. Frontend dispara em paralelo com /simulate.

POST /api/fixed-income/simulate
       Body: { positions: FixedIncomePosition[], horizonYears, startDate? }
       → FixedIncomePortfolio (serializado: arrays viram listas)
```

### CORS

Allowlist:
- `https://investa.vercel.app`
- `http://localhost:3000` (dev)

Sem credentials, sem cookies — apenas leitura simulação.

### Erros

Padrão consistente:
```json
{
  "error": "validation_failed",
  "message": "horizon must be between 1 and 30",
  "details": { "field": "horizon", "received": 50 }
}
```

| Status | Quando |
|---|---|
| 400 | Validação Pydantic falhou |
| 502 | BCB indisponível — devolve fallback com `isStale: true` (não falha) |
| 500 | Inesperado (capturado no FastAPI exception handler) |

## 3. Frontend

### Layout shell (`app/layout.tsx`)

```tsx
<body>
  <QueryProvider>
    <ScenarioProvider>           {/* Zustand: parâmetros atuais, persist */}
      <FixedIncomeProvider>      {/* Zustand: posições RF, persist */}
        <div className="flex">
          <Sidebar />              {/* 240px fixa, 8 nav items + user card */}
          <main className="flex-1">
            <Topbar />             {/* 64px com busca + CTA "Simular cenário" */}
            <div className="content">{children}</div>
          </main>
        </div>
        <ScenarioDrawer />        {/* off-canvas com form de inputs */}
      </FixedIncomeProvider>
    </ScenarioProvider>
  </QueryProvider>
</body>
```

### State management

| Estado | Lib | Persistência |
|---|---|---|
| Parâmetros do cenário | Zustand + `persist` | localStorage |
| Posições de Renda Fixa | Zustand + `persist` | localStorage (chave `fi_positions`) |
| Resposta de `/api/simulate*` | TanStack Query | cache em memória; key = JSON dos inputs |
| Macro (BCB) | TanStack Query (`staleTime: 1h`) | matches o cache do server |
| Filtros locais (1A/5A/10A) | `useState` | efêmero |

### Form do drawer "Simular cenário"

`react-hook-form` + `zod`. Campos espelham o sidebar do Streamlit hoje:
- capital, horizonte, reinvest
- RealEstate: monthly_rent, annual_appreciation, iptu_rate, vacancy, mgmt_fee, ir_bracket, financing toggle + termos
- Portfolio: assets list (weight/yield/capital_gain/tax_rate), monthly_contribution, indexed
- Benchmark: selic_rate
- MC: target_patrimony, n_trajectories, seed

Submit fecha drawer, persiste no Zustand, invalida queries → todas as abas re-renderizam.

### Tokens da paleta (`tailwind.config.ts`)

```ts
colors: {
  bg: { 0: "#050a0d", 1: "#0a1216", 2: "#121e24", 3: "#1a2a32", 4: "#233640" },
  ink: { DEFAULT: "#eaf6f4", 2: "#b6cdca", 3: "#7d9591", 4: "#506663" },
  brand: { DEFAULT: "#00b894", bright: "#2af0c4" },
  accent: {
    coral: "#ff6b5b",
    cyan: "#5cc8ff",
    green: "#46e8a4",
    red: "#ff5d72",
    amber: "#ffc857",
  },
}
```

Renomear `--purple*` do CSS handoff → `brand*` (handoff explicita que era de iteração antiga).

### Componentes UI atômicos

| Componente | Spec resumido |
|---|---|
| `<Card>` | bg-2, border `line`, radius 16, padding 18×20 (default) ou 14×16 (tight) |
| `<Pill>` | variants `brand` `green` `red` `amber` `cyan` `ghost`; radius 999; padding 4×10 |
| `<Button>` | `primary` (gradiente brand→bright + glow shadow) ou `ghost` (bg-2 + border) |
| `<KpiCard>` | label + value (26px/700) + delta (+/−) + sub; opcional `feature` (gradiente teal de fundo) |
| `<Tabs>` | segmented control: bg-2 + border + radius 12 + padding interno 4 |
| `<Table>` | header 11px/600/uppercase/letter-spacing 0.06em; row hover bg-3; `<td>` com `font-feature-settings: 'tnum'` |

### Charts (já decidido em decisão #2)

`web/components/charts/` com 6 arquivos TS portados de `charts.jsx` do handoff. API consistente: cada componente recebe `data` + `width/height` + props de tematização (`axisColor`, `gridColor`).

## 4. Deployment & CI

### Vercel (web)

- Import repo, Root Directory = `web`, framework = Next.js (auto)
- Auto-deploy em push pra `main`; preview deploys em PRs
- Env: `NEXT_PUBLIC_API_URL=https://investa-api.onrender.com`
- Domínio: `investa.vercel.app` (free)

### Render (api)

- Web Service, Root Directory = `api`, Runtime = Python 3.12
- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health check: `/api/health`
- Plan: free (cold start ~30s) ou Hobby ($7/mês)
- Auto-deploy em push pra `main`

### `render.yaml` (commitado no repo)

```yaml
services:
  - type: web
    name: investa-api
    runtime: python
    rootDir: api
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /api/health
    plan: free
```

### GitHub Actions

**`api-ci.yml`** (trigger: changes em `api/**`):
1. setup-python@v5, version 3.12
2. `pip install -r api/requirements.txt`
3. `pytest api/tests/ -v`

**`web-ci.yml`** (trigger: changes em `web/**`):
1. setup-node@v4, version 20
2. `pnpm install --frozen-lockfile` (em `web/`)
3. `pnpm tsc --noEmit`
4. `pnpm vitest run`
5. `pnpm playwright test --grep smoke`

Branch protection em `main`: requer CI verde.

## 5. Fases de migração

| # | Fase | Esforço | Critério de "done" |
|---|---|---|---|
| 1 | Infra & API | 1 dia | `curl https://investa-api.onrender.com/api/health` retorna 200; `/api/macro` retorna Selic real; 23+ testes passam |
| 2 | Web shell + tokens | 1 dia | `https://investa.vercel.app` mostra shell idêntico ao mock; nav entre 8 abas vazias funciona |
| 3 | Primitivos + 1º chart | 2 dias | Drawer abre/fecha, form valida, 1 KPI + 1 LineChart na home consomem `/api/simulate` |
| 4 | Visão Geral end-to-end | 2 dias | Aba `/` igual ao mock 01-visao-geral.png, dados reais |
| 5.1 | Imóvel | 1 dia | Aba `/imovel` igual ao mock 02 |
| 5.2 | Carteira | 1 dia | Aba `/carteira` igual ao mock 03 |
| 5.3 | Sensibilidade | 1 dia | Aba `/sensibilidade` igual ao mock 04 |
| 5.4 | Tributação | 1 dia | Aba `/tributacao` igual ao mock 05 |
| 5.5 | Risco MC | 1 dia | Aba `/risco` igual ao mock 06 |
| 5.6 | Exportar | 1 dia | Aba `/exportar` igual ao mock 07 |
| 5.7 | Renda Fixa | 1 dia | Aba `/renda-fixa` igual ao mock 08, design-rich (Duration, Por indexador, Calendário) |
| 6 | Smoke + cutover | 1 dia | Playwright smoke passa; manual smoke das 8 abas; README do Streamlit aponta pro novo |

**Total: ~12 dias úteis (~2 semanas).**

## Critério de aceitação global

1. Os 23+ testes pytest passam em `api/`
2. `pnpm tsc --noEmit` + `pnpm vitest run` + `pnpm playwright test --grep smoke` passam em `web/`
3. As 8 abas em produção (Vercel) renderizam fielmente os 8 mocks do design handoff
4. Os números (KPIs, charts, tabelas) batem com o Streamlit atual ±0,01 para o cenário base
5. CSV import/export do Renda Fixa funciona (mesmo formato do Streamlit, compatível)
6. Macro do BCB carrega e mostra fallback quando indisponível

## Fora de escopo desta migração

- Autenticação / multi-usuário
- Banco de dados / persistência server-side
- Internacionalização (continua só pt-BR)
- Mobile-first responsive (alvo é desktop ≥1280px conforme handoff; mobile fica como melhoria futura)
- Modal de "Aplicar sugestão" do Goal card (botão fica visível mas é placeholder)
- Notificações na topbar (sino + dot são decorativos)
- Animações de entrada/transição além do trivial (CSS hover/focus)
