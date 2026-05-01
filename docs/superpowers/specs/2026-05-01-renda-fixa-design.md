# Renda Fixa — Tracker de Posições

**Data:** 2026-05-01
**Status:** Spec aprovada (aguardando review final pelo usuário)

## Objetivo

Permitir que o usuário cadastre posições de renda fixa (Tesouro Direto, CDB, LCI, LCA, debêntures, etc.) com seus indexadores e prazos, e visualize a evolução do valor líquido (após IR) ao longo do tempo.

A feature é uma nova aba dedicada do dashboard, isolada das análises existentes (Imóvel × Carteira). Não substitui nem se integra ao item "Tesouro IPCA+ / LCI" da Carteira Diversificada — são análises independentes.

## Decisões de design

| # | Decisão | Justificativa |
|---|---------|---------------|
| 1 | Nova aba dedicada `📊 Renda Fixa` | Análise independente, não polui as comparações existentes |
| 2 | Modelo por indexador (Prefixado / CDI% / Selic+ / IPCA+) | Fidelidade — reusa `MacroParams` (Selic/CDI/IPCA do BCB) |
| 3 | IR regressivo automático (22,5% → 15% por holding period) | Realismo brasileiro; cada posição tem `purchase_date` |
| 4 | Vencimento opcional (campo `maturity_date`) | Cobre tanto Tesouro 2035 (com vencimento) quanto pós-fixados rolláveis |
| 5 | Só valor inicial — aportes adicionais viram novas posições | Cada compra tem seu próprio relógio de IR regressivo (modelo correto) |
| 6 | Tabela editável + gráfico de linhas por posição | Responde direto à pergunta "quanto cada uma rende ao longo do tempo" |
| 7 | Persistência: `st.session_state` + import/export CSV | Funciona em Streamlit Cloud, dados privados por sessão |

## Arquitetura

Distribuída seguindo o padrão do projeto:

| Arquivo | Adição |
|---|---|
| `config.py` | `FixedIncomePosition` dataclass + `IndexerKind` Literal |
| `models.py` | `FixedIncomeProjection`, `FixedIncomePortfolio` dataclasses + `simulate_fixed_income()` |
| `charts.py` | `fixed_income_evolution_chart()` |
| `app.py` | `render_fixed_income(macro, horizon)` + nova entrada em `st.tabs([...])` |
| `tests/test_fixed_income.py` | ~16 testes (novo arquivo) |

## 1. Modelo de dados (`config.py`)

```python
from datetime import date
from typing import Literal

IndexerKind = Literal["prefixado", "cdi", "selic", "ipca"]

@dataclass(slots=True)
class FixedIncomePosition:
    name: str                            # "LCI Banco X 2027"
    initial_amount: float                # R$ aportado
    purchase_date: date                  # data do aporte (pra IR regressivo)
    indexer: IndexerKind
    rate: float                          # decimal (ver tabela abaixo)
    maturity_date: date | None = None    # vencimento opcional
    is_tax_exempt: bool = False          # True para LCI/LCA/incentivadas
    color: str = "#3498DB"               # cor pro gráfico (auto-atribuída na UI)

    def effective_annual_rate(self, macro: MacroParams) -> float: ...
    def holding_days(self, at_date: date) -> int: ...
    def applicable_ir_rate(self, at_date: date) -> float: ...
```

### Como `rate` é interpretado por indexador

| indexer | rate é... | exemplo |
|---|---|---|
| `prefixado` | taxa anual nominal (decimal) | `0.12` = 12% a.a. |
| `cdi` | percentual do CDI (decimal) | `1.00` = 100% CDI; `0.95` = 95% CDI |
| `selic` | spread anual sobre Selic (decimal) | `0.001` = Selic + 0,1% |
| `ipca` | spread anual sobre IPCA (decimal) | `0.06` = IPCA + 6% |

### Conversão para taxa efetiva anual

```python
match indexer:
    case "prefixado": return rate
    case "cdi":       return macro.cdi * rate
    case "selic":     return macro.selic + rate
    case "ipca":      return (1 + macro.ipca) * (1 + rate) - 1   # composição correta
```

### IR regressivo (`applicable_ir_rate`)

| Holding (dias) | Alíquota |
|---|---|
| ≤ 180 | 22,5% |
| 181 – 360 | 20,0% |
| 361 – 720 | 17,5% |
| > 720 | 15,0% |
| qualquer (se `is_tax_exempt`) | 0% |

## 2. Engine de simulação (`models.py`)

```python
@dataclass(slots=True, frozen=True)
class FixedIncomeProjection:
    position: FixedIncomePosition
    years: np.ndarray              # 0, 1, ..., horizon
    gross_values: np.ndarray       # valor nominal no fim de cada ano
    net_values: np.ndarray         # após IR (== gross se isento)
    matured: np.ndarray            # bool — True a partir do ano de vencimento

@dataclass(slots=True, frozen=True)
class FixedIncomePortfolio:
    projections: list[FixedIncomeProjection]
    total_gross: np.ndarray
    total_net: np.ndarray
    total_initial: float

def simulate_fixed_income(
    positions: list[FixedIncomePosition],
    macro: MacroParams,
    horizon_years: int,
    start_date: date | None = None,        # default: date.today()
) -> FixedIncomePortfolio: ...
```

### Lógica de projeção (por posição, por ano)

1. `current_date = start_date + t anos`
2. Se há `maturity_date` e `current_date >= maturity_date`:
   - Trava valor no momento do vencimento (vira "caixa", não rende mais)
   - Holding period congelado em `(maturity - purchase).days`
3. Senão:
   - `holding_days = (current_date - purchase_date).days`
   - `gross = initial_amount * (1 + r) ** (holding_days / 365)`
4. **IR**:
   - Se `is_tax_exempt` ou `holding_days == 0`: `net = gross`
   - Senão: `ir = applicable_ir_rate(current_date)`; `net = initial_amount + (gross - initial_amount) * (1 - ir)`
   - **IR só incide sobre o ganho**, não sobre o principal

### Premissas

- Macro (Selic/CDI/IPCA) **constante** durante todo o horizonte (consistente com o resto do dashboard)
- "Ano 0" = `start_date` (hoje). Posição comprada no passado já mostra valor acumulado desde a compra
- O array `years` tem comprimento `horizon_years + 1` (anos 0, 1, …, horizon)
- Sem cupom semestral / sem marcação a mercado — modelo "carrega até o vencimento" (compound accrual)
- Anos de 365 dias para todos os cálculos (sem ajuste pra anos bissextos)
- `purchase_date` no futuro é rejeitado pela UI (validação) — engine assume `purchase_date <= start_date`

## 3. Gráfico (`charts.py`)

```python
def fixed_income_evolution_chart(portfolio: FixedIncomePortfolio) -> go.Figure:
    """Linha por posição mostrando evolução líquida no tempo."""
```

- **Uma linha por posição**, colorida com `position.color`
- Eixo Y: valor **líquido** (após IR regressivo)
- Hovertemplate consistente com o resto do app:
  ```
  <b>{name}</b>
  Ano X
  Líquido: R$ Y
  ```
- `hovermode="x unified"` — ver todas as posições no mesmo ano de uma vez
- Posições com vencimento ficam flat naturalmente após `maturity_year` (sem annotation extra)
- Layout: `_LAYOUT_DEFAULTS + _BOTTOM_LEGEND`
- Sem linha "Total" agregada — totais ficam na tabela; gráfico foca em comparação por posição

## 4. UI da aba (`app.py`)

Nova função `render_fixed_income(macro: MacroParams, horizon: int)` registrada como 8ª aba `📊 Renda Fixa`.

### Estrutura

```
📊 Renda Fixa
Caption: "Cadastre suas posições. IR regressivo aplicado automaticamente."

[📥 Carregar CSV] [📤 Baixar CSV]

Tabela editável (st.data_editor) com colunas:
  Nome | Indexador | Taxa (%) | Aporte (R$) | Data aporte | Vencimento | Isento IR

[Gráfico de evolução líquida]

Tabela resumo (read-only):
  Nome | Indexador | Taxa efetiva (%) | Aporte | Bruto fim | Líquido fim | Ganho líquido
  ───────────────────────────────────────────────────────────────────────
  Total                       —          Σ aporte  Σ bruto    Σ líquido    Σ líq − Σ aporte

(coluna "Taxa efetiva" do total fica em branco — não faz sentido média)
```

### Coluna "Taxa (%)" — interpretação por indexador

Mostrada como percentual (ex: `12.00`). Internamente: divide por 100 no save, multiplica por 100 no display.

Caption explicando:
- Prefixado: taxa anual (ex: `12.00`)
- CDI: percentual do CDI (ex: `100.00`)
- Selic: spread sobre Selic em pp (ex: `0.10`)
- IPCA: spread sobre IPCA em pp (ex: `6.00`)

### Persistência (`st.session_state["fi_positions"]`)

- Init com lista vazia (ou 1 linha em branco)
- `data_editor` lê/grava de session_state
- Cor da posição: auto-atribuída por índice de linha a partir de paleta fixa de 8 cores. Não exposta ao usuário

### CSV import/export

Formato fixo (header obrigatório, ordem livre):

```
name,initial_amount,purchase_date,indexer,rate,maturity_date,is_tax_exempt
LCI Banco X,30000.00,2025-03-15,cdi,0.95,2027-03-15,true
Tesouro IPCA+ 2035,50000.00,2024-08-01,ipca,0.06,2035-08-01,false
```

- `purchase_date` e `maturity_date`: ISO 8601 (`YYYY-MM-DD`); `maturity_date` pode ser vazio
- `rate`: decimal (`0.95` = 95% CDI, `0.06` = IPCA+6%) — mesmo formato do dataclass, **não** o display percentual da UI
- `is_tax_exempt`: `true`/`false`
- `color` não vai no CSV (auto-atribuído na deserialização)
- **Export**: `pd.DataFrame.to_csv(index=False)` via `st.download_button`. Nome: `renda-fixa-YYYY-MM-DD.csv`
- **Import**: `st.file_uploader(type="csv")` → parse + validação → substitui session_state. Erro de parsing → `st.error()` apontando a linha problemática

### Validações

| Condição | Comportamento |
|---|---|
| `name` vazio | Linha ignorada na simulação |
| `initial_amount <= 0` | Linha ignorada |
| `maturity_date <= purchase_date` | `st.error()` — bloqueia simulação |
| `purchase_date > today` (start_date) | `st.error()` — data de aporte não pode ser futura |
| `rate <= 0` | `st.warning()` — simula, mas não cresce |
| Sem nenhuma posição válida | `st.info("Cadastre ao menos uma posição válida.")` no lugar do gráfico |

## 5. Testes (`tests/test_fixed_income.py`)

Cobertura: ~16 testes determinísticos com fixtures pequenas.

### Conversão indexador → taxa efetiva
- `test_effective_rate_prefixado` — rate=0.12 → 0.12
- `test_effective_rate_cdi_percentual` — 100% CDI com cdi=0.1465 → 0.1465
- `test_effective_rate_selic_com_spread` — Selic + 0.1% com selic=0.1475 → 0.1485
- `test_effective_rate_ipca_compoe_corretamente` — IPCA+6% com ipca=0.048 → ~0.11088

### IR regressivo
- `test_ir_regressivo_22_5_ate_180_dias`
- `test_ir_regressivo_20_entre_181_e_360`
- `test_ir_regressivo_17_5_entre_361_e_720`
- `test_ir_regressivo_15_acima_de_720`
- `test_ir_isento_zero_independente_do_holding`

### Simulação ponta-a-ponta
- `test_simulate_prefixado_3_anos_golden_numbers` — números fechados ano a ano (bruto + líquido)
- `test_simulate_isento_net_igual_gross`
- `test_simulate_vencimento_congela_valor_apos_maturity`
- `test_simulate_posicao_comprada_no_passado_ja_inicia_acumulada`
- `test_portfolio_totals_somam_corretamente_multiplas_posicoes`

### CSV
- `test_csv_roundtrip_preserva_todos_os_campos`
- `test_csv_indexador_invalido_levanta_validation_error`

### Fora de escopo (smoke manual)
- UI (st.data_editor, file_uploader, download_button) — `streamlit.testing.v1` é flaky e adiciona dependência. Smoke manual no navegador é suficiente.
- Cor auto-atribuída por índice — trivial.

## Critério de aceitação

1. Os 16 testes em `tests/test_fixed_income.py` passam
2. Smoke manual no navegador:
   - Cadastrar 3 posições (1 prefixada, 1 CDI, 1 LCI isenta com vencimento)
   - Gráfico e tabela renderizam corretamente
   - Baixar CSV, recarregar a página, fazer upload do CSV — estado restaurado idêntico
3. Nenhuma regressão visível nas outras 7 abas existentes
