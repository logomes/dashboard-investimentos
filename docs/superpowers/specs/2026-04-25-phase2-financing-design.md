# Phase 2 (sub-projeto 1) — Financiamento imobiliário

**Data:** 2026-04-25
**Status:** Aprovado
**Escopo:** Cenário Imóvel ganha modo "financiado" opcional (SAC ou Price). Phase 2 tem 3 sub-projetos independentes; este é o primeiro. Os outros (Monte Carlo, Salvar/Comparar) terão specs próprios.

## Objetivo

Adicionar financiamento imobiliário ao cenário Imóvel sem quebrar o comportamento atual (à vista). Permite ao usuário simular alavancagem real (entrada + parcelas SAC/Price), com comparação justa contra a Carteira diversificada.

## Decisões de produto

| # | Decisão | Razão |
|---|---|---|
| 1 | Toggle no cenário Imóvel existente (não cenário separado) | Menos invasivo; preserva tudo de Phase 1; "financiamento desligado" = comportamento atual |
| 2 | Sobra do capital → carteira interna do cenário Imóvel, com mesmo blended yield da Carteira | Comparação justa: mesmo dinheiro, alocações diferentes |
| 3 | SAC e Price com toggle (default SAC) | SAC é o sistema dominante hoje (Caixa); Price ainda relevante. Custo: 1 selectbox |
| 4 | Carteira interna pode ficar negativa; UI alerta visualmente | Honesto — revela cenários insustentáveis em vez de mascarar |
| 5 | Taxa de juros nominal (sem TR) | Simplificação; TR está zerada na prática há anos. TR seria spec separado |
| 6 | Seguro mensal (MIP+DFI) default 0,05% a.m. sobre saldo devedor, oculto da UI | Proxy razoável; varia por idade/imóvel mas evita inflar inputs |
| 7 | Juros de financiamento **não** dedutíveis no IR sobre aluguel | Regra atual da RFB no carnê-leão. Sem mudança no `income_tax_amount` |

## Arquitetura

```
dashboard/
├── app.py              # toggle + inputs financiamento + alerta saldo negativo
├── config.py           # NOVO FinancingParams + campo opcional em RealEstateParams
├── models.py           # NOVO _sac_schedule, _price_schedule; estende simulate_real_estate
├── charts.py           # NOVO debt_evolution_chart (opcional)
├── data_sources/       # (sem mudanças)
├── services/           # (sem mudanças)
└── tests/
    ├── test_financing.py   # NOVO — testes puros das fórmulas SAC/Price
    └── test_models.py      # estendido com cenários financiados
```

### Modelo de dados

```python
@dataclass(slots=True, frozen=True)
class FinancingParams:
    term_years: int = 30
    annual_rate: float = 0.115            # 11.5% a.a. (TR + spread Caixa típico)
    entry_pct: float = 0.20               # 20% de entrada
    system: Literal["SAC", "Price"] = "SAC"
    monthly_insurance_rate: float = 0.0005  # MIP+DFI ≈ 0.05% a.m.

    @property
    def monthly_rate(self) -> float:
        return (1 + self.annual_rate) ** (1/12) - 1
```

`RealEstateParams` ganha 1 campo:
```python
financing: FinancingParams | None = None
```

`SimulationResult` ganha 1 campo opcional:
```python
debt_balance: np.ndarray | None = None      # ano a ano; None se à vista
```

### Fluxo de simulação (financiado)

```
entry = property_value * financing.entry_pct
loan_principal = property_value - entry
internal_buffer_initial = capital_initial - entry
schedule = build_schedule(financing, loan_principal)   # mensal

for each year y:
    annual_rent_net = (rent * 12) - costs                       # como Phase 1
    annual_payment = schedule.payments[12y .. 12y+12].sum()
    annual_insurance = schedule.balance[year_start..year_end] * monthly_insurance_rate
    net_cash_flow = annual_rent_net - annual_payment - annual_insurance

    internal_portfolio = internal_portfolio*(1 + blended_yield) + net_cash_flow
    property_value_t = property_value * (1 + appreciation)^y
    debt_balance[y] = schedule.balance[12y]

patrimony[y] = property_value_t - debt_balance[y] + internal_portfolio
```

Após o término do financiamento (ano > term), parcela = 0 e cash flow = aluguel - custos.

### Princípio de isolamento

Financiamento é uma camada opcional sobre o modelo Phase 1. Helpers de amortização (SAC, Price) ficam puros e testáveis independentemente. `simulate_real_estate` ramifica em `if params.financing is None` mantendo regressão garantida.

## Componentes

### `config.py`

- Novo `FinancingParams` (frozen dataclass).
- `RealEstateParams.financing: FinancingParams | None = None` no final dos campos, antes dos métodos.
- Sem outras mudanças.

### `models.py`

- `AmortizationSchedule` (frozen dataclass) — vetores NumPy de `payments`, `interest`, `principal`, `balance` (todos tamanho `n_months`).
- `_sac_schedule(principal, monthly_rate, n_months) -> AmortizationSchedule`.
- `_price_schedule(principal, monthly_rate, n_months) -> AmortizationSchedule`.
- `build_schedule(financing, principal) -> AmortizationSchedule` — dispatch baseado em `financing.system`.
- Refator: caminho atual de `simulate_real_estate` extraído em `_simulate_real_estate_cash` (sem mudança funcional).
- Nova função `_simulate_real_estate_financed`.
- `simulate_real_estate(params, horizon, reinvest, ipca=0.0, capital_initial=None)` — top-level dispatcher. `capital_initial=None` assume `= property_value` (compatível com Phase 1).
- `SimulationResult` ganha `debt_balance: np.ndarray | None = None`.

### `charts.py`

- `debt_evolution_chart(result, financing)` — area chart do saldo devedor decrescente. Renderizado apenas quando `financing is not None`.

### `app.py`

UI no bloco "🏠 Imóvel" da sidebar (após campos atuais):

```python
financing_enabled = st.sidebar.checkbox("Financiar imóvel", value=False)
if financing_enabled:
    with st.sidebar.expander("Detalhes do financiamento", expanded=True):
        entry_pct = st.slider("Entrada (% do imóvel)", 10, 80, 20, 5) / 100
        term_years = st.slider("Prazo (anos)", 5, 35, 30, 1)
        annual_rate = st.slider("Taxa anual (%)", 6.0, 18.0, 11.5, 0.25) / 100
        system = st.radio("Sistema", ["SAC", "Price"], horizontal=True)
    re_params.financing = FinancingParams(
        term_years=term_years, annual_rate=annual_rate,
        entry_pct=entry_pct, system=system,
    )
```

Aba "🏠 Imóvel" — quando financiado:
- KPIs adicionais: Entrada, Parcela inicial, Juros totais.
- Banner amarelo se `min(internal_portfolio) < 0`: "⚠️ Cenário com fluxo negativo: carteira interna fica deficitária no ano N".
- Gráfico `debt_evolution_chart` exibido entre KPIs e custos.

Capital insuficiente:
```
if capital_initial < entry:
    st.error("Capital insuficiente para a entrada (R$ X). Aumente o capital ou reduza % de entrada.")
    return  # bloqueia simulação
```

## Validação e edge cases

| Cenário | Comportamento |
|---|---|
| `financing = None` | Caminho Phase 1 idêntico (regressão garantida) |
| `entry_pct = 0` | Bloqueado pela UI (mín. 10%); aceita programaticamente |
| `horizon < term` | Saldo devedor remanescente em `debt_balance[-1]`; honesto |
| `horizon > term` | Após `term`, parcela = 0; cash flow só com aluguel - custos |
| `monthly_rate = 0` | SAC e Price degeneram em `principal/n` (sem juros) |
| `internal_portfolio < 0` | Continua simulando; banner alerta no ano em que cruza zero |
| Aluguel = 0 (12 meses vacância) | Tratado por `vacancy_loss`; déficit normal se aluguel insuficiente |
| `capital_initial < entry` | Erro UI; simulação não roda |

### Limites de input

| Campo | Limites | Step | Default |
|---|---|---|---|
| Entrada (%) | 10 – 80% | 5% | 20% |
| Prazo | 5 – 35 anos | 1 | 30 |
| Taxa anual | 6 – 18% | 0,25% | 11,5% |
| Sistema | SAC / Price | — | SAC |

## Testes

**Stack:** `pytest` + `pytest-mock` (já instalados na Phase 1).

### `tests/test_financing.py` — fórmulas puras

| # | Teste | Verifica |
|---|---|---|
| 1 | `test_sac_amortization_is_constant` | `principal` constante = `principal_loan/n` |
| 2 | `test_sac_balance_decreases_to_zero` | `balance[-1] ≈ 0`; monotonicamente decrescente |
| 3 | `test_sac_payment_decreasing` | `payments` estritamente decrescente |
| 4 | `test_sac_total_principal_equals_loan` | `principal.sum() ≈ loan_amount` |
| 5 | `test_price_payment_is_constant` | `payments` ≈ todos iguais |
| 6 | `test_price_balance_decreases_to_zero` | `balance[-1] ≈ 0` |
| 7 | `test_price_principal_increasing` | `principal` estritamente crescente |
| 8 | `test_price_total_principal_equals_loan` | `principal.sum() ≈ loan_amount` |
| 9 | `test_price_pmt_formula_known_case` | principal=100k, rate=0,01/mês, n=12 → PMT≈8884.88 |
| 10 | `test_total_interest_price_greater_than_sac` | `price.interest.sum() > sac.interest.sum()` (mesmos inputs) |
| 11 | `test_zero_rate_degenerate_case` | rate=0 → ambos: parcela = principal/n, juros = 0 |
| 12 | `test_build_schedule_dispatches_correctly` | `system="SAC"` → SAC; `"Price"` → Price |

### `tests/test_models.py` — extensões

| # | Teste | Verifica |
|---|---|---|
| 1 | `test_real_estate_no_financing_unchanged` | Regressão Phase 1: `financing=None` → output idêntico |
| 2 | `test_real_estate_with_financing_returns_debt_balance` | `result.debt_balance is not None`, tamanho `horizon+1` |
| 3 | `test_financed_horizon_equals_term_pays_off` | `horizon=term` → `debt_balance[-1] ≈ 0` |
| 4 | `test_financed_horizon_less_than_term_leaves_debt` | `horizon=10, term=30` → `debt_balance[-1] > 0` |
| 5 | `test_financed_horizon_greater_than_term_zero_after_term` | `debt_balance[31:] ≈ 0` |
| 6 | `test_financed_internal_portfolio_can_go_negative` | Aluguel baixo + parcela alta → carteira interna negativa em algum ano |
| 7 | `test_capital_initial_split_correctly` | `capital=300k, entry_pct=20%, property=200k` → buffer = 260k |
| 8 | `test_sac_vs_price_final_patrimony` | Mesmos inputs, sistemas diferentes → ambos válidos; Price gasta mais juros |

**Cobertura mínima:** 90%+ nas linhas tocadas.

## Ordem de implementação

Cada passo é commit isolado; app continua funcional após cada um.

1. **Helpers de amortização** (`_sac_schedule`, `_price_schedule`, `build_schedule`, `AmortizationSchedule`) + `tests/test_financing.py` (12 testes). TDD.
2. **`FinancingParams`** em `config.py` + campo em `RealEstateParams`.
3. **Refator `simulate_real_estate`** — extrai caminho atual em `_simulate_real_estate_cash`. Roteamento via `if params.financing is None`. Sem mudança funcional.
4. **`SimulationResult.debt_balance`** opcional, default `None`. Sem regressão.
5. **`_simulate_real_estate_financed` completo** + 8 testes em `tests/test_models.py`.
6. **UI toggle e inputs** em `app.py`.
7. **KPIs e alertas** + opcional `debt_evolution_chart` em `charts.py`.
8. **README** atualizado.

## Impacto em arquivos existentes

| Arquivo | Mudança | Tamanho |
|---|---|---|
| `config.py` | + `FinancingParams` + 1 campo | ~25 linhas |
| `models.py` | + 4 funções + refator | ~140 linhas |
| `app.py` | UI toggle, inputs, KPIs, banner | ~50 linhas |
| `charts.py` | + `debt_evolution_chart` | ~30 linhas |
| `README.md` | seção financiamento | ~15 linhas |

**Arquivo novo:** `tests/test_financing.py` (~150 linhas).

## Premissas

- Taxa anual nominal, sem TR (TR está zerada na prática há anos).
- Seguro mensal MIP+DFI proxy combinado em 0,05% a.m. sobre saldo devedor.
- ITBI/cartório (já em `acquisition_cost_pct = 5%`) inalterado.
- Parcela mensal, agregação anual (consistente com Phase 1).
- Juros não-dedutíveis no IR sobre aluguel (regra RFB para PF).

## Riscos

- Bancos reais aplicam TR + spread em alguns produtos. Aceito como simplificação.
- Seguro real varia muito; 0,05% a.m. é proxy razoável de mercado.
- Refinanciamento/portabilidade fora de escopo.

## Fora de escopo (sub-projetos seguintes da Phase 2)

- **Monte Carlo / análise estocástica** — sub-projeto 2 da Phase 2
- **Salvar e comparar cenários** — sub-projeto 3 da Phase 2

E também fora de escopo permanentemente neste sub-projeto:
- TR (correção do saldo devedor)
- IR sobre venda do imóvel
- Reformas/manutenção pesada além de `maintenance_annual`
