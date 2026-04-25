# Fase 1 — Base de dados e correções estruturais

**Data:** 2026-04-25
**Status:** Aprovado
**Escopo:** Dashboard `dashboard/` (Streamlit) — primeira fase de melhorias.

## Objetivo

Estabelecer fundação correta antes de novas features:

1. **Aporte mensal indexado pela inflação** na carteira diversificada (campo essencial faltando no modelo).
2. **Integração com a API SGS do Banco Central** para indicadores macro ao vivo (Selic, IPCA, CDI, USD/BRL), com fallback robusto.
3. **Cache da chamada externa** via `st.cache_data` (TTL 24h) para reduzir latência e respeitar a API. Simulações financeiras (`simulate_*`) não são cacheadas — são baratas e cache exigiria dataclasses hashable (over-engineering pro escopo atual).

## Decisões de produto

| # | Decisão | Razão |
|---|---|---|
| 1 | Aporte mensal **só na carteira** | Imóvel é ativo travado pós-compra; reflete realidade. Financiamento entra na Fase 2. |
| 2 | Aporte **indexado por IPCA** (default ligado, com toggle) | Em horizontes de 10-30 anos, valor nominal fixo perde poder de compra. |
| 3 | API BCB com **cache 24h** + fallback | Equilíbrio entre dados frescos e resiliência. |
| 4 | API falha → **valores hardcoded de Abr/2026** + banner de aviso | App nunca fica inutilizável; usuário sabe que está em modo offline. |
| 5 | Sliders macro **continuam editáveis** | Preserva flexibilidade atual ("e se Selic subir pra 18%?"). API só muda os defaults. |
| 6 | Falha **tudo-ou-nada** na API | Se 1 das 4 séries falhar, vai tudo pro fallback. Simplifica raciocínio do usuário. |

## Arquitetura

```
dashboard/
├── app.py                  # entry point Streamlit
├── config.py               # constantes + dataclasses
├── models.py               # engine de simulação
├── charts.py               # (sem mudanças)
├── data_sources/
│   ├── __init__.py
│   └── bcb.py              # NOVO: cliente HTTP da API SGS
├── services/
│   ├── __init__.py
│   └── macro.py            # NOVO: cache + fallback + flag stale
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_bcb.py
│   ├── test_macro.py
│   └── test_models.py
├── requirements.txt        # +requests
└── requirements-dev.txt    # NOVO: pytest, pytest-mock
```

### Fluxo de dados

```
[BCB SGS API]
      │  (HTTP GET séries 432/433/12/1)
      ▼
data_sources/bcb.py  ──── falha ────┐
      │                              │
      ▼                              ▼
services/macro.py  ◄─────────  MACRO_FALLBACK (config.py)
      │  (cached 24h)
      ▼
config.MacroParams (Selic, IPCA, CDI, USD, is_stale, source_label)
      │
      ▼
app.py sidebar (defaults editáveis) + banner se stale
      │
      ▼
models.py simulate_*  →  charts.py  →  st.plotly_chart
```

**Princípio de isolamento:** dados externos em `data_sources/`, cache+fallback em `services/`, app continua só consumindo dataclasses. Fase 2 (Monte Carlo) reaproveita a mesma estrutura.

## Componentes

### `data_sources/bcb.py`

Cliente HTTP puro, sem dependência do Streamlit.

```python
SGS_SERIES = {"selic": 432, "ipca": 433, "cdi": 12, "usd_brl": 1}

@dataclass
class BcbReading:
    selic: float          # decimal anual (ex.: 0.1475)
    ipca_12m: float       # IPCA acumulado 12 meses, decimal
    cdi: float            # decimal anual
    usd_brl: float        # PTAX venda
    fetched_at: datetime

class BcbApiError(Exception):
    pass

def fetch_macro(timeout: float = 5.0) -> BcbReading:
    """Busca os 4 indicadores. Lança BcbApiError em qualquer falha."""
```

- Endpoint: `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{id}/dados/ultimos/{n}?formato=json`
  - IPCA: `n=12` (mensal, acumulado via produto `Π(1 + r_i) − 1`)
  - Selic, CDI, USD/BRL: `n=1`
- Selic e CDI vêm como taxa diária, são convertidos pra anual via `(1 + r)^252 − 1`.
- Timeout 5s, sem retry.
- Falha em qualquer série → `BcbApiError` (tudo-ou-nada).

### `services/macro.py`

```python
@dataclass
class MacroParams:
    selic: float
    ipca: float
    cdi: float
    usd_brl: float
    is_stale: bool          # True se usou fallback
    source_label: str       # "BCB SGS (live)" ou "Fallback (Abr/2026)"

@st.cache_data(ttl=86400, show_spinner=False)
def get_macro_params() -> MacroParams: ...
```

- Tenta `bcb.fetch_macro()`. Sucesso → `is_stale=False`, label "BCB SGS (live)".
- `BcbApiError` → usa `MACRO_FALLBACK` de `config.py`, `is_stale=True`, label "Fallback (Abr/2026)".
- Cache no service (não em `bcb.py`) — mantém data layer testável sem mock do Streamlit.

### `config.py` — refatoração leve

- Constantes existentes (`SELIC_RATE`, `IPCA_EXPECTED`, `CDI_RATE`, `USD_BRL`) viram fonte de `MACRO_FALLBACK: MacroParams`.
- `RealEstateParams`, `BenchmarkParams`: sem mudança.
- `PortfolioParams` ganha:
  ```python
  monthly_contribution: float = 0.0          # R$/mês em valor de hoje
  contribution_inflation_indexed: bool = True
  ```

### `models.py` — `simulate_portfolio` estendido

- Para cada ano `t ∈ [0, horizon-1]`: aporte anual = `12 * monthly_contribution`, corrigido por `(1 + ipca) ** t` se `contribution_inflation_indexed`.
- Aporte entra no início do ano (PMT begin) — simplificação aceita.
- Yields existentes não são recalculados; aporte apenas soma ao principal.
- `simulate_real_estate` e `simulate_benchmark`: **inalterados**.

### `app.py` — pontos de mudança

- Sidebar: novo bloco "💰 Aporte mensal" com `number_input` (R$) + `checkbox` "Indexar pelo IPCA" (default true).
- Cabeçalho: ler `MacroParams` via `get_macro_params()`, exibir badge com `source_label`.
- Banner amarelo no topo quando `is_stale=True`.
- Sliders macro usam `MacroParams.<campo>` como default em vez de constantes literais.
- Botão "🔄 Recarregar dados macro" no rodapé da sidebar (chama `get_macro_params.clear()`).

## Validação e error handling

### Falhas da API

| Cenário | Comportamento |
|---|---|
| Timeout (5s) | `BcbApiError("timeout")` → fallback + banner |
| HTTP 4xx/5xx | `BcbApiError("http_<status>")` → fallback + banner |
| JSON malformado / série vazia | `BcbApiError("invalid_payload")` → fallback + banner |
| Indicador parcial (3 OK, 1 falhou) | Tudo-ou-nada → fallback + banner |
| `requests.ConnectionError` | Fallback + banner |

**Banner:** `⚠️ Indicadores macro indisponíveis ao vivo. Usando referências de Abr/2026. Tente recarregar em alguns minutos.` Renderizado uma vez no topo (após `st.title`), fundo amarelo claro.

### Validações de aporte

- **Mínimo:** 0 (zero desativa, comportamento idêntico ao app atual).
- **Máximo:** R$ 100.000/mês.
- **Step:** R$ 100.
- Indexação usa o IPCA do `MacroParams` ativo. Se usuário sobrescreveu o slider de IPCA, **usa o valor sobrescrito** (filosofia "sliders sempre ganham").

### Edge cases do modelo

- `monthly_contribution = 0` + `indexed = True` → matemática inalterada (multiplicador × 0 = 0). Sem branch.
- Horizonte = 1 ano + indexação → IPCA do ano 0 = 1.0. Aporte do ano 0 entra com valor nominal. Anos seguintes corrigem por `(1 + ipca) ** t`.
- IPCA = 0% → indexação degenera no caso nominal.
- IPCA negativo (deflação) → permitido, modelo é simétrico.
- `reinvest = False` + aporte > 0 → aporte ainda entra no principal; yields são distribuídos. Comportamento esperado.

### Cache invalidation

- `st.cache_data(ttl=86400)` invalida a cada 24h.
- Botão "🔄 Recarregar dados macro" chama `get_macro_params.clear()` manualmente.

## Testes

**Stack:** `pytest` + `pytest-mock`. Sem rodar Streamlit em testes — só lógica pura.

**`requirements-dev.txt`:** `pytest>=8.0`, `pytest-mock>=3.12`. Separado pra não inflar deploy do Streamlit Cloud.

### `test_bcb.py` — cliente HTTP isolado (mock `requests.get`)

| Caso | Verifica |
|---|---|
| Resposta válida das 4 séries | `BcbReading` populado; IPCA mensal acumula em anual via produto |
| Timeout | Lança `BcbApiError("timeout")` |
| HTTP 500 | Lança `BcbApiError("http_500")` |
| JSON inválido | Lança `BcbApiError("invalid_payload")` |
| Lista vazia | Lança `BcbApiError("invalid_payload")` |
| Falha em 1 das 4 séries | Lança `BcbApiError` (tudo-ou-nada) |

### `test_macro.py` — service de cache+fallback

Não testa `st.cache_data` em si. Testa lógica de fallback:

| Caso | Verifica |
|---|---|
| `bcb.fetch_macro` sucesso | `is_stale == False`, valores do mock |
| `bcb.fetch_macro` raises `BcbApiError` | `is_stale == True`, valores do `MACRO_FALLBACK` |
| Fallback contém todos os 4 indicadores | Smoke test |

### `test_models.py` — engine financeira

Foco no que mudou (`simulate_portfolio` com aporte) + regressão do inalterado:

| Caso | Verifica |
|---|---|
| `monthly_contribution = 0` (qualquer indexed) | Patrimônio idêntico ao comportamento pré-refatoração |
| Aporte nominal, IPCA=0, horizonte=10 | Soma simples: capital + 12 × aporte × 10 + yields |
| Aporte indexado, IPCA=5%, horizonte=10 | Aporte do ano `t` = `aporte_base × 1.05 ** t` |
| Aporte indexado, IPCA=0% | Equivalente ao nominal |
| Aporte > 0, reinvest=False | Capital cresce só pelo aporte (yields distribuídos) |
| `simulate_real_estate` e `simulate_benchmark` | Output idêntico antes/depois do refator (regressão) |

**Cobertura mínima:** 90%+ nas linhas tocadas. Sem CI no GitHub agora — rodar local com `pytest tests/` antes de cada push.

## Ordem de implementação

Cada passo é commit isolado; app continua funcional após cada um.

1. **Setup de testes** — `tests/`, `conftest.py`, `requirements-dev.txt`. `pytest` roda (sem testes ainda).
2. **`data_sources/bcb.py`** + `test_bcb.py`. Sem integrar no app.
3. **`services/macro.py`** + `MACRO_FALLBACK` em `config.py` + `test_macro.py`. Sem integrar no app.
4. **Integrar macro no `app.py`** — sliders consomem `MacroParams`, banner stale. Resto do app inalterado. *Deploy intermediário possível.*
5. **Estender `models.simulate_portfolio`** + `test_models.py`.
6. **UI do aporte na sidebar** + plumbing dos params. *Deploy final.*

## Impacto em arquivos existentes

| Arquivo | Mudança | Tamanho |
|---|---|---|
| `app.py` | input aporte, banner stale, import services | ~30 linhas |
| `config.py` | `MACRO_FALLBACK` + 2 campos em `PortfolioParams` | ~15 linhas |
| `models.py` | `simulate_portfolio` aceita aporte+indexação | ~20 linhas |
| `charts.py` | nenhuma | 0 |
| `requirements.txt` | `+requests` | 1 linha |
| `README.md` | seção sobre dados ao vivo + aporte | ~10 linhas |

**Arquivos novos:** `data_sources/bcb.py`, `services/macro.py`, `tests/*` (4 arquivos), `requirements-dev.txt`.

## Premissas

- Streamlit Cloud free tier aceita chamadas HTTP outbound.
- API SGS do BCB permanece estável (público, sem auth).
- Usuários fazem análises pontuais, não batch — `ttl=86400` adequado.
- Teste de regressão usa valores hardcoded (não comparação dinâmica).

## Riscos

- **Lentidão da API fora de horário comercial** → mitigado por timeout 5s + fallback.
- **Mudança de schema do SGS** → quebraria silenciosamente; aceito como risco baixo (smoke com response real seria caro).

## Fora de escopo (Fase 2+)

- Monte Carlo / simulação estocástica
- Financiamento imobiliário (entrada + parcelas)
- Salvar e comparar cenários
- Modo escuro, tooltips, URL params, export PDF
- Onboarding e refinamento mobile
