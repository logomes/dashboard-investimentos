# Phase 2 (sub-projeto 2) — Análise estocástica (Monte Carlo)

**Data:** 2026-04-26
**Status:** Aprovado
**Escopo:** Camada paralela de simulação Monte Carlo para Carteira (per-asset volatility) e Imóvel (appreciation volatility). Caminho determinístico (Phase 1) permanece intocado. Phase 2 tem 3 sub-projetos independentes; este é o segundo (após financiamento). Salvar/comparar virá em sub-projeto 3.

## Objetivo

Adicionar análise estocástica ao dashboard sem quebrar nada do determinístico:

1. **Carteira** estocástica per-asset (cada classe tem σ próprio).
2. **Imóvel** estocástico (σ na valorização anual). Aluguel cresce com a apreciação sorteada — segue o modelo Phase 1.
3. **Imóvel financiado**: parcela continua determinística (taxa fixa contratualmente); carteira interna fica estocástica seguindo a Carteira da mesma trajetória.
4. **UI**: nova aba "🎲 Risco" + banda p10/p50/p90 sobreposta nos gráficos de patrimônio existentes.
5. **Reprodutibilidade**: seed fixa (default 42), N=10.000 fixo. Cada interação re-simula em <100ms.

## Decisões de produto

| # | Decisão | Razão |
|---|---|---|
| 1 | Carteira (per-asset) + Imóvel (valorização) estocásticos; aporte determinístico | Comparação justa sob risco; aporte vem de IPCA (determinístico no BCB). |
| 2 | Volatilidades hardcoded por classe com sliders pra sobrescrever | Default funciona out-of-box; usuário avançado override. |
| 3 | Nova aba "🎲 Risco" + banda nos gráficos existentes | Mantém abas atuais limpas; conteúdo técnico isolado. |
| 4 | N=10.000 fixo, seed=42 fixa, sem cache | Reprodutível; performance ~50ms por simulação; sem complexidade de hash de params. |
| 5 | Distribuição normal por ativo, draws independentes | MVP. Caudas finas e diversificação superestimada são limitações documentadas. |
| 6 | Trajetórias anuais (não mensais) no MC | Performance + simplicidade. Mensal só relevante pra cash flow do financiamento, que continua determinístico. |
| 7 | `simulate_real_estate_mc(financed)` exige `portfolio_for_internal` | Carteira interna estocástica precisa do `PortfolioParams` da mesma trajetória. |

## Arquitetura

```
dashboard/
├── app.py              # nova aba "🎲 Risco" + banda p10/p90 + sidebar volatility sliders
├── config.py           # NOVO MonteCarloParams + volatility em AssetClass + appreciation_volatility em RealEstateParams
├── models.py           # NOVO MonteCarloResult, simulate_portfolio_mc, simulate_real_estate_mc, helpers
├── charts.py           # NOVO patrimony_band_chart, distribution_histogram_chart
├── data_sources/       # (sem mudanças)
├── services/           # (sem mudanças)
└── tests/
    └── test_monte_carlo.py    # NOVO — propriedades estatísticas + invariantes
```

### Modelo de dados

```python
# config.py — extensões

@dataclass(slots=True)
class AssetClass:
    name: str
    weight: float
    expected_yield: float
    capital_gain: float = 0.0
    tax_rate: float = 0.0
    note: str = ""
    volatility: float = 0.15   # NOVO — σ anual do retorno total

# Defaults históricos:
#   FIIs Papel: 0.14
#   FIIs Tijolo: 0.16
#   Ações BR Dividendos: 0.27
#   Aristocrats US: 0.18
#   Tesouro IPCA+/LCI: 0.05

# RealEstateParams ganha:
appreciation_volatility: float = 0.10

# Novo dataclass (frozen, consistente com Phase 1/2):
@dataclass(slots=True, frozen=True)
class MonteCarloParams:
    n_trajectories: int = 10_000
    seed: int = 42
    target_patrimony: float = 0.0   # 0 desativa cálculo de prob de bater meta
```

```python
# models.py — novo dataclass

@dataclass(slots=True, frozen=True)
class MonteCarloResult:
    trajectories: np.ndarray         # (N, horizon+1)
    percentiles: dict                # {"p10","p50","p90"} — cada um (horizon+1,)
    final_distribution: np.ndarray   # (N,)
    max_drawdowns: np.ndarray        # (N,)
    label: str
    color: str

    def prob_target(self, target: float) -> float:
        return float((self.final_distribution >= target).mean())
```

### Fluxo de dados

```
Sidebar (volatility sliders + target + N fixo + seed fixa)
    │
    ▼
main() — roda DETERMINÍSTICO (existente) E MONTE CARLO em paralelo
    │
    ├─→ determinístico → KPIs Visão Geral, sensibilidade, tabelas, exportação
    │
    └─→ MC: simulate_portfolio_mc, simulate_real_estate_mc
            │
            ├─→ patrimony_band_chart (banda p10–p90 + linha p50) sobreposto no overview
            │
            └─→ aba "🎲 Risco":
                    ├── KPIs (prob meta, drawdown médio, p10/p50/p90 ano final)
                    ├── distribution_histogram_chart por cenário
                    └── banda dedicada
```

**Princípio de isolamento:** caminho determinístico permanece intocado. MC é camada paralela que reaproveita os mesmos `params`. Helpers MC (draws, percentiles, drawdowns) são puros e testáveis.

## Componentes

### `config.py`

- Adicionar `volatility: float = 0.15` em `AssetClass`. Atualizar defaults da lista padrão de `PortfolioParams.assets` com volatilidades históricas listadas acima.
- Adicionar `appreciation_volatility: float = 0.10` em `RealEstateParams` (após `acquisition_cost_pct`, antes de `financing`).
- Adicionar `MonteCarloParams` (frozen).

### `models.py`

Helpers puros:
```python
def _draw_normal_returns(rng, mean, sigma, shape) -> np.ndarray
def _compute_percentiles(trajectories) -> dict
def _compute_max_drawdowns(trajectories) -> np.ndarray
```

`simulate_portfolio_mc(params, horizon, mc_params, ipca=0.0)`:
- Cada ano, cada ativo retorna `N(net_return_i, volatility_i²)` independente.
- Portfolio return ano t = `Σ weight_i × return_i_t`.
- Patrimônio: `cap × cumprod(1 + r_t) + aportes`. Aporte determinístico per Phase 1 (IPCA-indexed se ligado).
- Returns `MonteCarloResult` com label "Carteira (MC)" e cor "#27AE60".

`simulate_real_estate_mc(params, horizon, mc_params, capital_initial=None, portfolio_for_internal=None)`:
- **À vista** (`financing is None`): `appreciation_t ~ N(μ, σ²)`. Property value cresce per trajectory. Aluguel reinvestido na taxa `(net_yield + appreciation_t)` — taxa stochastic per ano. Patrimônio = property + accumulated rent.
- **Financiado** (`financing != None`): exige `portfolio_for_internal`. Schedule de amortização determinístico (parcela fixa por contrato). Internal portfolio cresce a cada ano com retorno blended estocástico da Carteira da mesma trajetória (using `_draw_normal_returns` com `portfolio_for_internal.assets`). Net cash flow = annual_rent_net (estocástico via appreciation) − parcela − seguro. Patrimônio = property − debt + internal.
- Returns `MonteCarloResult` com label "Imóvel (MC)" e cor "#C0392B".
- Erro: `simulate_real_estate_mc(financed_params, ..., portfolio_for_internal=None)` → `ValueError`.

Seed offset: Carteira usa `seed`; Imóvel usa `seed + 1` — streams independentes mas determinísticos.

### `charts.py`

```python
def patrimony_band_chart(
    mc_results: list[MonteCarloResult],
    deterministic_results: list[SimulationResult] | None = None,
) -> go.Figure:
    """Banda p10–p90 sombreada + linha p50 por cenário.

    Quando `deterministic_results` é fornecido, sobrepõe linhas sólidas
    correspondentes (mesma cor, sem sombra). Pareamento por ordem da lista.
    """
```
- Sombras com `fill="tonexty"` entre traces p10 e p90 do mesmo cenário.
- Linha p50 sólida da banda; linha determinística (se fornecida) tracejada.
- Cores dos cenários consistentes com determinístico (PALETTE).
- Adota `_LAYOUT_DEFAULTS` da Phase 2 financing.

```python
def distribution_histogram_chart(mc_result: MonteCarloResult, target: float = 0.0) -> go.Figure:
    """Histograma da distribuição final do patrimônio. Linha vertical na meta se target > 0."""
```

### `app.py`

**Sidebar** (rodapé, antes de "Recarregar dados macro"):

```python
st.sidebar.markdown("---")
st.sidebar.subheader("🎲 Análise estocástica")
target_patrimony = st.sidebar.number_input(
    "Meta de patrimônio (R$)",
    min_value=0.0, max_value=100_000_000.0, value=0.0, step=50_000.0,
    format="%.0f",
    help="Patrimônio-alvo no horizonte. Mostra prob. de bater. 0 desativa.",
)
with st.sidebar.expander("Volatilidades (σ anual)", expanded=False):
    for asset in pf_params.assets:
        asset.volatility = st.slider(
            f"σ — {asset.name} (%)", 0.0, 50.0, asset.volatility * 100, 1.0,
            key=f"vol_{asset.name}",
        ) / 100
    re_params.appreciation_volatility = st.slider(
        "σ — Valorização imóvel (%)", 0.0, 30.0, re_params.appreciation_volatility * 100, 1.0,
    ) / 100

mc_params = MonteCarloParams(target_patrimony=target_patrimony)  # n_trajectories e seed defaults
```

**Tabs** (7 abas em vez de 6, "🎲 Risco" entre "💸 Tributação" e "📥 Exportar"):

```python
tabs = st.tabs([
    "📌 Visão Geral",
    "🏠 Imóvel",
    "📈 Carteira",
    "🎯 Sensibilidade",
    "💸 Tributação",
    "🎲 Risco",        # NOVA
    "📥 Exportar",
])
```

**Pattern single-simulation extension:** `main()` roda determinístico (já fazia) E MC (novo) em paralelo. Resultados passados como parâmetros pra `render_overview` (recebe ambos), `render_risk` (só MC), `render_export` (determinístico, MC opcional pra anexar percentis).

`render_risk(re_mc, pf_mc, mc_params, horizon, capital_initial)`:
- KPIs (3 colunas × 4 linhas):
  - Linha 1: prob de bater meta (Carteira / Imóvel)
  - Linha 2: drawdown médio (Carteira / Imóvel)
  - Linha 3: p10 ano final (Carteira / Imóvel)
  - Linha 4: p90 ano final (Carteira / Imóvel)
- `patrimony_band_chart([re_mc, pf_mc])` — banda sobreposta
- `distribution_histogram_chart` por cenário (2 lado a lado)
- Banner amarelo se `>5%` das trajetórias terminam abaixo do capital inicial

**Banda sobreposta no overview**: em `render_overview`, **substituir** o `patrimony_evolution_chart` atual por uma única chamada `patrimony_band_chart(mc_results, deterministic_results=det_results)` que combina banda + linhas. Mantém um único chart na visão geral em vez de dois empilhados.

## Validação e edge cases

| Cenário | Comportamento |
|---|---|
| `volatility=0` em todos ativos + `appreciation_volatility=0` | Trajetórias colapsam em determinístico → p10=p50=p90 |
| `n_trajectories=1` | Aceito (degenerate); não bloqueia |
| `target_patrimony=0` | "Prob bater meta" oculto na UI; cálculo ainda roda |
| `seed` repetida | Resultado bit-a-bit idêntico |
| Retorno anual sorteado < −100% | Trajetória pode ficar negativa; aceito como representação de cenário extremo |
| `appreciation` sorteado negativo | Imóvel desvaloriza naquele ano; realista |
| Imóvel financiado com `portfolio_for_internal=None` | `ValueError` |
| Phase 1 aporte indexado em MC | Aplicado determinísticamente nos passos anuais (IPCA é determinístico) |

### Limites de input

| Campo | Limites | Step | Default |
|---|---|---|---|
| σ por ativo | 0% – 50% | 1% | histórico (ver lista acima) |
| σ valorização imóvel | 0% – 30% | 1% | 10% |
| Meta patrimônio | R$ 0 – 100M | R$ 50k | 0 (desativa) |
| N trajetórias | (fixo 10.000) | — | — |
| Seed | (fixa 42) | — | — |

## Performance

- N=10.000 × T=30 × K=5 ativos = 1,5M draws. NumPy `default_rng().normal()` em ~50ms.
- Memória: trajetórias shape (10.000, 31) × 8 bytes = ~2,5MB por cenário. OK.
- **Sem cache.** Cada interação re-simula. Total app render <200ms.
- Caso futuro: `st.cache_data` com hash de params. Não necessário pra MVP.

## Banner de risco (no Risco tab)

```
⚠️ Trajetórias com perda nominal
X% das trajetórias do cenário [Carteira/Imóvel] terminam abaixo do capital inicial
ao final do horizonte. Considere reduzir alocação em ativos de alta σ ou
ajustar o horizonte.
```

Renderizado quando `(final_distribution < capital_initial).mean() > 0.05`.

## Testes

**`tests/test_monte_carlo.py`** (~15 testes):

| # | Teste | Verifica |
|---|---|---|
| 1 | `test_zero_volatility_collapses_to_deterministic` | σ=0 → p10=p50=p90 = trajetória determinística |
| 2 | `test_seed_reproducibility` | Mesma seed → bit-a-bit idêntico |
| 3 | `test_different_seeds_produce_different_trajectories` | Sanity check |
| 4 | `test_n_trajectories_matches_shape` | `trajectories.shape == (N, horizon+1)` |
| 5 | `test_percentiles_are_monotonic` | p10 ≤ p50 ≤ p90 por ano |
| 6 | `test_mean_converges_to_deterministic_for_large_N` | N=50.000 → média ≈ determinístico (rel<2%) |
| 7 | `test_max_drawdown_non_negative` | Todas trajetórias têm drawdown ≥ 0 |
| 8 | `test_max_drawdown_matches_known_case` | Trajetória [100,120,80,90] → drawdown 33.3% |
| 9 | `test_prob_target_at_zero_is_one` | Capital baixo + σ baixa: `prob_target(0)` = 1.0 |
| 10 | `test_prob_target_at_inf_is_zero` | `prob_target(1e15)` = 0.0 |
| 11 | `test_carteira_mc_with_zero_contribution_no_aporte` | Aporte=0 → patrimônio cresce só pelos retornos |
| 12 | `test_carteira_mc_indexed_contribution_grows` | Aporte indexado: patrimônio médio cresce |
| 13 | `test_real_estate_mc_cash_unchanged_at_zero_vol` | Imóvel à vista σ=0 → reproduz determinístico |
| 14 | `test_real_estate_mc_financed_zero_vol_matches_deterministic` | Imóvel financiado σ=0 + portfolio σ=0 → reproduz Phase 2 financed |
| 15 | `test_real_estate_mc_requires_portfolio_when_financed` | financiado sem `portfolio_for_internal` → `ValueError` |

**Cobertura mínima:** 90%+ nas linhas tocadas.

## Ordem de implementação

Cada passo é commit isolado; app continua funcional após cada um.

1. Helpers puros (`_draw_normal_returns`, `_compute_percentiles`, `_compute_max_drawdowns`, `MonteCarloResult`) + 4 testes.
2. `MonteCarloParams` + volatilidades em `config.py` (sem testes — exercitado nos passos seguintes).
3. `simulate_portfolio_mc` + 4 testes (zero-σ, seed, convergência, aporte).
4. `simulate_real_estate_mc` (à vista) + 2 testes.
5. `simulate_real_estate_mc` (financiado) + 2 testes.
6. `charts.py` — `patrimony_band_chart` e `distribution_histogram_chart`.
7. UI sidebar (volatilidades + meta).
8. Aba "🎲 Risco" + banda no overview + banner de risco.
9. README atualizado.

## Impacto em arquivos existentes

| Arquivo | Mudança | Tamanho |
|---|---|---|
| `config.py` | + `MonteCarloParams`, + `volatility` em `AssetClass`, + `appreciation_volatility` em `RealEstateParams`, defaults históricos | ~30 linhas |
| `models.py` | + helpers, + `MonteCarloResult`, + `simulate_portfolio_mc`, + `simulate_real_estate_mc` | ~180 linhas |
| `charts.py` | + `patrimony_band_chart`, + `distribution_histogram_chart` | ~70 linhas |
| `app.py` | sidebar block, nova tab, `render_risk()`, banda no overview | ~110 linhas |
| `README.md` | seção análise de risco | ~12 linhas |

**Arquivo novo:** `tests/test_monte_carlo.py` (~250 linhas).

## Premissas

- Retornos **anuais** (não mensais) no MC — performance + simplicidade. Mensal só importaria pra cash flow detalhado, irrelevante pro patrimônio agregado.
- Distribuição **normal** por ativo — caudas finas mas didática. Migração futura pra t-Student é localizada.
- **Independência** entre ativos e entre Carteira/Imóvel — superestima diversificação. Limitação documentada.
- Aporte mensal **determinístico** — IPCA é fonte determinística do BCB.
- Phase 1 (aporte indexado) e Phase 2 (financiamento) integram corretamente com MC.

## Riscos

- Distribuição normal subestima eventos extremos (caudas gordas). Aceito como simplificação.
- Sem correlação → diversificação parece mais eficaz do que é. Aceito.
- Performance: 10k × 30 anos × 5 ativos ok hoje; se subir pra 100k via slider futuro, precisa cache.

## Fora de escopo

- **Salvar e comparar cenários** — Phase 2 sub-projeto 3 (próximo).
- Correlação entre ativos (matriz de covariância) — Phase 3.
- Distribuições não-normais (t-Student, log-normal) — Phase 3.
- VaR / CVaR (tail risk metrics formais) — Phase 3.
- Vacância estocástica do imóvel — fora de escopo permanente neste sub-projeto.
- Stress tests determinísticos (cenário fixo de crise) — Phase 3.
